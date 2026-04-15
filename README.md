# Adaptive Agent

[![Python](https://img.shields.io/badge/-Python_3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Next.js](https://img.shields.io/badge/-Next.js_15-000000?logo=next.js&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/-LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Self-improving AI agent with an eval → feedback → update loop. Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) and the [SICA paper](https://arxiv.org/abs/2504.15228).

---

**An agent that gets better at its job automatically.** Run evals, detect failures, generate improved prompts, re-eval, and accept only what improves metrics. The full loop runs from a single "Improve" button in the UI.

```
User Input → Agent (LangGraph) → Output → Eval Layer → Failure Detection
                                                ↓
                                    Test Case Generation
                                                ↓
                                    Prompt Update (LLM-generated)
                                                ↓
                                    Re-eval → Accept / Reject
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/maxpetrusenko/AdaptiveAgent.git
cd AdaptiveAgent

# Backend
cd backend
pip install -e ".[dev]"
cp .env.example .env          # add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload # http://localhost:8000

# Frontend (new terminal)
cd frontend
pnpm install
pnpm dev                      # http://localhost:3737
```

Open `http://localhost:3737`. The database and 10 seed eval cases are created automatically on first run.

---

## What It Does

### The Self-Improving Loop

The core loop follows the Karpathy autoresearch pattern — **only accept changes that measurably improve performance**:

1. **Eval** — Run all test cases against the current agent prompt
2. **Detect** — LLM-as-judge identifies failures (wrong answers, hallucinations)
3. **Generate** — LLM analyzes failure patterns and writes an improved system prompt
4. **Re-eval** — Run the same test suite with the new prompt
5. **Accept/Reject** — If pass rate improved → keep new prompt. If not → revert.

Every prompt version is stored with full history and rollback capability.

### Key Features

- **Chat** — Streaming conversations with tool use (calculator, time) via LangGraph
- **Evals** — Run evaluation suites with pass/fail, hallucination detection, and consistency checks
- **Cases** — 10 seed test cases + create your own + auto-generate from failures
- **Adaptation** — One-click self-improvement loop with before/after diff view
- **Dashboard** — Live metrics: pass rate, hallucination rate, cost, trends over time

---

## Architecture

```
frontend/                       backend/
├── Next.js 15 (App Router)     ├── FastAPI + SQLAlchemy + SQLite
├── shadcn/ui + Tailwind        ├── LangGraph agent with tools
├── Recharts for metrics        ├── LLM-as-judge evaluation
├── SSE streaming               ├── Prompt versioning + rollback
└── 5 pages, 12 components      └── Self-improving loop orchestrator
```

### Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 15, Tailwind CSS, shadcn/ui, Recharts, react-markdown |
| Backend | Python 3.11, FastAPI, LangGraph, SQLAlchemy, SQLite |
| Agent | Claude (via langchain-anthropic), tool calling, SSE streaming |
| Eval | LLM-as-judge (Haiku for speed), hallucination detection, consistency checks |
| Testing | Vitest (frontend), pytest (backend), 20 tests total |

---

## Key Paths

```
backend/
├── app/agent/graph.py          # LangGraph agent definition
├── app/agent/prompts.py        # System prompt (v1 seed)
├── app/eval/runner.py          # Eval execution engine
├── app/eval/checks.py          # Pass/fail, hallucination, consistency
├── app/adapt/loop.py           # Self-improving loop orchestrator
├── app/adapt/prompt_updater.py # LLM-based prompt improvement
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
| `GET` | `/api/adapt/runs` | List adaptation runs |
| `GET` | `/api/adapt/runs/:id` | Adaptation detail + prompt diff |
| `GET` | `/api/adapt/prompts` | List prompt versions |
| `GET` | `/api/dashboard/metrics` | Dashboard metrics |

---

## Data Models

```
Session          → Messages (chat history)
PromptVersion    → versioned system prompts with parent chain
EvalCase         → test inputs + expected outputs + tags
EvalRun          → execution of all cases against a prompt version
EvalResult       → per-case pass/fail + score + latency
AdaptationRun    → before/after prompt versions + pass rates + accepted?
```

---

## Design Decisions

- **SSE over WebSocket** — simpler, HTTP/2 compatible, matches Anthropic's streaming API
- **SQLite** — zero-config for MVP, single file, easy to inspect with DB Browser
- **LLM-as-judge** — Haiku for fast/cheap eval checks, main model for prompt generation
- **Accept/reject gate** — autoresearch pattern: never deploy a regression
- **Prompt versioning** — every change tracked, full rollback, diff view in UI

---

## Research References

Built on ideas from:

- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — fixed-budget modify/run/eval/accept loop
- [SICA: Self-Improving Coding Agent](https://arxiv.org/abs/2504.15228) — agent edits its own scaffolding
- [GVU Framework](https://arxiv.org/abs/2512.02731) — Generator-Verifier-Updater unifies all self-improvement methods
- [LangGraph Reflection Patterns](https://www.langchain.com/blog/reflection-agents/) — basic reflection, Reflexion, LATS
- [SelfCheckGPT](https://arxiv.org/abs/2303.08896) — consistency-based hallucination detection

Key insight: **strengthen the verifier, not the generator**. If your eval layer is weak, the improvement loop diverges.

---

## Next Steps

- [ ] Add more tools (web search, code interpreter, RAG)
- [ ] Implement consistency checking (multi-run variance)
- [ ] DSPy-style prompt compilation (MIPROv2 optimizer)
- [ ] Fine-tuning path (v2 adaptation beyond prompt updates)
- [ ] Playwright e2e tests for full UI flows
- [ ] OpenTelemetry tracing for agent observability

---

## License

MIT
