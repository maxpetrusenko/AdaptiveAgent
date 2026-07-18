# Rust Hybrid RAG: Documentation Plan

## Audience

- Hiring manager evaluating the repository in five minutes.
- Engineer cloning the project and reproducing the proof locally.
- Maintainer changing the retrieval, tracing, or durable-run contracts.

## Required Artifacts

| Artifact | Purpose | Completion proof |
| --- | --- | --- |
| Phase 0 plan | Freeze product, architecture, risks, and acceptance criteria before code | Reviewed before implementation |
| README proof map | Map every job requirement to a command, test, UI surface, or artifact | No unsupported claim |
| Architecture note | Explain Python/Rust boundary, data lineage, trust boundaries, and failure modes | Matches shipped contracts |
| API reference | Document ingest, search, proof-run, health, and error contracts | Examples execute locally |
| Performance report | Record corpus, dimensions, hardware, warmups, samples, percentiles, throughput, RSS, and commit | Reproducible command committed |
| TDD evidence log | Preserve representative red and green commands for every vertical slice | Each slice has a failing test before implementation |
| Live-run template | Record model, trace, tokens, latency, citations, and verifier result without content or secrets | Safe to commit |

## Documentation Sequence

1. Write and review this Phase 0 package.
2. Add API and architecture details with the first green contract slice.
3. Update the README proof map only when corresponding tests pass.
4. Generate the performance report from a release build.
5. Capture desktop and mobile proof after real-stack Playwright passes.
6. Run a final claim-to-evidence audit before push.

## Claim Rules

- “Semantic retrieval” requires a real embedding-provider adapter and a tested
  vector path. Deterministic embeddings are labeled as test fixtures.
- “Rust-powered” requires the application and E2E path to invoke the compiled
  Rust component.
- “Long-horizon” requires an agent worker, not manual operator advancement.
- “Claude verified” requires a sanitized live-run artifact.
- “Production-ready” requires deployable containers, health checks, bounded
  failures, tracing, and documented configuration. A local-only proof is
  labeled local-only.
- Benchmarks always name hardware, corpus, build profile, sample count, and
  commit. Hardware-sensitive ratios are evidence, not flaky CI thresholds.

