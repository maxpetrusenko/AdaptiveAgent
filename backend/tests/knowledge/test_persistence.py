import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.api import KnowledgeIndexManager
from app.knowledge.embeddings import DeterministicTestEmbedder
from app.knowledge.lineage import stable_content_hash, stable_source_id
from app.knowledge.models import EmbeddingIdentity, IndexedChunk
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.persistence import KnowledgeRepository
from app.knowledge.retrieval import ExactHybridRetriever
from app.knowledge.service import NoEvidenceError


def repository_for(path: Path) -> tuple[KnowledgeRepository, object]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return KnowledgeRepository(sessions), engine


def indexed_chunk(*, tenant_id: str, external_id: str, text: str) -> IndexedChunk:
    source_id = stable_source_id(tenant_id=tenant_id, external_id=external_id)
    return IndexedChunk(
        tenant_id=tenant_id,
        source_id=source_id,
        chunk_id=f"{source_id}:{stable_content_hash(text)}",
        content_hash=stable_content_hash(text),
        text=text,
        embedding=(1.0, 0.0),
    )


@pytest.mark.asyncio
async def test_ingest_is_idempotent_and_update_replaces_source_in_new_active_generation(
    tmp_path,
):
    repository, engine = repository_for(tmp_path / "knowledge.db")
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
        chunk_size_chars=200,
    )

    first = await manager.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Database migration requires a verified backup.",
    )
    replay = await manager.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Database migration requires a verified backup.",
    )
    updated = await manager.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Database migration requires a rollback plan.",
    )
    snapshot = await repository.get_active_snapshot()

    assert first.changed is True
    assert replay.changed is False
    assert replay.generation_id == first.generation_id
    assert updated.changed is True
    assert updated.generation_id != first.generation_id
    assert snapshot is not None
    source_chunks = [chunk for chunk in snapshot.chunks if chunk.source_id == first.source_id]
    assert len(source_chunks) == 1
    assert source_chunks[0].text.endswith("rollback plan.")
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_preparations_compose_and_older_activation_cannot_lose_update(
    tmp_path,
):
    repository, engine = repository_for(tmp_path / "concurrent.db")
    first_chunk = indexed_chunk(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Back up the database.",
    )
    second_chunk = indexed_chunk(
        tenant_id="tenant-a",
        external_id="runbook",
        text="Verify the restore.",
    )

    _first_result, first = await repository.prepare_ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        source_content_hash=stable_content_hash(first_chunk.text),
        embedding_fingerprint="embedding-v1",
        dimensions=2,
        chunks=[first_chunk],
    )
    _second_result, second = await repository.prepare_ingest(
        tenant_id="tenant-a",
        external_id="runbook",
        source_content_hash=stable_content_hash(second_chunk.text),
        embedding_fingerprint="embedding-v1",
        dimensions=2,
        chunks=[second_chunk],
    )

    assert {chunk.source_id for chunk in second.chunks} == {
        first_chunk.source_id,
        second_chunk.source_id,
    }

    await repository.activate(second.generation_id)
    await repository.activate(first.generation_id)
    active = await repository.get_active_snapshot()

    assert active is not None
    assert active.generation_id == second.generation_id
    assert {chunk.source_id for chunk in active.chunks} == {
        first_chunk.source_id,
        second_chunk.source_id,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_embedding_fingerprint_upgrade_drops_vectors_from_old_manifest(tmp_path):
    repository, engine = repository_for(tmp_path / "fingerprint-upgrade.db")
    retriever = AsyncNativeRetrieverAdapter(ExactHybridRetriever())
    first = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16, revision="v1"),
        retriever=retriever,
    )
    upgraded_embedder = DeterministicTestEmbedder(dimensions=16, revision="v2")
    upgraded = KnowledgeIndexManager(
        repository=repository,
        embedder=upgraded_embedder,
        retriever=retriever,
    )
    await first.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Back up the database.",
    )

    result = await upgraded.ingest(
        tenant_id="tenant-a",
        external_id="runbook",
        text="Verify the restore.",
    )
    active = await repository.get_active_snapshot()

    assert active is not None
    assert active.manifest.embedding_fingerprint == upgraded_embedder.identity.fingerprint
    assert result.chunk_count == 1
    assert [chunk.source_id for chunk in active.chunks] == [
        stable_source_id(tenant_id="tenant-a", external_id="runbook")
    ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_reindexes_without_source_and_search_fails_closed(tmp_path):
    repository, engine = repository_for(tmp_path / "delete.db")
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )
    ingested = await manager.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Database migration requires a verified backup.",
    )

    deleted = await manager.delete_source(
        tenant_id="tenant-a",
        external_id="handbook",
    )

    assert deleted.changed is True
    assert deleted.source_id == ingested.source_id
    with pytest.raises(NoEvidenceError):
        await manager.search(
            tenant_id="tenant-a",
            query_text="database migration",
            top_k=3,
        )
    await engine.dispose()


