"""SQLite-backed, recoverable knowledge-index generation orchestration."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.knowledge.lineage import stable_source_id
from app.knowledge.models import IndexedChunk, IndexManifest
from app.knowledge.service import NoEvidenceError


@dataclass(frozen=True)
class GenerationSnapshot:
    generation_id: str
    status: str
    manifest: IndexManifest
    chunks: tuple[IndexedChunk, ...]
    source_content_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class IndexMutationResult:
    generation_id: str
    source_id: str
    index_version: str
    changed: bool
    chunk_count: int


@dataclass(frozen=True)
class IndexHealth:
    status: str
    active_generation_id: str | None
    active_index_version: str | None
    building_count: int
    chunk_count: int


class KnowledgeRepository:
    """Generation snapshots keep incomplete native builds invisible to readers."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_active_snapshot(self) -> GenerationSnapshot | None:
        async with self._sessions() as db:
            await self._ensure_schema(db)
            return await self._active_snapshot(db)

    async def prepare_ingest(
        self,
        *,
        tenant_id: str,
        external_id: str,
        source_content_hash: str,
        embedding_fingerprint: str,
        dimensions: int,
        chunks: list[IndexedChunk],
    ) -> tuple[IndexMutationResult, GenerationSnapshot]:
        source_id = stable_source_id(tenant_id=tenant_id, external_id=external_id)
        operation_key = self._operation_key(
            "ingest",
            tenant_id,
            source_id,
            source_content_hash,
            embedding_fingerprint,
        )
        async with self._sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            await self._ensure_schema(db)
            active = await self._active_snapshot(db)
            if active and await self._active_source_matches(
                db,
                active.generation_id,
                source_id,
                source_content_hash,
                embedding_fingerprint,
                dimensions,
            ):
                return (
                    self._result(active, source_id=source_id, changed=False),
                    active,
                )

            existing = await self._snapshot_for_operation(db, operation_key)
            if existing is not None:
                return (
                    self._result(existing, source_id=source_id, changed=True),
                    existing,
                )

            # Include earlier prepared mutations so overlapping ingests form a
            # generation chain instead of branching from the same active snapshot.
            base = await self._latest_mutation_snapshot(
                db,
                embedding_fingerprint=embedding_fingerprint,
                dimensions=dimensions,
            )
            retained = (
                [chunk for chunk in base.chunks if chunk.source_id != source_id]
                if base
                else []
            )
            source_hashes = dict(base.source_content_hashes) if base else {}
            snapshot = await self._create_building(
                db,
                operation_key=operation_key,
                embedding_fingerprint=embedding_fingerprint,
                dimensions=dimensions,
                rows=[(chunk, source_hashes[chunk.source_id]) for chunk in retained]
                + [(chunk, source_content_hash) for chunk in chunks],
            )
            await db.commit()
            return self._result(snapshot, source_id=source_id, changed=True), snapshot

    async def prepare_delete(
        self,
        *,
        tenant_id: str,
        external_id: str,
    ) -> tuple[IndexMutationResult, GenerationSnapshot]:
        source_id = stable_source_id(tenant_id=tenant_id, external_id=external_id)
        async with self._sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            await self._ensure_schema(db)
            active = await self._active_snapshot(db)
            base = await self._latest_mutation_snapshot(db)
            if active is None or base is None:
                raise NoEvidenceError("knowledge index is empty")
            retained = [chunk for chunk in base.chunks if chunk.source_id != source_id]
            if len(retained) == len(base.chunks):
                changed = any(chunk.source_id == source_id for chunk in active.chunks)
                return self._result(base, source_id=source_id, changed=changed), base

            operation_key = self._operation_key(
                "delete",
                tenant_id,
                source_id,
                base.generation_id,
                base.manifest.embedding_fingerprint,
            )
            existing = await self._snapshot_for_operation(db, operation_key)
            if existing is not None:
                return self._result(existing, source_id=source_id, changed=True), existing

            source_hashes = dict(base.source_content_hashes)
            snapshot = await self._create_building(
                db,
                operation_key=operation_key,
                embedding_fingerprint=base.manifest.embedding_fingerprint,
                dimensions=base.manifest.dimensions,
                rows=[(chunk, source_hashes[chunk.source_id]) for chunk in retained],
            )
            await db.commit()
            return self._result(snapshot, source_id=source_id, changed=True), snapshot

    async def activate(self, generation_id: str) -> None:
        async with self._sessions() as db:
            await db.execute(text("BEGIN IMMEDIATE"))
            await self._ensure_schema(db)
            result = await db.execute(
                text(
                    "SELECT status, rowid AS sequence FROM knowledge_generations "
                    "WHERE generation_id = :generation_id"
                ),
                {"generation_id": generation_id},
            )
            row = result.first()
            if row is None:
                raise LookupError("knowledge generation not found")
            if row._mapping["status"] == "active":
                return
            if row._mapping["status"] == "superseded":
                return
            if row._mapping["status"] != "building":
                raise ValueError("only a building generation can be activated")
            sequence = int(row._mapping["sequence"])
            newer_active = await db.execute(
                text(
                    "SELECT 1 FROM knowledge_generations "
                    "WHERE status = 'active' AND rowid > :sequence LIMIT 1"
                ),
                {"sequence": sequence},
            )
            if newer_active.first() is not None:
                await db.execute(
                    text(
                        "UPDATE knowledge_generations SET status = 'superseded' "
                        "WHERE generation_id = :generation_id AND status = 'building'"
                    ),
                    {"generation_id": generation_id},
                )
                await db.commit()
                return
            await db.execute(
                text(
                    "UPDATE knowledge_generations SET status = 'superseded' "
                    "WHERE status = 'active' OR "
                    "(status = 'building' AND rowid < :sequence)"
                ),
                {"sequence": sequence},
            )
            updated = await db.execute(
                text(
                    "UPDATE knowledge_generations "
                    "SET status = 'active', activated_at = :activated_at "
                    "WHERE generation_id = :generation_id AND status = 'building'"
                ),
                {
                    "generation_id": generation_id,
                    "activated_at": self._now(),
                },
            )
            if updated.rowcount != 1:
                await db.rollback()
                raise RuntimeError("knowledge generation activation race")
            await db.commit()

    async def list_building(self) -> list[GenerationSnapshot]:
        async with self._sessions() as db:
            await self._ensure_schema(db)
            rows = await db.execute(
                text(
                    "SELECT generation_id FROM knowledge_generations "
                    "WHERE status = 'building' ORDER BY rowid"
                )
            )
            snapshots = []
            for row in rows.fetchall():
                snapshot = await self._snapshot(db, row._mapping["generation_id"])
                if snapshot is not None:
                    snapshots.append(snapshot)
            return snapshots

    async def health(self) -> IndexHealth:
        async with self._sessions() as db:
            await self._ensure_schema(db)
            active = await self._active_snapshot(db)
            building = await db.execute(
                text(
                    "SELECT COUNT(*) AS count FROM knowledge_generations "
                    "WHERE status = 'building'"
                )
            )
            building_count = int(building.one()._mapping["count"])
            return IndexHealth(
                status="ready" if active else ("building" if building_count else "empty"),
                active_generation_id=active.generation_id if active else None,
                active_index_version=active.manifest.index_version if active else None,
                building_count=building_count,
                chunk_count=len(active.chunks) if active else 0,
            )

    async def _ensure_schema(self, db: AsyncSession) -> None:
        await db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS knowledge_generations ("
                "generation_id TEXT PRIMARY KEY, index_version TEXT NOT NULL UNIQUE, "
                "status TEXT NOT NULL, operation_key TEXT NOT NULL UNIQUE, "
                "embedding_fingerprint TEXT NOT NULL, dimensions INTEGER NOT NULL, "
                "created_at TEXT NOT NULL, activated_at TEXT)"
            )
        )
        await db.execute(
            text(
                "CREATE TABLE IF NOT EXISTS knowledge_generation_chunks ("
                "generation_id TEXT NOT NULL, tenant_id TEXT NOT NULL, "
                "source_id TEXT NOT NULL, source_content_hash TEXT NOT NULL, "
                "chunk_id TEXT NOT NULL, content_hash TEXT NOT NULL, "
                "text_content TEXT NOT NULL, embedding_json TEXT NOT NULL, "
                "PRIMARY KEY (generation_id, chunk_id))"
            )
        )

    async def _active_snapshot(self, db: AsyncSession) -> GenerationSnapshot | None:
        result = await db.execute(
            text(
                "SELECT generation_id FROM knowledge_generations "
                "WHERE status = 'active' ORDER BY activated_at DESC LIMIT 1"
            )
        )
        row = result.first()
        if row is None:
            return None
        return await self._snapshot(db, row._mapping["generation_id"])

    async def _latest_mutation_snapshot(
        self,
        db: AsyncSession,
        *,
        embedding_fingerprint: str | None = None,
        dimensions: int | None = None,
    ) -> GenerationSnapshot | None:
        if embedding_fingerprint is None:
            query = text(
                "SELECT generation_id FROM knowledge_generations "
                "WHERE status IN ('active', 'building') "
                "ORDER BY rowid DESC LIMIT 1"
            )
            params = {}
        else:
            query = text(
                "SELECT generation_id FROM knowledge_generations "
                "WHERE status IN ('active', 'building') "
                "AND embedding_fingerprint = :embedding_fingerprint "
                "AND dimensions = :dimensions "
                "ORDER BY rowid DESC LIMIT 1"
            )
            params = {
                "embedding_fingerprint": embedding_fingerprint,
                "dimensions": dimensions,
            }
        result = await db.execute(query, params)
        row = result.first()
        if row is None:
            return None
        return await self._snapshot(db, row._mapping["generation_id"])

    async def _snapshot(
        self,
        db: AsyncSession,
        generation_id: str,
    ) -> GenerationSnapshot | None:
        generation = await db.execute(
            text(
                "SELECT * FROM knowledge_generations "
                "WHERE generation_id = :generation_id"
            ),
            {"generation_id": generation_id},
        )
        row = generation.first()
        if row is None:
            return None
        data = row._mapping
        chunk_rows = await db.execute(
            text(
                "SELECT * FROM knowledge_generation_chunks "
                "WHERE generation_id = :generation_id ORDER BY chunk_id"
            ),
            {"generation_id": generation_id},
        )
        items = chunk_rows.fetchall()
        chunks = tuple(
            IndexedChunk(
                tenant_id=item._mapping["tenant_id"],
                source_id=item._mapping["source_id"],
                chunk_id=item._mapping["chunk_id"],
                content_hash=item._mapping["content_hash"],
                text=item._mapping["text_content"],
                embedding=tuple(json.loads(item._mapping["embedding_json"])),
            )
            for item in items
        )
        return GenerationSnapshot(
            generation_id=generation_id,
            status=data["status"],
            manifest=IndexManifest(
                index_version=data["index_version"],
                embedding_fingerprint=data["embedding_fingerprint"],
                dimensions=int(data["dimensions"]),
            ),
            chunks=chunks,
            source_content_hashes=tuple(
                sorted(
                    {
                        item._mapping["source_id"]: item._mapping["source_content_hash"]
                        for item in items
                    }.items()
                )
            ),
        )

    async def _snapshot_for_operation(
        self,
        db: AsyncSession,
        operation_key: str,
    ) -> GenerationSnapshot | None:
        result = await db.execute(
            text(
                "SELECT generation_id FROM knowledge_generations "
                "WHERE operation_key = :operation_key"
            ),
            {"operation_key": operation_key},
        )
        row = result.first()
        return (
            await self._snapshot(db, row._mapping["generation_id"])
            if row is not None
            else None
        )

    async def _active_source_matches(
        self,
        db: AsyncSession,
        generation_id: str,
        source_id: str,
        source_content_hash: str,
        embedding_fingerprint: str,
        dimensions: int,
    ) -> bool:
        result = await db.execute(
            text(
                "SELECT COUNT(*) AS count FROM knowledge_generation_chunks "
                "WHERE generation_id = :generation_id AND source_id = :source_id "
                "AND source_content_hash = :source_content_hash"
            ),
            {
                "generation_id": generation_id,
                "source_id": source_id,
                "source_content_hash": source_content_hash,
            },
        )
        count = int(result.one()._mapping["count"])
        active = await self._snapshot(db, generation_id)
        return bool(
            count
            and active
            and active.manifest.embedding_fingerprint == embedding_fingerprint
            and active.manifest.dimensions == dimensions
        )

    async def _create_building(
        self,
        db: AsyncSession,
        *,
        operation_key: str,
        embedding_fingerprint: str,
        dimensions: int,
        rows: list[tuple[IndexedChunk, str]],
    ) -> GenerationSnapshot:
        generation_id = str(uuid.uuid4())
        index_version = f"generation-{generation_id}"
        await db.execute(
            text(
                "INSERT INTO knowledge_generations (generation_id, index_version, "
                "status, operation_key, embedding_fingerprint, dimensions, created_at) "
                "VALUES (:generation_id, :index_version, 'building', :operation_key, "
                ":embedding_fingerprint, :dimensions, :created_at)"
            ),
            {
                "generation_id": generation_id,
                "index_version": index_version,
                "operation_key": operation_key,
                "embedding_fingerprint": embedding_fingerprint,
                "dimensions": dimensions,
                "created_at": self._now(),
            },
        )
        for chunk, source_hash in rows:
            await db.execute(
                text(
                    "INSERT INTO knowledge_generation_chunks (generation_id, tenant_id, "
                    "source_id, source_content_hash, chunk_id, content_hash, "
                    "text_content, embedding_json) VALUES (:generation_id, :tenant_id, "
                    ":source_id, :source_hash, :chunk_id, :content_hash, "
                    ":text_content, :embedding_json)"
                ),
                {
                    "generation_id": generation_id,
                    "tenant_id": chunk.tenant_id,
                    "source_id": chunk.source_id,
                    "source_hash": source_hash,
                    "chunk_id": chunk.chunk_id,
                    "content_hash": chunk.content_hash,
                    "text_content": chunk.text,
                    "embedding_json": json.dumps(chunk.embedding, separators=(",", ":")),
                },
            )
        snapshot = await self._snapshot(db, generation_id)
        if snapshot is None:
            raise RuntimeError("building generation was not persisted")
        return snapshot

    @staticmethod
    def _operation_key(*parts: str) -> str:
        return sha256("\0".join(parts).encode()).hexdigest()

    @staticmethod
    def _result(
        snapshot: GenerationSnapshot,
        *,
        source_id: str,
        changed: bool,
    ) -> IndexMutationResult:
        return IndexMutationResult(
            generation_id=snapshot.generation_id,
            source_id=source_id,
            index_version=snapshot.manifest.index_version,
            changed=changed,
            chunk_count=len(snapshot.chunks),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
