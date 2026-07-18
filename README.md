# Adaptive Agent

[![Python](https://img.shields.io/badge/-Python_3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Next.js](https://img.shields.io/badge/-Next.js_16-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![CI](https://github.com/maxpetrusenko/AdaptiveAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/maxpetrusenko/AdaptiveAgent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Durable agent runtime with checkpointed execution and verifier-gated prompt improvement.

---

**An agent that can work for longer than one model call without grading or deploying its own changes.** Durable task ledgers survive restarts. Training failures can propose a bounded prompt candidate, but sealed validation and protected cases decide whether it is eligible. An operator must explicitly promote it.

```
Goal → Task ledger → Step → Checkpoint → Evidence → Resume / Replan

Training failures → Prompt candidate → Sealed validation + protected suite
                                      → Ready / Rejected
                                      → Explicit promote → Rollback
```

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
pnpm dev                      # http://localhost:3737
```

Open `http://localhost:3737`. The database and 10 governed seed cases are created automatically on first run. The operator ledger is at `/tasks`.

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
- **Promotion gate** — Sealed evaluation proof, explicit hash confirmation, and rollback
- **Dashboard** — Live metrics: pass rate, hallucination rate, cost, trends over time

---

## Architecture

```
frontend/                       backend/
├── Next.js 16 (App Router)     ├── FastAPI + SQLAlchemy + SQLite
├── shadcn/ui + Tailwind        ├── LangGraph agent with tools
├── Recharts for metrics        ├── LLM-as-judge evaluation
├── SSE streaming               ├── Durable task/effect ledger
└── Operator proof surface      └── Persisted promotion authority
```

### Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, Tailwind CSS, shadcn/ui, Recharts, react-markdown |
| Backend | Python 3.11, FastAPI, LangGraph, SQLAlchemy, SQLite |
| Agent | OpenAI / Anthropic / OpenAI-compatible local proxy, tool calling, SSE streaming |
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
├── src/hooks/use-chat.ts       # Chat state + streaming hook
└── src/components/             # Chat, evals, cases, adapt, layout
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
- [ ] Add more tools (web search, code interpreter, RAG)
- [ ] DSPy-style prompt compilation (MIPROv2 optimizer)
- [ ] Fine-tuning path (v2 adaptation beyond prompt updates)
- [ ] OpenTelemetry tracing for agent observability

---

## License

MIT
