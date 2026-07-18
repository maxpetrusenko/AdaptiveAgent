# Durable Self-Improvement: Phase 0

## Decision

Position AdaptiveAgent as a durable, resumable, verifier-gated self-improving
agent runtime.

Do not expand into arbitrary code self-modification yet. The next proof should
show that the system can:

1. execute a multi-step task across interruptions;
2. resume without repeating completed effects;
3. preserve an inspectable task and progress ledger;
4. generate a bounded prompt candidate from training failures;
5. reject candidates that regress sealed validation or protected safety cases;
6. record enough lineage to replay and explain every promotion decision.

## Target User And Job

Target user: an AI platform engineer evaluating whether an agent can be trusted
with multi-hour backend and data tasks.

Job to be done:

> Give the agent a goal that cannot be completed in one model call, observe
> incremental progress, survive a crash or pause, and know that any learned
> behavior was promoted through an independent no-regression gate.

## Why This Direction

The current application already demonstrates a Python/FastAPI/LangGraph agent,
tool calls, evaluation runs, prompt versioning, and accept/reject adaptation.
Its highest-value gap is not another tool. It is credible runtime durability and
separation between the updater and the verifier.

This direction maps directly to high-signal platform concerns:

- durable state and resumability;
- idempotent side effects;
- task planning and stall-aware replanning;
- held-out evaluation and reward-hacking resistance;
- auditability, rollback, and deterministic replay;
- API and operator-interface design.

## Prior Art

- Anthropic long-running harness: incremental feature work, structured progress
  artifacts, clean handoffs, and explicit self-verification.
  <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- LangGraph persistence: thread-keyed checkpoints, fault tolerance, state
  history, and resume.
  <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph functional API: checkpoint side effects and make them idempotent.
  <https://docs.langchain.com/oss/python/langgraph/functional-api>
- Microsoft Magentic-One: outer Task Ledger, inner Progress Ledger, and replan
  after stalled progress.
  <https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/>
- Anthropic agent evals: evaluate trajectories and outcomes over repeated trials,
  using deterministic graders where possible.
  <https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents>
- DSPy GEPA: trace-derived textual feedback, bounded candidate mutation, and
  Pareto retention.
  <https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/GEPA/overview.md>
- Google DeepMind AlphaEvolve: candidate generation separated from objective
  automated evaluators.
  <https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/>
- Anthropic reward tampering: an optimizer must not control its reward channel.
  <https://www.anthropic.com/research/reward-tampering>

## Product Workflow

```text
Create goal
  -> planner writes Task Ledger
  -> executor advances one bounded step
  -> checkpoint state and evidence
  -> verifier marks progress, stall, failure, or completion
  -> resume, cancel, or replan from the last durable checkpoint

Verified failures
  -> training-only diagnosis
  -> bounded prompt candidate
  -> validation and protected-suite comparison
  -> promote or reject
  -> append immutable decision lineage
  -> rollback remains available
```

## Scope

### Slice 0: Reproducible Foundation

- Fix the fresh-clone backend dependency contract.
- Add backend and frontend CI.
- Make the documented install and test commands pass without undeclared
  packages.

Proof:

- fresh `uv sync --extra dev && uv run pytest`;
- Ruff;
- frontend test, lint, and build;
- GitHub Actions green.

### Slice 1: Durable Long-Horizon Runs

- Add persistent task-run and task-step records.
- Store goal, acceptance criteria, plan version, step status, evidence,
  checkpoint metadata, stall count, budget, and terminal reason.
- Add create, list, detail, advance, pause, resume, cancel, and replan APIs.
- Require idempotency keys for advancing effectful steps.
- Preserve completed steps during replanning and replace only the blocked suffix.

TDD proof:

- resume after a simulated crash skips completed steps;
- duplicate resume or advance does not repeat an effect;
- cancel prevents the next step;
- repeated no-progress signals trigger one replan;
- completion is impossible while an acceptance criterion lacks evidence;
- budget exhaustion escalates instead of looping.

### Slice 2: Governed Improvement Promotion

- Separate proposal input from validation and protected evaluation.
- Add a deterministic promotion decision that considers quality delta, safety
  regressions, latency, and cost.
- Reject a candidate that improves training but regresses validation.
- Record parent version, candidate hash, dataset hashes, metric values, and
  decision reason.
- Keep mutation scope limited to prompts and tool descriptions.

TDD proof:

- proposal context contains no validation or protected case content;
- noisy gains are rejected;
- any protected regression vetoes promotion;
- a clear validated gain promotes;
- concurrent promotions have one winner;
- rollback restores the previous version.

### Slice 3: Operator Proof Surface

- Add a Tasks page showing task status, plan version, progress, evidence, and
  pause/resume/cancel controls.
- Extend Adapt with validation/protected metrics and promotion rationale.
- Add an end-to-end fixture that demonstrates interrupt, resume, and safe
  promotion without a paid model.

Proof:

- Vitest component coverage;
- Playwright desktop and narrow viewport flow;
- screenshots or a short inline-rendering proof artifact.

## Risks And Controls

| Risk | Control |
| --- | --- |
| Resume repeats a side effect | Idempotency key plus effect journal |
| Agent declares completion early | Acceptance criteria require evidence |
| Replanning discards useful work | Preserve verified facts and completed prefix |
| Optimizer overfits its own tests | Separate training, validation, and protected suites |
| Same model confirms its own improvement | Deterministic checks and promotion authority outside the proposer |
| Aggregate score hides safety regression | Protected-suite veto and per-dimension metrics |
| Arbitrary self-editing weakens trust | Prompt/tool-description mutation allowlist only |
| Test suite looks green only locally | Fresh-clone CI with locked dependency resolution |

## Explicit Non-Goals

- arbitrary code rewriting;
- production credentials in tests;
- unrestricted shell or network tools;
- distributed queue infrastructure;
- model-weight fine-tuning;
- claims of state-of-the-art benchmark performance.

## Ticket Graph

1. Foundation: reproducible install and CI.
2. Durable task runtime: task/progress ledger, checkpoint/resume, idempotency.
3. Governed improvement: split isolation, promotion gate, lineage, rollback.
4. Operator proof: task timeline, promotion rationale, deterministic E2E.

Tickets 2 and 3 may run in parallel only after Ticket 1 is green and their file
ownership is non-overlapping. Ticket 4 starts after both backend contracts are
accepted.

## Completion Gate

- Every production behavior has observed red then green test evidence.
- Focused tests and full backend/frontend gates pass.
- API behavior is exercised without paid-model dependence.
- Review reports no blocking correctness, security, or trust-boundary findings.
- CI is green on the pushed GitHub commit.
- README claims match the shipped proof exactly.
