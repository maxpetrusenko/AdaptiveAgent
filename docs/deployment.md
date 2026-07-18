# Deployment

AdaptiveAgent ships one multi-stage `Dockerfile` with two runtime targets:

- `backend-runtime`: Rust 1.97.1 builds the PyO3 ABI3 retrieval extension, then
  FastAPI runs on Python 3.11.
- `frontend-runtime`: Node 22 builds and runs the Next.js application.

Both runtime images use non-root users, drop Linux capabilities, set a
no-new-privileges policy, use a read-only root filesystem in Compose, and expose
container health checks.

## Local stack

Requirements: Docker Engine with Compose v2.

```bash
export OPERATOR_API_TOKEN="$(openssl rand -hex 32)"
docker compose up --build --detach
./scripts/smoke-stack.sh
```

Open <http://localhost:3737>. The API is at <http://localhost:8000>.

Stop containers without deleting persisted state:

```bash
docker compose down
```

The `backend-sqlite` volume stores the application and research SQLite files.
The `retrieval-index` volume stores native index generations. Rebuilds and
container replacement preserve both volumes.

## Environment contract

Compose interpolation reads values from the shell or a local `.env` file.
`.env` files are excluded from Docker build contexts and must not be committed.
Production secrets belong in the deployment platform's secret store.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `MODEL_PROVIDER` | No | `anthropic` | `anthropic`, `openai`, `ollama`, or supported auto mode |
| `ANTHROPIC_API_KEY` | For Anthropic calls | empty | Claude authentication |
| `OPENAI_API_KEY` | For OpenAI calls | empty | OpenAI authentication |
| `GEMMA4_API_KEY` | For authenticated compatible endpoints | empty | Bearer token for the local/proxy model endpoint |
| `OLLAMA_BASE_URL` | No | host Ollama URL | OpenAI-compatible/local model endpoint |
| `OLLAMA_MODEL` | No | `gemma4` | Local/proxy agent model |
| `LANGFUSE_PUBLIC_KEY` | For Langfuse | empty | Langfuse project key |
| `LANGFUSE_SECRET_KEY` | For Langfuse | empty | Langfuse secret |
| `LANGFUSE_BASE_URL` | No | Langfuse Cloud | Langfuse host |
| `OPERATOR_API_TOKEN` | Production and proof compose | required, no default | Protects operator mutations and stays server-side in the proof proxy |
| `OPERATOR_PROXY_MODE` | Local Compose only | disabled | Set to `local` only for the loopback-bound operator console |
| `PROOF_PROXY_MODE` | Local Compose only | disabled | Set to `local` only for the loopback-bound proof console |
| `RESEARCH_PROOF_MODE` | No | `true` in Compose | Enables the controlled, post-checkpoint proof interruption |
| `KNOWLEDGE_EMBEDDING_PROVIDER` | No | `deterministic` | Local fixture or `openai` semantic embeddings |
| `KNOWLEDGE_EMBEDDING_BASE_URL` | No | OpenAI API | OpenAI-compatible embedding endpoint |
| `KNOWLEDGE_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model identity |
| `KNOWLEDGE_EMBEDDING_DIMENSIONS` | No | `768` | Manifest and vector dimensions |
| `NEXT_PUBLIC_API_URL` | Production frontend | `http://localhost:8000` | Public API URL embedded during the Next build |
| `BACKEND_PORT` | No | `8000` | Host-only backend port |
| `FRONTEND_PORT` | No | `3737` | Host-only frontend port |

The container sets these storage contracts:

| Variable | Container value |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:////data/sqlite/adaptive_agent.db` |
| `RESEARCH_DATABASE_PATH` | `/data/sqlite/research.db` |
| `KNOWLEDGE_INDEX_PATH` | `/data/index` |

`NEXT_PUBLIC_API_URL` is public by design. Never place credentials in a
`NEXT_PUBLIC_*` variable.

The browser calls narrow, same-origin Next.js proxies for protected operator and
proof mutations. Each proxy uses an exact method/path allowlist and adds
`OPERATOR_API_TOKEN` on the server. The token never enters the browser bundle.
Both proxies fail closed unless their mode is explicitly `local`, the request
host is loopback, and browser fetch metadata proves a same-origin request.
Compose opts into those local modes and binds both services to loopback. Do not
enable either proxy on an internet-facing deployment. Set
`RESEARCH_PROOF_MODE=false` outside an intentional proof environment.

## Production notes

- Put TLS and request limits at a maintained reverse proxy or platform ingress.
- Change `CORS_ORIGINS` to the exact production frontend origin.
- Set a high-entropy `OPERATOR_API_TOKEN`; do not expose mutation routes
  without it. Never put it in a `NEXT_PUBLIC_*` variable. An internet-facing
  frontend must use real user/session authorization or keep operator mutations
  backend-only; the local proxy deliberately denies non-loopback requests.
- Set `RESEARCH_PROOF_MODE=false` unless the deployment intentionally exposes
  the controlled crash-and-resume demonstration.
- Use one backend worker with SQLite. Move to PostgreSQL and a distributed lease
  implementation before horizontal backend scaling.
- Mount durable storage at `/data/sqlite` and `/data/index`.
- Run `scripts/smoke-stack.sh` after deployment. Set `BACKEND_URL` and
  `FRONTEND_URL` to the deployed origins.
- Knowledge and research health probes are optional in the smoke script until
  those routers are mounted. Once present, any response other than HTTP 200
  fails the smoke.

Example:

```bash
BACKEND_URL=https://api.example.com \
FRONTEND_URL=https://agent.example.com \
./scripts/smoke-stack.sh
```

## Build targets

Build each image independently when Compose is not the deploy transport:

```bash
docker build --target backend-runtime --tag adaptive-agent-backend .
docker build \
  --target frontend-runtime \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --tag adaptive-agent-frontend .
```

No API key or operator token is accepted as a Docker build argument. This keeps
credentials out of image history and build caches.
