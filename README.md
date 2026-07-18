# Adaptive Agent

[![Python](https://img.shields.io/badge/-Python_3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![Rust](https://img.shields.io/badge/-Rust_1.97-000000?logo=rust&logoColor=white)](https://www.rust-lang.org)
[![TypeScript](https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Next.js](https://img.shields.io/badge/-Next.js_16-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Langfuse](https://img.shields.io/badge/-Langfuse_traced-111111)](https://langfuse.com)
[![CI](https://github.com/maxpetrusenko/AdaptiveAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/maxpetrusenko/AdaptiveAgent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> A durable agent runtime with native Rust hybrid retrieval, cited research,
> crash-safe execution, and verifier-gated self-improvement.

---

**An agent that can work for longer than one model call without grading or
deploying its own changes.** Python owns orchestration and API contracts. Rust
owns the measured retrieval hot path: exact cosine, Tantivy BM25, tenant
filtering, and deterministic reciprocal-rank fusion. Durable effect journals
survive worker failure. Training failures may propose bounded prompt changes,
but sealed validation and protected cases decide whether they are eligible.
An operator must explicitly promote them.

```
Goal → Plan → Rust retrieve → Sealed effect → Synthesize → Verify
                        ↘ crash → resume without repeating retrieval

Training failures → Prompt candidate → Sealed validation + protected suite
                                      → Ready / Rejected
                                      → Explicit promote → Rollback
```

---

## Five-Minute Proof

Open the application at `/proof`, then:

1. Ingest the three visible sources.
2. Inspect the native index generation and source hashes.
3. Start a four-step research run.
4. Observe a controlled interruption after retrieval is durably sealed.
5. Resume and verify that retrieval remains on attempt one.
6. Audit the cited Rust search hits, vector and BM25 ranks, index version, and
   embedding fingerprint.

Deterministic mode proves recovery and inspects native retrieval as a separate,
clearly labeled result. Select live mode with a configured model key to run
synthesis and verification over the tenant's native retrieval results.

![Durable research proof showing a sealed crash and exactly-once resume](assets/proof-console.png)

| Claim | Shipped evidence |
| --- | --- |
| Agentic long-horizon execution | Four autonomous plan, retrieve, synthesize, verify steps; leases, budgets, replanning, and sealed effects |
| RAG and semantic retrieval | OpenAI-compatible embedding adapter, cited answers, citation and lexical-overlap verifier, prompt-injection boundary |
| Rust performance | Runtime PyO3 extension using Rayon, Tantivy, exact cosine, and RRF |
| Correctness before speed | Python oracle parity is mandatory before any latency is reported |
| Self-improvement safety | Sealed validation, protected-suite veto, explicit promotion, transactional rollback |
| Production tooling | FastAPI, Next.js, Langfuse redaction, health/recovery, Docker, CI, and real Playwright |

Measured locally on an Apple arm64 machine, the reproducible 10,000-chunk,
128-dimension fixture produced an 8.06 ms Rust p50 versus 161.07 ms for the
Python oracle, a 19.97× p50 speedup. Treat this as a machine-specific engineering
measurement, not a universal product benchmark. See the
[benchmark artifact](docs/proof/retrieval-benchmark.json) and
[TDD ledger](docs/proof/tdd-red-green.md).

Reproduce it:

```bash
cd backend
uv run adaptive-agent-retrieval-benchmark \
  --chunks 10000 --dimensions 128 --queries 5 --iterations 10
```

A live OpenAI embedding → Rust retrieval → cited GPT-5.4 answer run completed
with a redacted Langfuse trace; the
[proof artifact](docs/proof/live-openai-rust-rag.json) records model, ranks,
latency, usage, and trace ID. Claude is wired through the same shared model
boundary, but the recorded live Claude attempt is honestly
[blocked by Anthropic account credit](docs/proof/live-claude-blocker.json).

---

## Quick Start

```bash
# Clone
git clone https://github.com/maxpetrusenko/AdaptiveAgent.git
cd AdaptiveAgent

# Backend
cd backend
uv sync --extra dev
cp .env.example .env          # add OPENAI_API_KEY or ANTHROPIC_API_KEY
uv run uvicorn app.main:app --reload # http://localhost:8000

# Frontend (new terminal)
cd frontend
pnpm install
PROOF_PROXY_MODE=local \
OPERATOR_PROXY_MODE=local \
pnpm dev                      # http://localhost:3737
```

Open `http://localhost:3737/proof`. `uv sync` builds and installs the locked
PyO3 ABI3 extension. Rust 1.97.1 is pinned in the native crate. The database and
10 governed seed cases are created automatically on first run. The operator
ledger is at `/tasks`.

For a one-command container stack, follow
[docs/deployment.md](docs/deployment.md).

The default configuration is local-only SQLite. Operator-controlled mutations are
limited to loopback clients unless `OPERATOR_API_TOKEN` is set; with a token configured,
task, evaluation, case, and adaptation mutations require the same value in the
`X-Operator-Token` header.

---

## Quality Gates

Run the same checks enforced by GitHub Actions:

```bash
# Backend
cd backend
uv sync --extra dev --locked
uv run ruff check .
uv run pytest -q

# Native retrieval
cd ../native/adaptive_retrieval
cargo fmt --check
cargo clippy --all-targets --all-features --locked -- -D warnings
cargo test --locked

# Frontend
cd ../frontend
pnpm install --frozen-lockfile
pnpm test
pnpm lint
pnpm build
pnpm e2e
```

---

## Benchmark It

What the current benchmark story can prove:

- the adaptive loop improves a weak starting prompt when there is a real failure signal
- training, validation, and protected cases are kept in separate roles
- evaluation creates an inactive ready or rejected candidate with replayable lineage
- only an explicit `--promote-candidate` run can change the active prompt
- saturated suites stay stable instead of forcing pointless prompt churn
- the adaptive agent can catch up to strong tool-using baselines on the smoke suite

What it does not prove yet:

- state-of-the-art performance against external agent products
- broad statistical significance across large public benchmarks
- code-level self-modification beyond prompt updates

Two benchmark modes:

1. single-system adaptation benchmark
2. comparative leaderboard against baselines

Single-system:

```bash
cd backend
python -m app.benchmarks.run --repeats 3 --out benchmark-results/latest.json
```

The default is evaluate-only. For an isolated benchmark where you explicitly want to activate an eligible candidate:

```bash
python -m app.benchmarks.run \
  --repeats 3 \
  --promote-candidate \
  --out benchmark-results/latest.json
```

Comparative leaderboard:

```bash
cd backend
python -m app.benchmarks.compare --out benchmark-results/compare.json
```

Human-readable storyboard:

```bash
python -m app.benchmarks.report_html --dir benchmark-results
open benchmark-results/index.html
```

If the seeded suite is already at 100% and you want to prove the loop can recover from a weak prompt, run the stress benchmark:

```bash
python -m app.benchmarks.run \
  --stress-baseline tool-agnostic \
  --case-tag tool-use \
  --repeats 1 \
  --consistency-repeats 0 \
  --out benchmark-results/stress-tool-use.json
```

The report includes:

- baseline mean/std pass rate
- candidate prompt evaluation
- verifier decision, rationale, hashes, and dataset lineage
- candidate status and whether explicit promotion occurred
- whether the active prompt version changed

The comparative report includes:

- `direct_llm` vs `weak_static_agent` vs `adaptive_agent` vs `seed_tool_agent` vs `sdk_tool_agent`
- 8 train cases and 42 held-out eval cases across tool use, reasoning, factual recall, safety, uncertainty, privacy, retrieval, prompt-injection, and multi-turn behavior
- average latency
- hallucination failures
- pairwise win/loss/tie deltas against `adaptive_agent`
- judge calibration on 56 labeled cases
- adversarial null-agent and judge-bias checks

See [docs/runbooks/benchmarking.md](docs/runbooks/benchmarking.md) for interpretation.

### Comparative Benchmark — 5 systems, live on Gemma 4
![Benchmark Leaderboard](assets/benchmark-leaderboard.png)

---

## Screenshots

### Dashboard — Monitor agent metrics in real-time
![Dashboard](assets/dashboard.png)

### Chat — Streaming conversations with tool use
![Chat](assets/chat-with-message.png)

### Evaluations — Run evals, see pass/fail rates and trends
![Evals](assets/evals.png)

### Test Cases — 10 seed cases + create your own
![Cases](assets/cases.png)

### Adaptation — Candidate evaluation with prompt diff view
![Adapt](assets/adapt.png)

### Operator console — Durable tasks and explicit promotion authority
![Operator console](assets/operator-console.png)

---

## What It Does

### The Governed Improvement Loop

The updater can propose; it cannot approve or activate:

1. **Train** — Evaluate the active prompt on training cases and generate a bounded prompt candidate from those failures only.
2. **Validate** — Compare parent and candidate on sealed validation cases.
3. **Protect** — Veto any protected-suite status or score regression.
4. **Budget** — Enforce uncertainty, latency, and token-usage limits.
5. **Record** — Persist raw paired results, policy, hashes, mutations, and rationale.
6. **Authorize** — Keep eligible candidates inactive until explicit operator promotion.
7. **Rollback** — Restore the verified parent through the same transactional authority.

Rejected candidates never become active. Concurrent promotions have one database-authorized winner.

### Durable Long-Horizon Tasks

Task runs persist goals, constraints, acceptance criteria, plan versions, checkpoints, steps, budgets, stalls, evidence, and effect journals. Optimistic compare-and-swap updates prevent concurrent commands from losing work. Idempotency keys replay the same request and reject conflicting payload reuse. Repeated stalls enter `replan_required`; verified completed steps survive replanning and process restarts.

### Key Features

- **Chat** — Streaming conversations with tool use (calculator, time) via LangGraph
- **Evals** — Run evaluation suites with pass/fail, hallucination detection, and consistency checks
- **Cases** — 10 seed test cases + create your own + auto-generate from failures
- **Adaptation** — Candidate evaluation history with before/after prompt diff
- **Tasks** — Durable execution timeline, checkpoint pressure, evidence state, and lifecycle controls
- **Proof** — Real native ingest/search plus controlled research crash and resume
- **Knowledge** — Content-addressed sources, versioned generations, real embedding adapter, citations, and fail-closed citation/overlap checks
- **Research** — Autonomous plan, retrieve, synthesize, verify loop with leases, budgets, recovery, and suffix replanning
- **Native retrieval** — PyO3, Rayon exact cosine, Tantivy BM25, tenant filtering, and deterministic RRF
- **Observability** — Langfuse callbacks with prompt and output content redacted by default
- **Promotion gate** — Sealed evaluation proof, explicit hash confirmation, and rollback
- **Dashboard** — Live metrics: pass rate, hallucination rate, cost, trends over time

---

## Architecture

```
frontend/                         backend/                         native/
├── Next.js 16 (App Router)       ├── FastAPI + SQLAlchemy          └── adaptive_retrieval
├── proof + operator surfaces     ├── knowledge generations            ├── PyO3 ABI3
├── narrow server proof proxy     ├── autonomous research loop         ├── Tantivy BM25
└── SSE streaming                 ├── LangGraph + model tools           ├── Rayon cosine
                                  ├── Langfuse redaction                └── versioned snapshots
                                  └── effect + promotion authority
```

### Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, Tailwind CSS, shadcn/ui, Recharts, react-markdown |
| Backend | Python 3.11, FastAPI, LangGraph, SQLAlchemy, SQLite |
| Retrieval | Rust 1.97.1, PyO3, Tantivy, Rayon, maturin |
| Agent | OpenAI / Anthropic / OpenAI-compatible local proxy, tool calling, SSE streaming |
| RAG | OpenAI-compatible embeddings, content lineage, hybrid search, RRF, citations, lexical-overlap verification |
| Observability | Langfuse v4 callbacks, correlation metadata, content redaction |
| Eval | deterministic checks first, LLM-as-judge fallback, hallucination detection, consistency checks |
| Testing | Vitest, Playwright, pytest, Ruff, ESLint, GitHub Actions |

---

## Key Paths

```
backend/
├── app/agent/graph.py          # LangGraph agent definition
├── app/agent/prompts.py        # System prompt (v1 seed)
├── app/eval/runner.py          # Eval execution engine
├── app/eval/checks.py          # Pass/fail, hallucination, consistency
├── app/adapt/loop.py           # Self-improving loop orchestrator
├── app/adapt/promotion.py      # Deterministic verifier policy
├── app/adapt/authority.py      # Transactional promotion and rollback
├── app/adapt/prompt_updater.py # LLM-based prompt improvement
├── app/tasks/                  # Durable task ledger and checkpoints
├── app/knowledge/              # Ingest, embeddings, lineage, native retrieval, grounding
├── app/research/               # Autonomous durable research runner and adapters
├── app/observability/          # Langfuse callbacks, metadata, and redaction
├── app/memory/store.py         # Failure storage
├── app/memory/cases.py         # Failure → test case conversion
├── app/models.py               # All SQLAlchemy models
├── app/seed.py                 # 10 seed eval cases + prompt v1
└── app/api/                    # REST endpoints (chat, evals, cases, adapt, dashboard)

frontend/
├── src/app/page.tsx            # Dashboard with live metrics
├── src/app/chat/page.tsx       # Chat interface with SSE streaming
├── src/app/evals/page.tsx      # Eval runs + results + charts
├── src/app/cases/page.tsx      # Test case management
├── src/app/adapt/page.tsx      # Adaptation history + prompt diff
├── src/app/tasks/page.tsx      # Operator task and promotion console
├── src/app/proof/page.tsx      # Native RAG and crash-resume proof
├── src/hooks/use-chat.ts       # Chat state + streaming hook
└── src/components/             # Chat, evals, cases, adapt, layout

native/adaptive_retrieval/
├── src/index.rs                # Tantivy search and tenant filter
├── src/scoring.rs              # Rayon cosine and deterministic RRF
├── src/persistence.rs          # Versioned, atomic native snapshots
└── tests/hybrid_contract.rs    # ABI contract and recovery coverage
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/chat/sessions` | Create chat session |
| `GET` | `/api/chat/sessions` | List sessions |
| `POST` | `/api/chat/stream` | Stream agent response (SSE) |
| `GET` | `/api/cases` | List eval test cases |
| `POST` | `/api/cases` | Create test case |
| `POST` | `/api/evals/run` | Trigger eval run |
| `GET` | `/api/evals/runs` | List eval runs |
| `GET` | `/api/evals/runs/:id/results` | Get eval results |
| `POST` | `/api/adapt/improve` | Trigger self-improving loop |
| `GET` | `/api/adapt/candidates` | List persisted promotion candidates |
| `POST` | `/api/adapt/candidates/:id/promote` | Explicitly activate an eligible candidate |
| `POST` | `/api/adapt/candidates/:id/rollback` | Restore the candidate parent |
| `GET` | `/api/adapt/runs` | List adaptation runs |
| `GET` | `/api/adapt/runs/:id` | Adaptation detail + prompt diff |
| `GET` | `/api/adapt/prompts` | List prompt versions |
| `GET` | `/api/dashboard/metrics` | Dashboard metrics |
| `POST` | `/api/tasks` | Create a durable task ledger |
| `GET` | `/api/tasks` | List durable tasks |
| `GET` | `/api/tasks/:id` | Get task state, checkpoint, and evidence |
| `POST` | `/api/tasks/:id/advance` | Record one idempotent step result |
| `POST` | `/api/tasks/:id/replan` | Replace the uncompleted plan suffix |
| `POST` | `/api/tasks/:id/pause` | Pause an active task |
| `POST` | `/api/tasks/:id/resume` | Resume a paused task |
| `POST` | `/api/tasks/:id/cancel` | Cancel a task |
| `GET` | `/api/tasks/:id/effects` | Inspect the idempotent effect journal |
| `POST` | `/api/knowledge/ingest` | Build and activate a versioned native generation |
| `POST` | `/api/knowledge/search` | Search the active Rust hybrid index |
| `GET` | `/api/knowledge/index/health` | Inspect generation and index health |
| `POST` | `/api/research/:tenant/runs` | Create an autonomous durable research run |
| `POST` | `/api/research/:tenant/runs/:id/run` | Run or resume from the durable cursor |

---

## Data Models

```
Session          → Messages (chat history)
PromptVersion    → versioned system prompts with parent chain
EvalCase         → test inputs + expected outputs + tags
EvalRun          → execution of all cases against a prompt version
EvalResult       → per-case pass/fail + score + latency
AdaptationRun    → before/after prompt versions + pass rates + accepted?
PromotionRecord  → immutable verifier evidence + operator lifecycle
TaskLedger       → checkpoints + steps + evidence + idempotent effects
```

---

## Design Decisions

- **SSE over WebSocket** — simpler, HTTP/2 compatible, matches Anthropic's streaming API
- **SQLite** — zero-config local runtime; the task ledger currently uses SQLite-specific migration and compare-and-swap behavior
- **LLM-as-judge fallback** — deterministic checks first; configured judge model handles qualitative checks
- **Separate updater and authority** — candidate generation cannot see sealed cases or activate itself
- **Fail-closed verifier** — protected regressions, invalid scores, insufficient samples, and budget regressions reject
- **Prompt versioning** — every candidate is inactive until authorized, with transactional rollback
- **Idempotent task effects** — request hashes plus checkpoint compare-and-swap prevent duplicate or lost effects
- **PyO3 instead of a retrieval microservice** — keeps the measured CPU hot path
  native without adding network serialization or another deployment unit
- **Correctness-gated performance** — native timing is rejected until ranked
  IDs, dense scores, and per-leg ranks match the Python oracle
- **Metadata-only LLM telemetry** — Langfuse keeps timing, model, usage, and
  correlation while masking prompt and output attributes

---

## Research References

Built on ideas from:

- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — fixed-budget modify/run/eval/accept loop
- [SICA: Self-Improving Coding Agent](https://arxiv.org/abs/2504.15228) — agent edits its own scaffolding
- [GVU Framework](https://arxiv.org/abs/2512.02731) — Generator-Verifier-Updater unifies all self-improvement methods
- [LangGraph Reflection Patterns](https://www.langchain.com/blog/reflection-agents/) — basic reflection, Reflexion, LATS
- [SelfCheckGPT](https://arxiv.org/abs/2303.08896) — consistency-based hallucination detection
- [Anthropic long-running agent harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — incremental progress, durable artifacts, and self-verification
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — checkpoints, threads, replay, and fault tolerance
- [Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/) — task and progress ledgers with stall-aware replanning
- [Anthropic agent evaluations](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — trajectory and outcome evaluation
- [Anthropic reward tampering](https://www.anthropic.com/research/reward-tampering) — keep the optimizer away from its reward channel

Key insight: **strengthen the verifier, not the generator**. If your eval layer is weak, the improvement loop diverges.

---

## Next Steps

- [ ] Add a production queue and worker lease for distributed task execution
- [ ] Replace SQLite-specific task migrations before a PostgreSQL deployment
- [ ] Add authenticated multi-user operator roles
- [ ] Add more tools (web search and code interpreter)
- [ ] Add approximate vector search after exact-search scale data justifies it
- [ ] DSPy-style prompt compilation (MIPROv2 optimizer)
- [ ] Fine-tuning path (v2 adaptation beyond prompt updates)
- [ ] Add a hosted, authenticated demo after selecting a deployment target

---

## License

MIT
