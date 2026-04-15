# Benchmarking

## Goal

Prove the agent is adaptive with numbers, not screenshots.

The benchmark runner does three things:

1. repeated baseline evals on the current active prompt
2. one full adaptation run
3. repeated post-adaptation evals on the new active prompt

It writes a JSON report with:

- baseline mean/std pass rate
- post-adaptation mean/std pass rate
- accepted/rejected adaptation decision
- prompt version change
- per-run hallucination and protected-case failures
- per-tag pass rates

## Why this shape

Based on recent self-improvement/eval work:

- SICA: adaptation must be verified, not just generated
- SelfCheckGPT: consistency is useful as a verifier signal
- recent agent benchmark work highlights variance across runs, so repeated runs matter

Practical takeaway:

- stronger verifier
- repeated measurement
- protected-suite no-regression gate

## Prerequisites

- `backend/.env` with `ANTHROPIC_API_KEY`
- backend deps installed
- seeded DB available

## Run

From `backend/`:

```bash
python -m app.benchmarks.run --repeats 3 --out benchmark-results/latest.json
```

Or via the installed script:

```bash
adaptive-agent-benchmark --repeats 3 --out benchmark-results/latest.json
```

## Read the result

Good result:

- `adaptation.accepted = true`
- `delta.active_prompt_changed = true`
- `delta.mean_pass_rate_delta > 0`
- post-adaptation std not exploding
- protected failures not increasing

Bad result:

- adaptation rejected
- prompt unchanged
- no meaningful pass-rate delta
- protected or hallucination regressions

## Suggested benchmark cadence

- `--repeats 3` for quick iteration
- `--repeats 5` before claiming improvement
- compare JSON reports over time, not one-off best runs
