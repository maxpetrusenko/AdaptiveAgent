import json
from hashlib import sha256
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def request_hash(command: Any) -> str:
    payload = command.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return sha256(encoded).hexdigest()


def set_checkpoint(
    task: dict[str, Any],
    operation: str,
    idempotency_key: str | None,
    updated_at: str,
) -> None:
    task["checkpoint"] = {
        "sequence": task["checkpoint"]["sequence"] + 1,
        "operation": operation,
        "idempotency_key": idempotency_key,
        "updated_at": updated_at,
    }


async def ensure_schema(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS task_ledgers (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                status TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                current_step_index INTEGER NOT NULL,
                stall_count INTEGER NOT NULL,
                stall_threshold INTEGER NOT NULL,
                action_budget INTEGER NOT NULL,
                actions_used INTEGER NOT NULL,
                replan_reason TEXT,
                escalation_reason TEXT,
                checkpoint_sequence INTEGER NOT NULL DEFAULT 1,
                checkpoint_operation TEXT NOT NULL DEFAULT 'create',
                checkpoint_idempotency_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS task_effect_journal (
                task_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL DEFAULT '',
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (task_id, operation, idempotency_key)
            )
            """
        )
    )
    await _ensure_legacy_columns(db)


async def _ensure_legacy_columns(db: AsyncSession) -> None:
    task_columns = {
        row._mapping["name"]
        for row in (
            await db.execute(text("PRAGMA table_info(task_ledgers)"))
        ).fetchall()
    }
    additions = {
        "checkpoint_sequence": "INTEGER NOT NULL DEFAULT 1",
        "checkpoint_operation": "TEXT NOT NULL DEFAULT 'create'",
        "checkpoint_idempotency_key": "TEXT",
    }
    for name, definition in additions.items():
        if name not in task_columns:
            await db.execute(
                text(f"ALTER TABLE task_ledgers ADD COLUMN {name} {definition}")
            )

    journal_columns = {
        row._mapping["name"]
        for row in (
            await db.execute(text("PRAGMA table_info(task_effect_journal)"))
        ).fetchall()
    }
    if "request_hash" not in journal_columns:
        await db.execute(
            text(
                "ALTER TABLE task_effect_journal "
                "ADD COLUMN request_hash TEXT NOT NULL DEFAULT ''"
            )
        )


def row_to_task(row: Any) -> dict[str, Any]:
    data = dict(row._mapping)
    return {
        "id": data["id"],
        "goal": data["goal"],
        "constraints": json.loads(data["constraints_json"]),
        "acceptance_criteria": json.loads(data["criteria_json"]),
        "steps": json.loads(data["steps_json"]),
        "status": data["status"],
        "plan_version": data["plan_version"],
        "current_step_index": data["current_step_index"],
        "stall_count": data["stall_count"],
        "stall_threshold": data["stall_threshold"],
        "action_budget": data["action_budget"],
        "actions_used": data["actions_used"],
        "replan_reason": data["replan_reason"],
        "escalation_reason": data["escalation_reason"],
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "completed_at": data["completed_at"],
        "checkpoint": {
            "sequence": data["checkpoint_sequence"],
            "operation": data["checkpoint_operation"],
            "idempotency_key": data["checkpoint_idempotency_key"],
            "updated_at": data["updated_at"],
        },
    }
