from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.adapt import router as adapt_router
from app.api.cases import router as cases_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.evals import router as evals_router
from app.api.operator_auth import require_operator
from app.api.tasks import router as tasks_router
from app.config import settings
from app.database import async_session, init_db
from app.knowledge.api import KnowledgeIndexManager, create_knowledge_router
from app.knowledge.embeddings import (
    DeterministicTestEmbedder,
    OpenAICompatibleEmbeddingProvider,
)
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.persistence import KnowledgeRepository
from app.knowledge.rust import RustHybridRetriever
from app.research.api import build_research_router
from app.research.live import LiveResearchAdapters
from app.research.persistence import SqliteResearchRepository
from app.seed import ensure_seed_eval_case_tags, seed_eval_cases, seed_prompt_v1


def _knowledge_embedder():
    if settings.knowledge_embedding_provider == "openai":
        return OpenAICompatibleEmbeddingProvider(
            base_url=settings.knowledge_embedding_base_url,
            api_key=settings.openai_api_key,
            model=settings.knowledge_embedding_model,
            dimensions=settings.knowledge_embedding_dimensions,
        )
    return DeterministicTestEmbedder(
        dimensions=settings.knowledge_embedding_dimensions,
    )


knowledge_repository = KnowledgeRepository(async_session)
knowledge_manager = KnowledgeIndexManager(
    repository=knowledge_repository,
    embedder=_knowledge_embedder(),
    retriever=AsyncNativeRetrieverAdapter(
        RustHybridRetriever(settings.knowledge_index_path)
    ),
)
research_repository = SqliteResearchRepository(settings.research_database_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed data
    async with async_session() as db:
        await seed_prompt_v1(db)
        await seed_eval_cases(db)
        await ensure_seed_eval_case_tags(db)
    await knowledge_manager.recover_building()
    await knowledge_manager.load_active()
    yield


app = FastAPI(
    title="Adaptive Agent API",
    description="Self-improving AI agent backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(evals_router)
app.include_router(cases_router)
app.include_router(adapt_router)
app.include_router(dashboard_router)
app.include_router(tasks_router)
app.include_router(
    create_knowledge_router(
        knowledge_manager,
        knowledge_repository,
        operator_guard=require_operator,
    ),
)
app.include_router(
    build_research_router(
        repository=research_repository,
        operator_guard=require_operator,
        live_adapters=LiveResearchAdapters(knowledge=knowledge_manager),
        proof_mode=settings.research_proof_mode,
    )
)


@app.get("/health")
async def health():
    index = await knowledge_repository.health()
    return {
        "status": "ok",
        "version": "0.1.0",
        "retrieval_backend": "rust-pyo3",
        "embedding_provider": settings.knowledge_embedding_provider,
        "knowledge_index": index.status,
    }
