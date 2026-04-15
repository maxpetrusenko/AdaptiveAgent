# Benchmarking

## Goal

Prove the agent is adaptive with numbers, not screenshots.

There are now two benchmark modes:

1. `run.py`: single-system regression and adaptation benchmark
2. `compare.py`: comparative leaderboard against baselines on a held-out suite

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

- `backend/.env` with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- backend deps installed
- seeded DB available

Provider selection:

- `MODEL_PROVIDER=auto` uses OpenAI first when available, then Anthropic
- `MODEL_PROVIDER=openai` forces OpenAI
- `MODEL_PROVIDER=anthropic` forces Anthropic

## Run

From `backend/`:

```bash
python -m app.benchmarks.run --repeats 3 --out benchmark-results/latest.json
```

Or via the installed script:

```bash
adaptive-agent-benchmark --repeats 3 --out benchmark-results/latest.json
```

Comparative benchmark:

```bash
adaptive-agent-compare --out benchmark-results/compare.json
```

If the default suite is already saturated, prove the loop itself on a stress baseline:

```bash
adaptive-agent-benchmark \
  --stress-baseline tool-agnostic \
  --case-tag tool-use \
  --repeats 1 \
  --consistency-repeats 0 \
  --out benchmark-results/stress-tool-use.json
```

That mode starts from a deliberately weak active prompt inside the benchmark DB only. It does not change your real app prompt unless you point the benchmark at your main DB file.

## Read the result

Good result:

- `adaptation.accepted = true`
- `delta.active_prompt_changed = true`
- `delta.mean_pass_rate_delta > 0`
- post-adaptation std not exploding
- protected failures not increasing

Good comparative result:

- `adaptive_agent` beats `direct_llm`
- `adaptive_agent` beats `weak_static_agent`
- `adaptive_agent` closes the gap to `seed_tool_agent`
- pairwise deltas are positive on the held-out split

Bad result:

- adaptation rejected
- prompt unchanged
- no meaningful pass-rate delta
- protected or hallucination regressions

## Suggested benchmark cadence

- `--repeats 3` for quick iteration
- `--repeats 5` before claiming improvement
- compare JSON reports over time, not one-off best runs
- use `compare.py` when you need a leaderboard, not just a single-system health check