class FailingNativeRetriever:
    def replace_index(self, manifest, chunks) -> None:
        raise RuntimeError("native build failed")

    def search(self, request):
        return []


class SerializingReplacementAdapter:
    def __init__(self) -> None:
        self.first_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.second_started = asyncio.Event()
        self.manifest = None
        self.chunks = []
        self.replace_count = 0

    async def replace_index(self, manifest, chunks) -> None:
        self.replace_count += 1
        if self.replace_count == 1:
            self.first_started.set()
            await self.release_first.wait()
        else:
            self.second_started.set()
        self.manifest = manifest
        self.chunks = list(chunks)


class BlockingReplacementAdapter:
    def __init__(self) -> None:
        self._native = ExactHybridRetriever()
        self.replace_count = 0
        self.replacement_visible = asyncio.Event()
        self.release_replacement = asyncio.Event()

    async def replace_index(self, manifest, chunks) -> None:
        self.replace_count += 1
        self._native.replace_index(manifest, chunks)
        if self.replace_count == 2:
            self.replacement_visible.set()
            await self.release_replacement.wait()

    async def search(self, request):
        return self._native.search(request)


class PauseFirstBuilding:
    def __init__(self) -> None:
        self.calls = 0
        self.first_read_complete = asyncio.Event()
        self.release_first = asyncio.Event()


class PausingKnowledgeRepository(KnowledgeRepository):
    def __init__(self, sessions, pause: PauseFirstBuilding) -> None:
        super().__init__(sessions)
        self._pause = pause

    async def _create_building(self, db, **kwargs):
        self._pause.calls += 1
        if self._pause.calls == 1:
            self._pause.first_read_complete.set()
            await self._pause.release_first.wait()
        return await super()._create_building(db, **kwargs)


class WrongDimensionEmbedder:
    identity = EmbeddingIdentity(
        provider="broken-test",
        model="wrong-dimension",
        dimensions=2,
    )

    async def embed(self, texts):
        return [[1.0] for _text in texts]


@pytest.mark.asyncio
async def test_building_generation_is_recoverable_after_native_failure(tmp_path):
    repository, engine = repository_for(tmp_path / "recover.db")
    embedder = DeterministicTestEmbedder(dimensions=16)
    failing = KnowledgeIndexManager(
        repository=repository,
        embedder=embedder,
        retriever=AsyncNativeRetrieverAdapter(FailingNativeRetriever()),
    )

    with pytest.raises(RuntimeError, match="native build failed"):
        await failing.ingest(
            tenant_id="tenant-a",
            external_id="handbook",
            text="Database migration requires a verified backup.",
        )

    health = await repository.health()
    assert health.active_generation_id is None
    assert health.building_count == 1

    recovered = KnowledgeIndexManager(
        repository=repository,
        embedder=embedder,
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )
    recovered_ids = await recovered.recover_building()
    active = await repository.get_active_snapshot()

    assert recovered_ids
    assert active is not None
    assert active.generation_id == recovered_ids[0]
    assert (await repository.health()).building_count == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_shared_native_mutations_are_serialized_on_canonical_active_generation(
    tmp_path,
):
    repository, engine = repository_for(tmp_path / "serialized-replacement.db")
    retriever = SerializingReplacementAdapter()
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16),
        retriever=retriever,
    )

    first = asyncio.create_task(
        manager.ingest(
            tenant_id="tenant-a",
            external_id="handbook",
            text="Back up the database.",
        )
    )
    await retriever.first_started.wait()
    second = asyncio.create_task(
        manager.ingest(
            tenant_id="tenant-a",
            external_id="runbook",
            text="Verify the restore.",
        )
    )
    await asyncio.sleep(0)
    assert not retriever.second_started.is_set()

    retriever.release_first.set()
    await asyncio.gather(first, second)
    active = await repository.get_active_snapshot()

    assert active is not None
    assert retriever.manifest == active.manifest
    assert {chunk.source_id for chunk in retriever.chunks} == {
        chunk.source_id for chunk in active.chunks
    }
    assert retriever.replace_count == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_never_observes_unactivated_shared_retriever_generation(tmp_path):
    repository, engine = repository_for(tmp_path / "active-isolation.db")
    retriever = BlockingReplacementAdapter()
    embedder = DeterministicTestEmbedder(dimensions=16)
    writer = KnowledgeIndexManager(
        repository=repository,
        embedder=embedder,
        retriever=retriever,
    )
    reader = KnowledgeIndexManager(
        repository=repository,
        embedder=embedder,
        retriever=retriever,
    )
    await writer.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Back up the database.",
    )

    replacement = asyncio.create_task(
        writer.ingest(
            tenant_id="tenant-a",
            external_id="runbook",
            text="Verify the restore.",
        )
    )
    await retriever.replacement_visible.wait()
    search = asyncio.create_task(
        reader.search(
            tenant_id="tenant-a",
            query_text="verify restore",
            top_k=3,
        )
    )
    await asyncio.sleep(0)

    assert not search.done()

    retriever.release_replacement.set()
    await replacement
    hits = await search
    active = await repository.get_active_snapshot()

    assert active is not None
    assert hits[0].index_version == active.manifest.index_version
    assert hits[0].text == "Verify the restore."
    await engine.dispose()


