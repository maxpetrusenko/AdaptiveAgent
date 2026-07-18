# TDD Red-Green Evidence

Representative evidence from the evidence-grounded research-agent slices. Full
commands are rerun at the final gate; transient red output is summarized here so
the repository does not merge failing commits.

## Safe Calculator

Red:

```bash
cd backend
uv run pytest -q tests/test_agent_tools.py
```

The adversarial tool test failed because the public calculator still executed
Python `eval` and returned Python's name-resolution error.

Green:

```text
18 passed
All checks passed!
```

Command:

```bash
uv run pytest -q tests/test_agent_tools.py tests/test_safe_math.py
uv run ruff check app/agent/tools.py app/safe_math.py \
  tests/test_agent_tools.py tests/test_safe_math.py
```

## Langfuse And Trace Safety

Red:

- provider-neutral observability tests failed collection because the package did
  not exist;
- the Langfuse adapter test failed collection because
  `app.observability.langfuse` did not exist;
- the shared-model test failed because model constructors had no callbacks;
- the memory-case test failed because it constructed `ChatAnthropic` directly.

Green:

```text
15 passed
All checks passed!
```

The shared factory now attaches the optional Langfuse callback, export masking
removes content attributes by default, and the direct Anthropic call uses the
same factory.

## Rust Hybrid Retrieval

Red:

```bash
cd native/adaptive_retrieval
cargo test --test hybrid_contract
```

Five contract tests failed against explicit `NotImplemented` stubs.

Green:

```text
1 unit test passed
6 integration tests passed
```

Commands:

```bash
cargo fmt --check
cargo clippy --all-targets --all-features --locked -- -D warnings
cargo test --locked
```

A release ABI3 wheel also passed an isolated Python build/import/search smoke.

## Knowledge, Grounding, And Native Boundary

Red:

- six focused slices first failed import or contract checks;
- a no-hit edge case exposed cancellation to a zero deterministic vector;
- native wrapper and benchmark tests failed collection before their modules
  existed.

Green:

```text
33 knowledge tests passed
4 benchmark harness tests passed
All targeted Ruff checks passed
```

Additional red tests reproduced two release-blocking races: overlapping
generation preparations could lose a source, and reverse native-build
completion could leave the in-memory manifest behind canonical SQLite state.
An embedding fingerprint upgrade also retained stale vectors under the new
manifest.

The green path serializes canonical mutations, composes compatible generations,
drops incompatible vectors, fences late activation, and reconciles the loaded
native generation. The real ABI3 round trip passed. The benchmark now refuses
to time a candidate until Python and Rust ranked IDs, per-leg ranks, and dense
scores have parity. The recorded 10,000-chunk run compared 50 ranked hits before
reporting latency.

An independent release audit then reproduced a search observing a shared native
retriever between replacement and canonical activation. The final access lock
now spans native replacement, SQLite activation, reconciliation, and every
search snapshot. A two-manager regression proves search returns only the old
committed generation or the new committed generation, never the building one.

## Autonomous Research Runner

Red:

- initial runner tests failed collection because `app.research` did not exist;
- hardening tests observed zero lease renewals and allowed fabricated citations
  to reach the verifier;
- persistence/API tests failed before SQLite adapters and router existed.
- a two-worker regression reproduced duplicate slow-effect execution after the
  original 200 ms lease expired.

Green:

```text
27 research tests passed
All checks passed!
```

Proof covers four autonomous steps, sealed-effect crash/resume, one retrieval
effect, heartbeat renewal during blocking providers, monotonic fencing tokens,
tenant-scoped leases, suffix-only replan, budget escalation, and fail-closed
citation evidence.

Mode lineage is also durable: execution mode and adapter fingerprint are stored
with the run, included in effect keys, and revalidated on resume. A
deterministic-to-live resume attempt now fails with 409 instead of reusing
cross-mode effects. Exact retrieval hash, index, embedding, score, and rank
lineage is decoded intact after every checkpoint and repository restart.

## Proof Interface And Server Boundary

Red:

- the first browser proof run was missing a route and coordinator files;
- independent review showed that deterministic fixture synthesis was displayed
  beside unrelated native hits as if it were one live grounded run;
- the browser called protected backend mutations directly, so the Compose
  network could not authorize the proof safely;
- the first real Playwright assertion counted a heading plus the four step
  attempts.

Green:

```text
7 focused Vitest tests passed
2 real Playwright proof tests passed
```

The UI now seals an explicit deterministic or live mode. Fixture mode labels
native search as a separate inspection; only verified live mode claims grounded
model output. A narrow same-origin Next.js route adds the operator token only on
the server. Playwright executes ingest, compiled Rust search, controlled
post-retrieval interruption, resume, exactly-once evidence, and mobile overflow
checks without route mocks.

## Frontend Runtime And Full Integration

Red:

- unmount tests observed both polling pages leaving live intervals behind;
- server-rendering the confirmation dialog read `document.body`;
- deterministic date-format tests failed before the UTC formatter existed;
- the full 18-test browser suite exposed legacy clients still targeting port
  8000 while the isolated test backend ran on 8017.

Green:

```text
51 Vitest tests passed
18 Playwright tests passed
Next.js 16.2.10 production build passed
React Doctor changed-file score: 85, zero errors or security warnings
```

Pollers now clear their intervals, modal rendering is server-safe, dates use an
explicit locale and timezone, and Playwright injects one build-time backend URL
for both legacy clients and the server-only proof proxy.

The final security slice routes protected browser mutations through an exact
server-side allowlist. Both operator and proof proxies attach secrets only on
the server and fail closed unless explicit local mode, loopback host, and
same-origin fetch metadata are present. Live evidence cards now render only the
verifier-approved chunks sealed in the run, including their original hash,
index, embedding, and rank lineage; they never substitute a later search.
