# syntax=docker/dockerfile:1.7

FROM rust:1.97.1-slim-bookworm AS rust-toolchain


FROM python:3.11-slim-bookworm AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /usr/local/bin/
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        python3-dev \
    && apt-get clean

ENV CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH \
    RUSTUP_HOME=/usr/local/rustup \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app/backend

COPY native/adaptive_retrieval /app/native/adaptive_retrieval
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app ./app

RUN uv sync --frozen --no-dev


FROM python:3.11-slim-bookworm AS backend-runtime

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && apt-get clean \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/backend /data/sqlite /data/index \
    && chown -R app:app /app /data

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/sqlite/adaptive_agent.db \
    RESEARCH_DATABASE_PATH=/data/sqlite/research.db \
    KNOWLEDGE_INDEX_PATH=/data/index

WORKDIR /app/backend

COPY --from=backend-builder --chown=app:app /opt/venv /opt/venv
COPY --from=backend-builder --chown=app:app /app/backend/app ./app

USER 10001:10001

EXPOSE 8000
VOLUME ["/data/sqlite", "/data/index"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]


FROM node:22-bookworm-slim AS frontend-deps

RUN npm install --global pnpm@10.27.0

WORKDIR /app/frontend

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./

RUN pnpm install --frozen-lockfile


FROM node:22-bookworm-slim AS frontend-builder

RUN npm install --global pnpm@10.27.0

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app/frontend

COPY --from=frontend-deps /app/frontend/node_modules ./node_modules
COPY frontend ./

RUN pnpm build \
    && pnpm prune --prod


FROM node:22-bookworm-slim AS frontend-runtime

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && apt-get clean \
    && npm install --global pnpm@10.27.0 \
    && mkdir -p /app/frontend \
    && chown -R node:node /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_URL=http://localhost:8000

WORKDIR /app/frontend

COPY --from=frontend-builder --chown=node:node /app/frontend/.next ./.next
COPY --from=frontend-builder --chown=node:node /app/frontend/node_modules ./node_modules
COPY --from=frontend-builder --chown=node:node /app/frontend/package.json ./package.json
COPY --from=frontend-builder --chown=node:node /app/frontend/public ./public

USER node

EXPOSE 3737

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD curl --fail --silent --show-error http://127.0.0.1:3737/ >/dev/null || exit 1

CMD ["pnpm", "start", "--port", "3737"]
