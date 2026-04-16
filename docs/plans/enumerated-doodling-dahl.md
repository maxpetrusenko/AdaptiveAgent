# Adaptive Agent — Implementation Plan

## Status

Source draft saved from `~/.claude/plans/enumerated-doodling-dahl.md`.

This version tightens a few things:

- Adds a bootstrap wave for repo setup, contracts, and local dev ergonomics
- Splits online chat path from offline adaptation worker path
- Makes evals deterministic-first; LLM-as-judge secondary, not primary
- Adds prompt adaptation guardrails to prevent silent regressions
- Replaces dark-default UI bias with system-aware theming
- Defines exit criteria per wave instead of feature-only checklists

## Outcome

Build a self-improving agent product with:

- a clean operator UI
- a usable chat surface
- an eval system that can detect regressions
- a memory layer that turns failures into reusable cases
- an adaptation loop that proposes prompt/routing changes, re-runs evals, and accepts only verified improvements

## Non-goals for MVP

- multi-user auth / org permissions
- distributed job queues
- production-grade sandboxed code execution
- autonomous codebase rewrites outside prompt/routing/config layers
- model fine-tuning

## Core Product Shape

Two loops. Keep them separate.

1. Online loop
   User input -> agent -> tools -> streamed output -> trace/log persistence

2. Offline improvement loop
   eval suite -> failure analysis -> candidate update -> re-run evals -> accept/reject -> version history

That separation matters. Chat latency stays predictable. Self-improvement stays observable and reversible.

## Guiding Principles

- Vertical slices. Every wave ends in a user-visible working path.
- Deterministic before clever. Exact checks and regression fixtures before LLM judges.
- Reversible adaptation. Every accepted change tied to a version and rollback path.
- Local-first dev. Everything runnable in local/dev with the same env shape.
- Constrained self-editing. The system can update prompts, routing weights, and adaptation config before it can touch arbitrary code.
- Inspectable data. SQLite for MVP, flat-enough records, easy manual inspection.

## Reference Patterns to Borrow

Base reference: `/Users/maxpetrusenko/Downloads/claw-code-main.zip`

Adopt:

- trait/interface-driven dependency injection
- session-first agent state model
- flat JSON-ish event/session artifacts where useful
- layered prompt composition
- permission-gated tool execution

Do not blindly port:

- Rust-specific abstractions that add ceremony without helping TypeScript/Python
- any CLI-first UX that fights the web product shape

## Tech Stack

- Frontend: Next.js 16 App Router, TypeScript, Tailwind CSS, shadcn/ui, Recharts
- Backend API: Python 3.11, FastAPI, Pydantic, SQLAlchemy, SQLite
- Agent runtime: LangGraph
- Frontend tests: Vitest
- Backend tests: pytest
- E2E: Playwright
- Frontend package manager: pnpm
- Backend env/package manager: uv

## Proposed Repo Layout

```text
AdaptiveAgent/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   └── styles/
│   ├── e2e/
│   ├── public/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── agent/
│   │   ├── adapt/
│   │   ├── db/
│   │   ├── eval/
│   │   ├── memory/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
├── docs/
│   ├── architecture/
│   ├── plans/
│   └── runbooks/
├── .env.example
├── Makefile
├── pnpm-workspace.yaml
└── README.md
```

Notes:

- `services/` for provider wrappers and background orchestration helpers
- `db/` split from `models.py` monolith early; avoids 500+ LOC creep
- root `Makefile` or task runner for a single dev/test entrypoint

## High-Level Architecture

```text
User -> Next.js UI -> FastAPI -> LangGraph Agent -> Tools -> Response Stream
                                      |
                                      v
                           Session + Message + Trace Storage

Operator -> Eval UI -> Eval Runner -> Current Prompt Version -> Results
                                           |
                                           v
                                   Failure Memory Store
                                           |
                                           v
                                  Adaptation Orchestrator
                                           |
                              candidate prompt/routing update
                                           |
                                re-run gated eval comparison
                                           |
                               accept + activate or reject
```

## API Surface, MVP

Frontend should code against explicit contracts early.

