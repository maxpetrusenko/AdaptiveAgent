import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.knowledge.api import KnowledgeIndexManager, create_knowledge_router
from app.knowledge.embeddings import DeterministicTestEmbedder
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.persistence import KnowledgeRepository
from app.knowledge.retrieval import ExactHybridRetriever


async def api_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    repository = KnowledgeRepository(sessions)
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )
    app = FastAPI()
    app.include_router(create_knowledge_router(manager, repository))
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    return client, engine


@pytest.mark.asyncio
async def test_typed_ingest_search_health_and_idempotent_contract(tmp_path):
    client, engine = await api_client(tmp_path)
    async with client:
        first = await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-a",
                "external_id": "handbook",
                "text": "Database migration requires a verified backup.",
            },
        )
        replay = await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-a",
                "external_id": "handbook",
                "text": "Database migration requires a verified backup.",
            },
        )
        health = await client.get("/api/knowledge/index/health")
        search = await client.post(
            "/api/knowledge/search",
            json={
                "tenant_id": "tenant-a",
                "query": "database migration backup",
                "top_k": 3,
            },
        )

    assert first.status_code == 201
    assert first.json()["changed"] is True
    assert replay.status_code == 200
    assert replay.json()["changed"] is False
    assert health.json()["status"] == "ready"
    assert health.json()["chunk_count"] == 1
    assert search.status_code == 200
    assert search.json()["hits"][0]["tenant_id"] == "tenant-a"
    assert search.json()["hits"][0]["citation_id"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_enforces_tenant_isolation_and_text_bounds(tmp_path):
    client, engine = await api_client(tmp_path)
    async with client:
        await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-a",
                "external_id": "secret",
                "text": "Alpha-only acquisition secret.",
            },
        )
        await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-b",
                "external_id": "guide",
                "text": "Public deployment guide.",
            },
        )
        cross_tenant_only = await client.post(
            "/api/knowledge/search",
            json={
                "tenant_id": "tenant-b",
                "query": "Alpha-only acquisition secret",
                "top_k": 5,
            },
        )
        isolated = await client.post(
            "/api/knowledge/search",
            json={
                "tenant_id": "tenant-b",
                "query": "public deployment guide",
                "top_k": 5,
            },
        )
        oversized = await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-a",
                "external_id": "too-large",
                "text": "x" * 100_001,
            },
        )

    assert cross_tenant_only.status_code == 404
    assert cross_tenant_only.json()["detail"]["code"] == "no_evidence"
    assert isolated.status_code == 200
    assert isolated.json()["hits"]
    assert {hit["tenant_id"] for hit in isolated.json()["hits"]} == {"tenant-b"}
    assert oversized.status_code == 422
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_creates_new_index_and_missing_tenant_fails_closed(tmp_path):
    client, engine = await api_client(tmp_path)
    async with client:
        await client.post(
            "/api/knowledge/ingest",
            json={
                "tenant_id": "tenant-a",
                "external_id": "handbook",
                "text": "Database migration requires a verified backup.",
            },
        )
        deleted = await client.request(
            "DELETE",
            "/api/knowledge/sources",
            json={"tenant_id": "tenant-a", "external_id": "handbook"},
        )
        missing = await client.post(
            "/api/knowledge/search",
            json={
                "tenant_id": "tenant-a",
                "query": "database migration",
                "top_k": 3,
            },
        )

    assert deleted.status_code == 200
    assert deleted.json()["changed"] is True
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "no_evidence"
    await engine.dispose()


@pytest.mark.asyncio
async def test_operator_guard_protects_corpus_routes_but_not_health(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'guard.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    repository = KnowledgeRepository(sessions)
    manager = KnowledgeIndexManager(
        repository=repository,
        embedder=DeterministicTestEmbedder(dimensions=16),
        retriever=AsyncNativeRetrieverAdapter(ExactHybridRetriever()),
    )

    def reject():
        raise HTTPException(status_code=401, detail="operator required")

    app = FastAPI()
    app.include_router(
        create_knowledge_router(manager, repository, operator_guard=reject)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        health = await client.get("/api/knowledge/index/health")
        search = await client.post(
            "/api/knowledge/search",
            json={"tenant_id": "tenant-a", "query": "secret"},
        )

    assert health.status_code == 200
    assert search.status_code == 401
    await engine.dispose()
