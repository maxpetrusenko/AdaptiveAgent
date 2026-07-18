import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.evidence import (
    apply_evidence,
    missing_criteria,
    trusted_request_hash,
)
from app.tasks.persistence import ensure_schema, request_hash, row_to_task, set_checkpoint
from app.tasks.schemas import (
    AdvanceCommand,
    ReplanCommand,
    TaskCreate,
    TrustedVerificationResult,
)


class TaskNotFoundError(Exception):
    pass


class InvalidTaskTransitionError(Exception):
    pass


class EvidenceRequiredError(Exception):
    def __init__(self, missing_criteria: list[str]):
        self.missing_criteria = missing_criteria


class IdempotencyConflictError(Exception):
    pass


class ConcurrentMutationError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


async def _fetch_task(db: AsyncSession, task_id: str) -> dict[str, Any]:
    await ensure_schema(db)
    result = await db.execute(
        text("SELECT * FROM task_ledgers WHERE id = :task_id"),
        {"task_id": task_id},
    )
    row = result.first()
    if row is None:
        raise TaskNotFoundError
    return row_to_task(row)


async def create_task(db: AsyncSession, command: TaskCreate) -> dict[str, Any]:
    await ensure_schema(db)
    task_id = _uuid()
    now = _now()
    criteria = [
        {
            "id": criterion.id,
            "description": criterion.description,
            "evidence": [],
        }
        for criterion in command.acceptance_criteria
    ]
    steps = [
        {
            "id": _uuid(),
            "title": step.title,
            "status": "active" if index == 0 else "pending",
        }
        for index, step in enumerate(command.steps)
    ]
    await db.execute(
        text(
            """
            INSERT INTO task_ledgers (
                id, goal, constraints_json, criteria_json, steps_json, status,
                plan_version, current_step_index, stall_count, stall_threshold,
                action_budget, actions_used, checkpoint_sequence,
                checkpoint_operation, created_at, updated_at
            ) VALUES (
                :id, :goal, :constraints, :criteria, :steps, 'active',
                1, 0, 0, :stall_threshold, :action_budget, 0, 1, 'create',
                :created_at, :updated_at
            )
            """
        ),
        {
            "id": task_id,
            "goal": command.goal,
            "constraints": _dump(command.constraints),
            "criteria": _dump(criteria),
            "steps": _dump(steps),
            "stall_threshold": command.stall_threshold,
            "action_budget": command.action_budget,
            "created_at": now,
            "updated_at": now,
        },
    )
    await db.commit()
    return await _fetch_task(db, task_id)


async def list_tasks(db: AsyncSession) -> list[dict[str, Any]]:
    await ensure_schema(db)
    result = await db.execute(
        text("SELECT * FROM task_ledgers ORDER BY created_at DESC")
    )
    return [row_to_task(row) for row in result.fetchall()]


async def get_task(db: AsyncSession, task_id: str) -> dict[str, Any]:
    return await _fetch_task(db, task_id)