@pytest.mark.asyncio
async def test_simultaneous_repository_ingests_compose_under_sqlite_write_lock(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'simultaneous.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    pause = PauseFirstBuilding()
    first_repository = PausingKnowledgeRepository(sessions, pause)
    second_repository = PausingKnowledgeRepository(sessions, pause)
    first_chunk = indexed_chunk(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Back up the database.",
    )
    second_chunk = indexed_chunk(
        tenant_id="tenant-a",
        external_id="runbook",
        text="Verify the restore.",
    )

    first_task = asyncio.create_task(
        first_repository.prepare_ingest(
            tenant_id="tenant-a",
            external_id="handbook",
            source_content_hash=stable_content_hash(first_chunk.text),
            embedding_fingerprint="embedding-v1",
            dimensions=2,
            chunks=[first_chunk],
        )
    )
    await pause.first_read_complete.wait()
    second_task = asyncio.create_task(
        second_repository.prepare_ingest(
            tenant_id="tenant-a",
            external_id="runbook",
            source_content_hash=stable_content_hash(second_chunk.text),
            embedding_fingerprint="embedding-v1",
            dimensions=2,
            chunks=[second_chunk],
        )
    )
    asyncio.get_running_loop().call_later(0.05, pause.release_first.set)
    (_first_result, first), (_second_result, second) = await asyncio.gather(
        first_task,
        second_task,
    )
    await second_repository.activate(second.generation_id)
    await first_repository.activate(first.generation_id)
    active = await first_repository.get_active_snapshot()

    assert active is not None
    assert {chunk.source_id for chunk in active.chunks} == {
        first_chunk.source_id,
        second_chunk.source_id,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_simultaneous_ingest_then_delete_compose_from_latest_mutation(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'simultaneous-delete.db'}"
    )
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    repository = KnowledgeRepository(sessions)
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=2),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )
    await manager.ingest(
        tenant_id="tenant-a",
        external_id="handbook",
        text="Back up the database.",
    )
    await manager.ingest(
        tenant_id="tenant-a",
        external_id="runbook",
        text="Verify the restore.",
    )
    active_before = await repository.get_active_snapshot()
    assert active_before is not None

    pause = PauseFirstBuilding()
    ingest_repository = PausingKnowledgeRepository(sessions, pause)
    delete_repository = PausingKnowledgeRepository(sessions, pause)
    new_chunk = indexed_chunk(
        tenant_id="tenant-a",
        external_id="alerts",
        text="Page the operator.",
    )
    ingest_task = asyncio.create_task(
        ingest_repository.prepare_ingest(
            tenant_id="tenant-a",
            external_id="alerts",
            source_content_hash=stable_content_hash(new_chunk.text),
            embedding_fingerprint=active_before.manifest.embedding_fingerprint,
            dimensions=active_before.manifest.dimensions,
            chunks=[new_chunk],
        )
    )
    await pause.first_read_complete.wait()
    delete_task = asyncio.create_task(
        delete_repository.prepare_delete(
            tenant_id="tenant-a",
            external_id="handbook",
        )
    )
    asyncio.get_running_loop().call_later(0.05, pause.release_first.set)
    (_ingest_result, ingest), (_delete_result, delete) = await asyncio.gather(
        ingest_task,
        delete_task,
    )
    await delete_repository.activate(delete.generation_id)
    await ingest_repository.activate(ingest.generation_id)
    active = await repository.get_active_snapshot()

    assert active is not None
    assert {chunk.source_id for chunk in active.chunks} == {
        stable_source_id(tenant_id="tenant-a", external_id="runbook"),
        new_chunk.source_id,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_embedding_batch_is_rejected_before_a_generation_is_created(
    tmp_path,
):
    repository, engine = repository_for(tmp_path / "invalid-embedding.db")
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=WrongDimensionEmbedder(),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )

    with pytest.raises(ValueError, match="dimension"):
        await manager.ingest(
            tenant_id="tenant-a",
            external_id="handbook",
            text="Database migration requires a backup.",
        )

    assert (await repository.health()).building_count == 0
    await engine.dispose()
