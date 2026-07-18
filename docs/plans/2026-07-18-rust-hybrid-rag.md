# Evidence-Grounded Research Agent: Phase 0

## Decision

Build one narrow, end-to-end research-agent proof that closes the exact job
requirements:

```text
source ingestion
  -> Python normalization, chunking, lineage, and embeddings
  -> Rust hybrid vector + lexical retrieval
  -> agent-driven durable research run
  -> Claude synthesis with stable citations
  -> deterministic grounding verifier
  -> inspectable trace, benchmark, and operator proof
```

Rust owns a measured retrieval hot path. Python owns orchestration, provider
adapters, durable task state, citations, and APIs. The existing governed prompt
improvement loop remains independent.

Do not build a generic vector database, arbitrary self-editing, or another
dashboard. Do not claim a 10/10 fit until every hard cap in this plan has
evidence.

## Target User And Job

Target user: the hiring manager seeking one engineer who has already shipped
agentic AI, Python APIs, RAG, semantic/vector search, Rust, and performance work.

Job to be done:

> Open one public repository and verify in five minutes that the agent can
> ingest real sources, find semantic evidence through runtime-invoked Rust,
> survive interruption, produce a Claude answer with citations, reject
> unsupported output, expose a redacted trace, and reproduce its performance
> claims.

## Current Baseline

The repository already has:

- a FastAPI/LangGraph tool loop and operator UI;
- OpenAI, Anthropic, and OpenAI-compatible model adapters;
- a durable task/progress ledger with idempotent effects and replanning;
- verifier-gated prompt candidate promotion, protected-suite veto, lineage, and
  rollback;
- backend, frontend, and Playwright tests in green CI.

Literal job-fit gaps:

- no document ingestion, embeddings, semantic model, vector index, or cited RAG;
- no Rust crate or runtime invocation;
- the task ledger is advanced by operator API calls rather than an agent worker;
- no Langfuse trace, production composition, or systems benchmark;
- no sanitized live Claude proof.

Baseline score under the strict job matrix: 59/100. This is a fit score, not a
general code-quality score.

## Exact Requirement Matrix

| Requirement | Weight | Required new evidence |
| --- | ---: | --- |
| Shipped agentic experience | 15 | Real research tool path and public green commit |
| Long-horizon + self-improvement | 15 | Agent-driven four-step run, crash/resume, effect exactly once; existing governed promotion retained |
| Python backend + APIs | 12 | Typed ingest, search, proof-run, status, and health contracts |
| Claude + LLM tooling | 8 | Live redacted Claude artifact plus provider-contract CI |
| RAG + semantic models + vector search | 15 | Source lineage, embeddings, Rust hybrid index, citations, grounding eval |
| Rust + real performance | 15 | Runtime-invoked crate, correctness oracle, release benchmark |
| Agent interface | 8 | Cohesive Proof Run UI exercised against the real stack |
| Production speed + observability | 12 | Langfuse, redaction, containers, health/recovery, CI and smoke proof |

## Architecture Decision

### Boundary

Use a PyO3/maturin extension named `adaptive_retrieval`.

Python responsibilities:

- validate tenant, source, model, and dimension contracts;
- normalize and chunk source text;
- call a real embedding-provider adapter;
- persist document/chunk lineage and stable citation IDs;
- invoke the Rust index and expose typed FastAPI endpoints;
- orchestrate plan, retrieve, synthesize, and verify checkpoints;
- propagate trace metadata and redact content by default.

Rust responsibilities:

- maintain a persistent index manifest with model, dimension, and index version;
- index lexical terms and normalized dense vectors;
- filter by tenant before scoring;
- execute BM25 and exact cosine search;
- fuse independent ranks with reciprocal-rank fusion;
- return per-leg score/rank provenance and stable chunk IDs;
- save atomically and reload deterministically;
- expose timing and corpus statistics to Python.

Why extension rather than sidecar:

- retrieval is a CPU-bound hot path where avoiding transport overhead is useful;
- the repository is currently a single FastAPI application;
- Python can use Rust synchronously inside a bounded worker thread;
- a compiled-but-unused crate is impossible because contract and Playwright tests
  require the native module;
- the index contract remains separable so a Qdrant or Rust service adapter can
  replace it at distributed scale.

The extension choice does not waive production requirements. Rust panics must
not cross the FFI boundary, blocking work must stay off the async event loop,
and health must identify missing or corrupt native state.

Build and runtime contract:

- `backend/pyproject.toml` uses maturin as its build backend and declares the
  native module explicitly;
- CI installs current stable Rust, caches Cargo, builds a locked release wheel,
  installs that wheel, and then runs Python and Playwright integration tests;