async def _cached_effect(
    db: AsyncSession,
    task_id: str,
    operation: str,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT response_json, request_hash FROM task_effect_journal
            WHERE task_id = :task_id
              AND operation = :operation
              AND idempotency_key = :idempotency_key
            """
        ),
        {
            "task_id": task_id,
            "operation": operation,
            "idempotency_key": idempotency_key,
        },
    )
    row = result.first()
    if row is None:
        return None
    stored_hash = row._mapping["request_hash"]
    if stored_hash and stored_hash != request_hash:
        raise IdempotencyConflictError
    return json.loads(row._mapping["response_json"])


async def _save_task_and_effect(
    db: AsyncSession,
    task: dict[str, Any],
    operation: str,
    idempotency_key: str,
    request_hash: str,
    expected_sequence: int,
) -> bool:
    update = await db.execute(
        text(
            """
            UPDATE task_ledgers SET
                criteria_json = :criteria,
                steps_json = :steps,
                status = :status,
                plan_version = :plan_version,
                current_step_index = :current_step_index,
                stall_count = :stall_count,
                actions_used = :actions_used,
                replan_reason = :replan_reason,
                escalation_reason = :escalation_reason,
                checkpoint_sequence = :checkpoint_sequence,
                checkpoint_operation = :checkpoint_operation,
                checkpoint_idempotency_key = :checkpoint_idempotency_key,
                updated_at = :updated_at,
                completed_at = :completed_at
            WHERE id = :id AND checkpoint_sequence = :expected_sequence
            """
        ),
        {
            "id": task["id"],
            "criteria": _dump(task["acceptance_criteria"]),
            "steps": _dump(task["steps"]),
            "status": task["status"],
            "plan_version": task["plan_version"],
            "current_step_index": task["current_step_index"],
            "stall_count": task["stall_count"],
            "actions_used": task["actions_used"],
            "replan_reason": task["replan_reason"],
            "escalation_reason": task["escalation_reason"],
            "checkpoint_sequence": task["checkpoint"]["sequence"],
            "checkpoint_operation": task["checkpoint"]["operation"],
            "checkpoint_idempotency_key": task["checkpoint"]["idempotency_key"],
            "expected_sequence": expected_sequence,
            "updated_at": task["updated_at"],
            "completed_at": task["completed_at"],
        },
    )
    if update.rowcount != 1:
        await db.rollback()
        return False
    await db.execute(
        text(
            """
            INSERT INTO task_effect_journal (
                task_id, operation, idempotency_key, request_hash,
                response_json, created_at
            ) VALUES (
                :task_id, :operation, :idempotency_key, :request_hash,
                :response_json, :created_at
            )
            """
        ),
        {
            "task_id": task["id"],
            "operation": operation,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "response_json": _dump(task),
            "created_at": task["updated_at"],
        },
    )
    await db.commit()
    return True


async def advance_task(
    db: AsyncSession,
    task_id: str,
    command: AdvanceCommand,
) -> dict[str, Any]:
    return await _advance_task(db, task_id, command, ())


async def advance_verified_task(
    db: AsyncSession,
    task_id: str,
    command: AdvanceCommand,
    trusted_results: list[TrustedVerificationResult],
) -> dict[str, Any]:
    """Advance with proof produced by an in-process verifier adapter."""
    return await _advance_task(db, task_id, command, tuple(trusted_results))


async def _advance_task(
    db: AsyncSession,
    task_id: str,
    command: AdvanceCommand,
    trusted_results: tuple[TrustedVerificationResult, ...],
) -> dict[str, Any]:
    if trusted_results:
        command_hash = trusted_request_hash(command, trusted_results)
    else:
        command_hash = request_hash(command)
    for _ in range(5):
        task = await _fetch_task(db, task_id)
        cached = await _cached_effect(
            db,
            task_id,
            "advance",
            command.idempotency_key,
            command_hash,
        )
        if cached is not None:
            return cached
        if task["status"] != "active":
            raise InvalidTaskTransitionError(
                f"Cannot advance task with status {task['status']}"
            )

        candidate = deepcopy(task)
        now = _now()
        apply_evidence(
            candidate["acceptance_criteria"],
            command,
            now,
            trusted_results,
        )
        current_index = candidate["current_step_index"]
        is_final_step = current_index == len(candidate["steps"]) - 1

        if command.progress:
            if is_final_step:
                missing = missing_criteria(candidate["acceptance_criteria"])
                if missing:
                    raise EvidenceRequiredError(missing)
            candidate["steps"][current_index]["status"] = "completed"
            candidate["stall_count"] = 0
            if is_final_step:
                candidate["status"] = "completed"
                candidate["completed_at"] = now
            else:
                candidate["current_step_index"] += 1
                candidate["steps"][candidate["current_step_index"]]["status"] = "active"
        else:
            candidate["stall_count"] += 1
            if candidate["stall_count"] >= candidate["stall_threshold"]:
                candidate["stall_count"] = 0
                candidate["status"] = "replan_required"
                candidate["replan_reason"] = "stall_threshold_reached"

        candidate["actions_used"] += 1
        if (
            candidate["status"] in {"active", "replan_required"}
            and candidate["actions_used"] >= candidate["action_budget"]
        ):
            candidate["status"] = "escalated"
            candidate["escalation_reason"] = "action_budget_exhausted"
        candidate["updated_at"] = now
        set_checkpoint(candidate, "advance", command.idempotency_key, now)
        saved = await _save_task_and_effect(
            db,
            candidate,
            operation="advance",
            idempotency_key=command.idempotency_key,
            request_hash=command_hash,
            expected_sequence=task["checkpoint"]["sequence"],
        )
        if saved:
            return candidate
    raise ConcurrentMutationError


async def replan_task(
    db: AsyncSession,
    task_id: str,
    command: ReplanCommand,
) -> dict[str, Any]:
    command_hash = request_hash(command)
    for _ in range(5):
        task = await _fetch_task(db, task_id)
        cached = await _cached_effect(
            db,
            task_id,
            "replan",
            command.idempotency_key,
            command_hash,
        )
        if cached is not None:
            return cached
        if task["status"] not in {"active", "replan_required"}:
            raise InvalidTaskTransitionError(
                f"Cannot replan task with status {task['status']}"
            )

        completed_steps = [
            step
            for step in task["steps"][: task["current_step_index"]]
            if step["status"] == "completed"
        ]
        replacement_steps = [
            {
                "id": _uuid(),
                "title": step.title,
                "status": "active" if index == 0 else "pending",
            }
            for index, step in enumerate(command.steps)
        ]
        candidate = deepcopy(task)
        candidate["steps"] = completed_steps + replacement_steps
        candidate["current_step_index"] = len(completed_steps)
        candidate["plan_version"] += 1
        candidate["stall_count"] = 0
        candidate["replan_reason"] = command.reason
        candidate["status"] = "active"
        candidate["actions_used"] += 1
        if candidate["actions_used"] >= candidate["action_budget"]:
            candidate["status"] = "escalated"
            candidate["escalation_reason"] = "action_budget_exhausted"
        candidate["updated_at"] = _now()
        set_checkpoint(
            candidate,
            "replan",
            command.idempotency_key,
            candidate["updated_at"],
        )
        saved = await _save_task_and_effect(
            db,
            candidate,
            operation="replan",
            idempotency_key=command.idempotency_key,
            request_hash=command_hash,
            expected_sequence=task["checkpoint"]["sequence"],
        )
        if saved:
            return candidate
    raise ConcurrentMutationError


async def transition_task(
    db: AsyncSession,
    task_id: str,
    transition: str,
) -> dict[str, Any]:
    for _ in range(5):
        task = await _fetch_task(db, task_id)
        current = task["status"]
        if transition == "pause":
            if current == "paused":
                return task
            if current != "active":
                raise InvalidTaskTransitionError(
                    f"Cannot pause task with status {current}"
                )
            target = "paused"
        elif transition == "resume":
            if current != "paused":
                raise InvalidTaskTransitionError(
                    f"Cannot resume task with status {current}"
                )
            target = "active"
        elif transition == "cancel":
            if current == "cancelled":
                return task
            if current not in {"active", "paused", "replan_required"}:
                raise InvalidTaskTransitionError(
                    f"Cannot cancel task with status {current}"
                )
            target = "cancelled"
        else:
            raise ValueError(f"Unknown transition: {transition}")

        candidate = deepcopy(task)
        candidate["status"] = target
        candidate["updated_at"] = _now()
        set_checkpoint(candidate, transition, None, candidate["updated_at"])
        update = await db.execute(
            text(
                """
                UPDATE task_ledgers
                SET status = :status,
                    checkpoint_sequence = :checkpoint_sequence,
                    checkpoint_operation = :checkpoint_operation,
                    checkpoint_idempotency_key = NULL,
                    updated_at = :updated_at
                WHERE id = :task_id
                  AND checkpoint_sequence = :expected_sequence
                """
            ),
            {
                "task_id": task_id,
                "status": target,
                "checkpoint_sequence": candidate["checkpoint"]["sequence"],
                "checkpoint_operation": transition,
                "expected_sequence": task["checkpoint"]["sequence"],
                "updated_at": candidate["updated_at"],
            },
        )
        if update.rowcount == 1:
            await db.commit()
            return candidate
        await db.rollback()
    raise ConcurrentMutationError


async def list_effects(
    db: AsyncSession,
    task_id: str,
) -> list[dict[str, Any]]:
    await _fetch_task(db, task_id)
    result = await db.execute(
        text(
            """
            SELECT idempotency_key, operation, created_at
            FROM task_effect_journal
            WHERE task_id = :task_id
            ORDER BY created_at
            """
        ),
        {"task_id": task_id},
    )
    return [dict(row._mapping) for row in result.fetchall()]
