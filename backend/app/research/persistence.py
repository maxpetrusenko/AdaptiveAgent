"""Tenant-scoped SQLite persistence for research runs, effects, and leases."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from app.research.ports import LeaseFenceRejectedError, LeaseGrant
from app.research.types import (
    DEFAULT_ADAPTER_FINGERPRINTS,
    PlanArtifact,
    ResearchArtifacts,
    ResearchRun,
    ResearchStep,
    RetrievedChunk,
    SynthesisArtifact,
    VerificationResult,
)


class ResearchRunExistsError(RuntimeError):
    pass


class SqliteResearchRepository:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        self._ensure_schema()

    def for_tenant(self, tenant_id: str) -> TenantResearchRepository:
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        return TenantResearchRepository(self.database_path, tenant_id)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_runs (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS research_effects (
                    tenant_id TEXT NOT NULL,
                    effect_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (tenant_id, effect_key)
                );
                CREATE TABLE IF NOT EXISTS research_leases (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    fence_token INTEGER NOT NULL DEFAULT 1,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (tenant_id, run_id)
                );
                """
            )
            lease_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(research_leases)"
                ).fetchall()
            }
            if "fence_token" not in lease_columns:
                connection.execute(
                    "ALTER TABLE research_leases "
                    "ADD COLUMN fence_token INTEGER NOT NULL DEFAULT 1"
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


class TenantResearchRepository:
    """One tenant-bound object implements all three runner persistence ports."""

    def __init__(self, database_path: str, tenant_id: str):
        self.database_path = database_path
        self.tenant_id = tenant_id

    def create(self, run: ResearchRun) -> ResearchRun:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO research_runs (
                        tenant_id, run_id, version, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        self.tenant_id,
                        run.id,
                        run.version,
                        _encode_run(run),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ResearchRunExistsError(
                f"Run {run.id} already exists for tenant {self.tenant_id}"
            ) from error
        return self.load(run.id)

    def load(self, run_id: str) -> ResearchRun:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM research_runs
                WHERE tenant_id = ? AND run_id = ?
                """,
                (self.tenant_id, run_id),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return _decode_run(row["payload_json"])

    def compare_and_set(
        self,
        run: ResearchRun,
        *,
        expected_version: int,
        lease: LeaseGrant | None = None,
    ) -> bool:
        stored = replace(run, version=expected_version + 1)
        with self._connect() as connection:
            if lease is not None:
                connection.execute("BEGIN IMMEDIATE")
                self._assert_current_lease(connection, lease)
            cursor = connection.execute(
                """
                UPDATE research_runs
                SET version = ?, payload_json = ?
                WHERE tenant_id = ? AND run_id = ? AND version = ?
                """,
                (
                    stored.version,
                    _encode_run(stored),
                    self.tenant_id,
                    run.id,
                    expected_version,
                ),
            )
            if lease is not None:
                connection.commit()
        return cursor.rowcount == 1

    def get(self, key: str) -> Any | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM research_effects
                WHERE tenant_id = ? AND effect_key = ?
                """,
                (self.tenant_id, key),
            ).fetchone()
        return None if row is None else _decode_effect(row["payload_json"])

    def seal(
        self,
        key: str,
        value: Any,
        *,
        lease: LeaseGrant | None = None,
    ) -> Any:
        with self._connect() as connection:
            if lease is not None:
                connection.execute("BEGIN IMMEDIATE")
                self._assert_current_lease(connection, lease)
            connection.execute(
                """
                INSERT OR IGNORE INTO research_effects (
                    tenant_id, effect_key, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    self.tenant_id,
                    key,
                    _encode_effect(value),
                    time.time(),
                ),
            )
            row = connection.execute(
                """
                SELECT payload_json
                FROM research_effects
                WHERE tenant_id = ? AND effect_key = ?
                """,
                (self.tenant_id, key),
            ).fetchone()
            if lease is not None:
                connection.commit()
        if row is None:
            raise RuntimeError("Sealed effect could not be loaded")
        return _decode_effect(row["payload_json"])

    def count_effects(self, *, step: str | None = None) -> int:
        query = "SELECT COUNT(*) AS count FROM research_effects WHERE tenant_id = ?"
        parameters: list[Any] = [self.tenant_id]
        if step is not None:
            query += " AND effect_key LIKE ?"
            parameters.append(f"%:{step}:%")
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return int(row["count"])

    def acquire(
        self,
        run_id: str,
        worker_id: str,
        *,
        ttl_seconds: float,
    ) -> LeaseGrant | None:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT worker_id, fence_token, expires_at
                FROM research_leases
                WHERE tenant_id = ? AND run_id = ?
                """,
                (self.tenant_id, run_id),
            ).fetchone()
            if (
                row is not None
                and row["worker_id"] != worker_id
                and float(row["expires_at"]) > now
            ):
                connection.rollback()
                return None
            if row is None:
                fence_token = 1
            elif row["worker_id"] == worker_id and float(row["expires_at"]) > now:
                fence_token = int(row["fence_token"])
            else:
                fence_token = int(row["fence_token"]) + 1
            connection.execute(
                """
                INSERT INTO research_leases (
                    tenant_id, run_id, worker_id, fence_token, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, run_id) DO UPDATE SET
                    worker_id = excluded.worker_id,
                    fence_token = excluded.fence_token,
                    expires_at = excluded.expires_at
                """,
                (
                    self.tenant_id,
                    run_id,
                    worker_id,
                    fence_token,
                    now + ttl_seconds,
                ),
            )
            connection.commit()
        return LeaseGrant(
            run_id=run_id,
            worker_id=worker_id,
            fence_token=fence_token,
        )

    def renew(
        self,
        lease: LeaseGrant,
        *,
        ttl_seconds: float,
    ) -> bool:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE research_leases
                SET expires_at = ?
                WHERE tenant_id = ? AND run_id = ? AND worker_id = ?
                  AND fence_token = ?
                  AND expires_at > ?
                """,
                (
                    now + ttl_seconds,
                    self.tenant_id,
                    lease.run_id,
                    lease.worker_id,
                    lease.fence_token,
                    now,
                ),
            )
        return cursor.rowcount == 1

    def is_current(self, lease: LeaseGrant) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM research_leases
                WHERE tenant_id = ? AND run_id = ? AND worker_id = ?
                  AND fence_token = ? AND expires_at > ?
                """,
                (
                    self.tenant_id,
                    lease.run_id,
                    lease.worker_id,
                    lease.fence_token,
                    time.time(),
                ),
            ).fetchone()
        return row is not None

    def release(self, lease: LeaseGrant) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE research_leases
                SET expires_at = 0
                WHERE tenant_id = ? AND run_id = ? AND worker_id = ?
                  AND fence_token = ?
                """,
                (
                    self.tenant_id,
                    lease.run_id,
                    lease.worker_id,
                    lease.fence_token,
                ),
            )

    def _assert_current_lease(
        self,
        connection: sqlite3.Connection,
        lease: LeaseGrant,
    ) -> None:
        row = connection.execute(
            """
            SELECT 1
            FROM research_leases
            WHERE tenant_id = ? AND run_id = ? AND worker_id = ?
              AND fence_token = ? AND expires_at > ?
            """,
            (
                self.tenant_id,
                lease.run_id,
                lease.worker_id,
                lease.fence_token,
                time.time(),
            ),
        ).fetchone()
        if row is None:
            raise LeaseFenceRejectedError(
                f"Lease fence rejected token {lease.fence_token}"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


def _encode_run(run: ResearchRun) -> str:
    return json.dumps(asdict(run), separators=(",", ":"), sort_keys=True)


def _decode_run(payload: str) -> ResearchRun:
    data = json.loads(payload)
    artifact_data = data["artifacts"]
    plan_data = artifact_data["plan"]
    synthesis_data = artifact_data["synthesis"]
    verification_data = artifact_data["verification"]
    artifacts = ResearchArtifacts(
        plan=(
            None
            if plan_data is None
            else PlanArtifact(queries=tuple(plan_data["queries"]))
        ),
        retrieval=tuple(
            RetrievedChunk(**chunk) for chunk in artifact_data["retrieval"]
        ),
        synthesis=(
            None
            if synthesis_data is None
            else SynthesisArtifact(
                answer=synthesis_data["answer"],
                citation_ids=tuple(synthesis_data["citation_ids"]),
            )
        ),
        verification=(
            None
            if verification_data is None
            else VerificationResult(
                passed=verification_data["passed"],
                evidence_citation_ids=tuple(
                    verification_data["evidence_citation_ids"]
                ),
                reason=verification_data["reason"],
            )
        ),
    )
    return ResearchRun(
        id=data["id"],
        goal=data["goal"],
        execution_mode=data.get("execution_mode", "deterministic"),
        adapter_fingerprint=data.get(
            "adapter_fingerprint",
            DEFAULT_ADAPTER_FINGERPRINTS["deterministic"],
        ),
        steps=tuple(ResearchStep(**step) for step in data["steps"]),
        status=data["status"],
        cursor=data["cursor"],
        version=data["version"],
        plan_version=data["plan_version"],
        action_budget=data["action_budget"],
        actions_used=data["actions_used"],
        artifacts=artifacts,
        terminal_reason=data["terminal_reason"],
    )


def _encode_effect(value: Any) -> str:
    if isinstance(value, PlanArtifact):
        payload = {"type": "plan", "value": asdict(value)}
    elif isinstance(value, tuple) and all(
        isinstance(item, RetrievedChunk) for item in value
    ):
        payload = {
            "type": "retrieval",
            "value": [asdict(item) for item in value],
        }
    elif isinstance(value, SynthesisArtifact):
        payload = {"type": "synthesis", "value": asdict(value)}
    elif isinstance(value, VerificationResult):
        payload = {"type": "verification", "value": asdict(value)}
    else:
        raise TypeError(f"Unsupported research effect: {type(value).__name__}")
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _decode_effect(payload: str) -> Any:
    data = json.loads(payload)
    value = data["value"]
    if data["type"] == "plan":
        return PlanArtifact(queries=tuple(value["queries"]))
    if data["type"] == "retrieval":
        return tuple(RetrievedChunk(**chunk) for chunk in value)
    if data["type"] == "synthesis":
        return SynthesisArtifact(
            answer=value["answer"],
            citation_ids=tuple(value["citation_ids"]),
        )
    if data["type"] == "verification":
        return VerificationResult(
            passed=value["passed"],
            evidence_citation_ids=tuple(value["evidence_citation_ids"]),
            reason=value["reason"],
        )
    raise ValueError(f"Unknown research effect type: {data['type']}")