- CPU-bound native calls release the GIL with `Python::detach` and Python
  invokes them through a bounded `asyncio.to_thread` executor;
- every public FFI entry point contains panic isolation and maps typed failures
  to Python exceptions;
- the native module exposes a build/version fingerprint through health.

### Retrieval Semantics

- Dense leg: cosine similarity over normalized vectors.
- Lexical leg: BM25.
- Fusion: reciprocal-rank fusion over ranks, not raw scores with a fixed alpha.
- Filters: tenant and active index version are applied before scoring.
- Citations: `source_id`, `chunk_id`, `content_hash`, `embedding_model`, and
  `index_version` travel together.
- Retrieved text is untrusted data. It is delimited as evidence and cannot
  introduce agent instructions.
- No-hit and stale-index states fail closed.

### Persistence

Python stores canonical source and chunk lineage in the existing database. Rust
stores the search index under a configured data directory using an atomic
temporary-write and rename protocol. The Rust manifest is derived from Python
lineage and rejects model or dimension drift.

Deletion creates a new index version. Active readers see either the old complete
version or the new complete version, never a partial update.

The database and filesystem cannot share a transaction. Index construction is
therefore a recoverable two-phase state machine:

1. commit a `building` index generation and immutable corpus manifest;
2. build and fsync a versioned Rust snapshot;
3. verify manifest and checksum by reopening it;
4. atomically mark that generation `active` in the database.

On startup, `building` generations are either completed from canonical chunks or
marked failed. Orphaned snapshots are never served and may be garbage-collected
only after active-generation verification.

### Observability

Langfuse wraps every LLM call. A proof run carries:

- run/task ID;
- prompt version and hash;
- provider and model;
- embedding model and index version;
- Rust retrieval duration and candidate counts;
- token, cost, latency, and error metadata;
- citation IDs and verifier result.

Content capture is disabled by default. The committed live artifact stores only
safe metadata.

## Product Workflow

```text
Operator ingests inspectable sources
  -> lineage and embeddings recorded
  -> native index version becomes active

Operator starts proof run
  -> agent plans four bounded steps
  -> retrieve_knowledge calls Rust
  -> effect journal seals retrieval
  -> optional crash is injected
  -> worker resumes without repeating retrieval
  -> Claude synthesizes a cited answer
  -> verifier maps claims to chunk IDs
  -> unsupported completion is rejected
  -> UI shows checkpoints, citations, trace metadata, and benchmark context
```

## TDD Vertical Slices

### Slice 1: Native Retrieval Contract

Write failing tests first for:

- bounded calculator expressions and rejection of calls, attributes, names, and
  oversized inputs after removing Python `eval`;
- deterministic BM25, cosine, and RRF ordering;
- tenant filtering;
- model/dimension mismatch as typed errors;
- persistence and identical reload results;
- concurrent readers observing complete versions;
- brute-force cosine oracle parity.

Implement:

- safe AST-based arithmetic parser;
- Rust crate, typed errors, index manifest, search kernel, persistence;
- PyO3 boundary and Python protocol/reference implementation;
- release benchmark harness.

Proof gate:

- `cargo fmt --check`;
- `cargo clippy --all-targets --all-features --locked -- -D warnings`;
- `cargo test --locked`;
- Python native-contract suite;
- benchmark report generated from `--release`.

### Slice 2: Knowledge And Grounding

Write failing tests first for:

- stable source/chunk hashes and idempotent re-ingestion;
- real-provider adapter contract and deterministic fixture provider;
- semantic golden-suite recall at 3 of at least 90%;
- delete/re-index lineage;
- no-hit and stale-index behavior;
- retrieved prompt injection remaining inert;
- citation mismatch and unsupported answer rejection.

Implement:

- document/chunk/embedding lineage;
- ingest and hybrid search APIs;
- `retrieve_knowledge` agent tool;
- bounded excerpts and stable citations;
- grounding verifier.

Proof gate:

- backend focused tests, then full backend lint and tests;
- native module required by integration tests;
- committed three-source fixture and golden query suite.

### Slice 3: Autonomous Durable Research

Write failing tests first for:

- agent advances plan, retrieve, synthesize, and verify without manual calls;
- injected crash after retrieval resumes from the next checkpoint;
- retrieval effect count remains exactly one;
- lease prevents two workers from executing one step;
- stall replans only the unfinished suffix;
- budget exhaustion escalates;
- missing citation evidence blocks completion.

Implement:

- research-run worker connected to the existing ledger;
- bounded lease/heartbeat and recoverable failure states;
- proof-run API with deterministic fixture and live-Claude modes.

