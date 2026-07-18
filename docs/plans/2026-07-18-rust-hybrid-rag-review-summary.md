# Rust Hybrid RAG: Phase 0 Review Summary

## Reviews

Three independent inputs shaped the plan:

1. Repository gap audit: the durable ledger is operator-driven; RAG, Rust,
   tracing, deployment, and systems performance are absent.
2. Strict job rubric: current literal fit is 59/100 and hard caps prevent a
   truthful 10/10 without runtime Rust, real semantic retrieval, autonomous
   crash/resume, Claude proof, tracing, benchmark evidence, and a deployable
   stack.
3. Rust/RAG architecture research: Rust should own a real retrieval hot path;
   rank-based hybrid fusion is safer than mixing incomparable raw scores.
4. Gemini architecture gate: NO-GO until the maturin build/CI contract,
   event-loop and panic isolation, split-persistence recovery, tracing
   dependency, and exposed `eval` removal are explicit acceptance requirements.

## Decisions

- One evidence-grounded research path, not broad feature expansion.
- PyO3/maturin extension, not a network sidecar, for the current monolith.
- Python owns model/provider and durable orchestration contracts.
- Rust owns persistence, BM25, exact cosine, tenant filtering, and RRF.
- Exact search first because it produces a simple correctness oracle and honest
  benchmark. Approximate search is future scale work.
- Qdrant remains a documented adapter direction, not a default dependency.
- Langfuse metadata tracing is required and content is redacted by default.
- Live Claude and public deployment remain proof gates, not assumptions.
- Native build/install runs before Python and Playwright integration tests.
- GIL release, bounded Python offload, and FFI panic mapping are mandatory.
- Index activation uses a recoverable two-phase generation state machine.

## Scope Challenges Accepted

- Add an autonomous worker because manual task advancement does not prove a
  long-horizon agent.
- Replace the `eval` calculator before a production-ready claim.
- Require the compiled Rust path in integration and Playwright tests.
- Preserve the existing governed self-improvement loop rather than adding
  unsafe arbitrary self-editing.

## Open Proof Dependencies

- A configured Anthropic key is required for the sanitized live-Claude artifact.
- An explicitly authorized deployment target is required for independently
  reachable production proof.
- Hardware-sensitive performance results will be recorded after release-build
  implementation; the plan does not pre-claim the target ratio.

## Review Outcome

The second-model NO-GO findings are now represented as blocking acceptance
criteria. Phase 0 is ready for ticket creation. Implementation may start with
tests for the safe calculator and native contract; the final gate remains NO-GO
until all findings are green.
