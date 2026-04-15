from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.adapt import router as adapt_router
from app.api.cases import router as cases_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.evals import router as evals_router
from app.config import settings
from app.database import async_session, init_db
from app.seed import ensure_seed_eval_case_tags, seed_eval_cases, seed_prompt_v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Seed data
    async with async_session() as db:
        await seed_prompt_v1(db)
        await seed_eval_cases(db)
        await ensure_seed_eval_case_tags(db)
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