Proof gate:

- restart integration test;
- real native retrieval invocation;
- existing task and promotion regression suites remain green.

### Slice 4: Trace, UI, And Delivery

Write failing tests first for:

- Langfuse callback coverage and content redaction;
- correlation across orchestration, retrieval, generation, and verification;
- Rust-offline/corrupt-index, embedding failure, unauthorized, and resume states;
- keyboard navigation and mobile overflow;
- Playwright invoking FastAPI and compiled Rust without route mocks.

Implement:

- cohesive Proof Run surface;
- checkpoint/effect timeline, retrieved chunks, lineage, model, trace, and
  benchmark panels;
- deployable containers, health checks, restart behavior, and smoke command;
- README proof map and screenshots.

Proof gate:

- backend and frontend full gates;
- Playwright at 1440 by 900 and 390 by 844;
- React Doctor at least 90 with zero errors;
- one-command stack and health smoke;
- sanitized live Claude run if credentials are available;
- public CI green on the pushed commit.

## Performance Protocol

Correctness comes before speed.

- Fixed seeded corpus with documented count and dimensions.
- Python reference and Rust implementation consume identical normalized vectors
  and queries.
- Validate result parity before measuring.
- Release build, warmups excluded, at least 30 measured trials.
- Report CPU, RAM, OS, corpus, dimensions, concurrency, top-k, p50, p95, p99,
  throughput, peak RSS, and commit.
- Target: at least 3 times Python-reference throughput at 100,000 vectors by 768
  dimensions, top 10, concurrency 16.
- CI checks correctness and a generous absolute ceiling only. It does not fail on
  a hardware-sensitive speedup ratio.

## Security And Failure Controls

| Risk | Control |
| --- | --- |
| Retrieved prompt injection | Treat chunks as delimited untrusted evidence; deterministic adversarial test |
| Cross-tenant leakage | Filter before scoring; negative integration test |
| Stale or mixed embeddings | Model/dimension/index manifest; typed rejection |
| Partial index update | Atomic version activation |
| Rust panic crashes Python | Panic-safe FFI and typed exception mapping |
| CPU work blocks event loop | Run native search/ingest in bounded worker thread |
| Python and Rust persistence diverge | Recoverable two-phase generation activation and startup reconciliation |
| Duplicate effect after crash | Existing idempotency journal plus restart test |
| Unsupported model answer | Claim-to-citation verifier blocks completion |
| Trace leaks content | Metadata-only by default; redaction tests |
| Benchmark theater | Fixed protocol, parity gate, hardware disclosure |
| Calculator code execution | Remove `eval` in Slice 1; bounded AST parser with adversarial tests |
| README overclaim | Final claim-to-evidence audit |

## Explicit Non-Goals

- approximate-nearest-neighbor index engineering;
- distributed replication or consensus;
- arbitrary code self-modification;
- unrestricted web crawling;
- model fine-tuning;
- claims that deterministic fixture embeddings are production semantic models;
- forcing a public deployment when no deployment target was authorized.

## Five-Minute Proof

1. Open README proof map and green CI.
2. Start the one-command stack; show Python, Rust, and index health.
3. Ingest three sources and run a semantic query with score/lineage.
4. Start an agent-driven four-step research task.
5. Inject a crash after retrieval; restart and show one effect.
6. Produce a Claude cited answer; show the grounding verdict.
7. Open the redacted Langfuse trace metadata.
8. Show recall and Rust-versus-Python p50/p95/p99/throughput evidence.
9. Show a protected prompt candidate rejection and rollback.

## Hard Score Caps

- no runtime-invoked compiled Rust: 70 maximum;
- no real semantic retrieval path: 75 maximum;
- no agent-driven crash/resume: 82 maximum;
- no verified Claude run: 90 maximum;
- no Claude to Rust retrieval to cited-answer trace: 94 maximum;
- no reproducible latency/throughput evidence: 96 maximum;
- no deployable stack and smoke proof: 97 maximum;
- no Langfuse trace/redaction proof: 98 maximum;
- red CI, leaked secret, or unsupported README claim: ship blocker.

## Completion Gate

- Phase 0 independently reviewed before implementation.
- Every slice preserves representative red then green evidence.
- Every hard-cap requirement has a code, test, command, artifact, or UI anchor.
- Full Rust, backend, frontend, Playwright, container, and documentation gates
  pass.
- Independent final review reports no blocking correctness, security,
  performance, or trust-boundary issue.
- GitHub CI is green on the pushed commit.
- If live credentials or a deployment target are unavailable, the final score is
  honestly capped and the exact missing proof is reported.