- `GET /health`
- `GET /api/dashboard`
- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{id}`
- `POST /api/chat/stream`
- `GET /api/eval-cases`
- `POST /api/eval-cases`
- `POST /api/eval-runs`
- `GET /api/eval-runs`
- `GET /api/eval-runs/{id}`
- `GET /api/adapt-runs`
- `POST /api/adapt-runs`
- `POST /api/prompt-versions/{id}/activate`

Use SSE for chat streaming and long-running job progress before considering WebSockets.

## Data Model, MVP

Keep tables focused and inspectable.

- `sessions`
  - `id`, `title`, `created_at`, `updated_at`
- `messages`
  - `id`, `session_id`, `role`, `content`, `tool_calls_json`, `model`, `latency_ms`, `created_at`
- `prompt_versions`
  - `id`, `version`, `content`, `layer`, `parent_id`, `change_reason`, `is_active`, `created_at`
- `eval_cases`
  - `id`, `name`, `input`, `expected_output`, `rubric_json`, `tags_json`, `source`, `created_at`
- `eval_runs`
  - `id`, `prompt_version_id`, `status`, `mode`, `started_at`, `completed_at`, `total`, `passed`, `failed`, `pass_rate`
- `eval_results`
  - `id`, `eval_run_id`, `eval_case_id`, `status`, `actual_output`, `score`, `checker_breakdown_json`, `error`, `latency_ms`
- `failure_events`
  - `id`, `session_id`, `message_id`, `eval_case_id`, `kind`, `input`, `expected_output`, `actual_output`, `diagnostics_json`, `created_at`
- `adaptation_runs`
  - `id`, `status`, `started_at`, `completed_at`, `before_version_id`, `candidate_version_id`, `after_version_id`, `before_pass_rate`, `after_pass_rate`, `accepted`, `summary_json`

Add migrations from the start. Avoid auto-create once real data matters.

## Prompt System

Do not store a single blob only.

Layer prompts:

- base system prompt
- product/task instructions
- tool-use policy
- adaptation patch layer

MVP rule: adaptation can only change the adaptation patch layer, not the whole base prompt. That keeps diffs readable and rollback safe.

## Eval Strategy

Use a checker stack, not one score.

Priority order:

1. exact / normalized string match
2. structured JSON/schema match
3. rubric checklist
4. consistency variance check
5. LLM-as-judge for unsupported claims / qualitative fit

Acceptance should not depend on judge score alone.

## Adaptation Guardrails

Required before auto-accept:

- pass rate improves or targeted failure rate drops materially
- no regression on protected seed cases
- no increase beyond threshold in hallucination or inconsistency score
- candidate diff limited to allowed prompt layer
- full before/after eval artifact stored

Recommended first acceptance rule:

- accept only if:
  - overall pass rate improves by at least `+5 percentage points`, or
  - targeted failing cohort improves by at least `+20 percentage points`
- and protected seed suite has zero new failures

Anything else: reject, store candidate, surface for review.

## Tooling Constraints

MVP tools:

- `web_search`
- `calculator`
- `code_interpreter_stub` or disabled placeholder behind feature flag

Important:

- start with a stubbed or tightly constrained code-exec tool
- permission gating explicit in backend, not prompt-only
- tool invocations logged with args, latency, and error state

## UI Direction

Avoid dark-default bias. Use system theme first; support both light and dark.

Pages:

- Dashboard
- Chat
- Evals
- Cases
- Adapt

Design direction:

- compact operator console, not consumer chat app
- strong typography, neutral + bold accent palette
- charts and tables first-class
- visible status, diffs, and acceptance decisions

## Wave Plan

### Wave 0 — Bootstrap + Contracts

Goal:
Create a repo that installs, runs, and has typed contracts before feature work.

Tasks:

- scaffold `frontend/` and `backend/`
- add root README with setup + commands
- add root `.env.example`
- add root task entrypoints: `make dev`, `make test`, `make lint`
- define API response/request types in one place
- add docs:
  - `docs/architecture/overview.md`
  - `docs/runbooks/local-dev.md`
- add CI skeleton for frontend + backend checks

Exit criteria:

- fresh machine setup documented
- frontend installs and starts
- backend installs and starts
- `GET /health` returns 200
- CI config exists, even if feature tests are still minimal

### Wave 1 — App Shell + Persistence Skeleton

Goal:
Operator shell live. Database live. Core entities persisted.

Frontend:

- app layout with sidebar and header
- dashboard placeholder cards
- route scaffolds for Chat, Evals, Cases, Adapt
- shared API client and type layer
- smoke test with Vitest

Backend:

- FastAPI app, CORS, settings
- SQLAlchemy models + migrations
- SQLite local DB
- health endpoint
- list/create session endpoints
- seed command for demo data
- pytest smoke test

Exit criteria:

- session can be created and listed
- frontend can fetch backend data
- migrations run cleanly
- frontend/backend smoke tests pass

### Wave 2 — Chat Vertical Slice

Goal:
A user can chat with the agent in a persistent session and inspect tool use.

Frontend:

- chat page with session list
- message timeline
- input composer
- SSE stream consumption
- markdown rendering
- tool call blocks with expandable raw payloads

Backend:

- LangGraph graph: input -> tool loop -> final response
- prompt loading from active prompt version
- `POST /api/chat/stream`
- session detail endpoint
- message persistence
- basic tools wired

Exit criteria:

- streamed response appears incrementally
- session resume works after refresh
- tool invocations visible in UI
- tests cover chat happy path

### Wave 3 — Eval Vertical Slice

Goal:
Create cases, run evals, inspect failures.

Frontend:

- eval run list
- run detail view
- per-case result table
- create/edit eval case flow
- pass-rate chart

Backend:

- eval case CRUD
- eval runner
- checker stack
- result persistence
- run trigger endpoint
- protected seed suite support

Exit criteria:

- operator can author a case
- eval run executes against active prompt version
- failed cases show checker breakdown
- pass/fail trend visible
- pytest covers checker behavior

### Wave 4 — Failure Memory + Adaptation

Goal:
Turn failures into reusable memory and gated prompt candidates.

Frontend:

- cases page shows manual vs generated source
- adapt page shows run history
- prompt diff view
- trigger adaptation action
- accept/reject badges and metrics deltas

Backend:

- failure event store
- failure-to-case generation pipeline
- candidate prompt patch generation
- adaptation orchestrator
- before/after eval comparison
- activate accepted prompt version
- rollback endpoint/action

Exit criteria:

- failed evals create memory artifacts
- adaptation run generates candidate prompt patch
- candidate is auto-rejected on regression
- accepted candidate becomes active version with history

### Wave 5 — Metrics + Polish + E2E Gate

Goal:
Shipable MVP quality bar.

Frontend:

- dashboard metrics: pass rate, hallucination trend, consistency, latency, cost estimate
- loading, error, empty states
- responsive polish
- theme toggle

Backend:

- dashboard aggregation endpoints
- cost/latency accounting
- background-safe progress updates for long runs

Testing:

- Playwright:
  - chat flow
  - eval case creation
  - eval run
  - adaptation run
  - dashboard reflects results
- lint/type/test gates wired into CI

Exit criteria:

- `pnpm lint`
- `pnpm test`
- `pnpm exec playwright test`
- `uv run pytest`
- `uv run ruff check`
- no broken critical path in local dev

## Seed Eval Suite

Start with 10 to 15 cases:

- basic factual QA with exact answer
- calculator use
- tool-required lookup
- multi-step reasoning with structured output
- refusal / safe boundary case
- ambiguity handling
- hallucination trap with unknown answer
- session memory follow-up
- formatting/schema compliance
- consistency probe run multiple times

Mark 3 to 5 as protected seed cases. No regressions allowed there.

## Delivery Order

If only one engineer/agent lane at a time:

1. Wave 0
2. Wave 1
3. Wave 2
4. Wave 3
5. Wave 4
6. Wave 5

If parallel lanes available:

- Lane A: frontend shell, charts, operator UX
- Lane B: backend API, DB, eval/adapt logic
- Sync point every wave on API contracts and exit criteria

## Risks

### 1. LLM-as-judge noise

Mitigation:

- use deterministic checkers first
- judge only for dimensions deterministic checks cannot cover
- store judge rationale, not just score

### 2. Adaptation overfits to a tiny suite

Mitigation:

- protected seed suite
- manual/generated case labels
- compare targeted gains vs global regression

### 3. Chat latency degrades once adaptation features land

Mitigation:

- separate online request path from offline improvement jobs
- do not run adaptation logic inline with user chat

### 4. Prompt diffs become unreadable

Mitigation:

- layered prompt system
- patch-only adaptation scope for MVP

### 5. Code interpreter safety

Mitigation:

- feature flag or stub first
- explicit permission gate
- no production shell access in MVP

## Definition of Done

MVP is done when:

- an operator can chat with the agent in the UI
- eval cases can be authored and run
- failures are persisted and inspectable
- adaptation can propose and test a prompt patch
- only improved prompt versions are activated
- full local gate passes
- docs exist for setup, architecture, and adaptation flow

## First Build Checklist

Day 1 target:

- scaffold frontend/backend
- add health endpoint
- add sidebar shell
- wire root task commands
- add DB + one persisted table
- add one smoke test per side
- commit only after local green

## Recommended Next Artifact

After this plan, write:

- `docs/architecture/overview.md`

It should lock:

- request flow
- adaptation flow
- prompt layering rules
- eval acceptance criteria
- API contract ownership
