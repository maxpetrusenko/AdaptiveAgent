# Benchmarking

## Goal

Prove the agent is adaptive with numbers, not screenshots.

Current proof claim:

- The agent improves when the starting prompt is weak and failures are measurable.
- The agent does not accept prompt churn on saturated suites.
- The adaptive agent catches up to strong tool-using baselines on the smoke suite.

Current non-claim:

- This is not proof of state-of-the-art performance against external products.
- This is not proof of code-level self-modification.
- This is not a large public benchmark result.

There are now two benchmark modes:

1. `run.py`: single-system regression and adaptation benchmark
2. `compare.py`: comparative leaderboard against baselines on a held-out suite

The single-system benchmark runner does three things:

1. repeated baseline evals on the current active prompt
2. one full adaptation run
3. repeated post-adaptation evals on the new active prompt

`run.py` writes a JSON report with:

- baseline mean/std pass rate
- post-adaptation mean/std pass rate
- accepted/rejected adaptation decision
- prompt version change
- per-run hallucination and protected-case failures
- per-tag pass rates
- sibling HTML report with charts

## Why this shape

Based on recent self-improvement/eval work:

- SICA: adaptation must be verified, not just generated
- SelfCheckGPT: consistency is useful as a verifier signal
- recent agent benchmark work highlights variance across runs, so repeated runs matter

Practical takeaway:

- stronger verifier
- repeated measurement
- protected-suite no-regression gate

`compare.py` now adds:

- 40+ held-out eval cases across tool use, reasoning, factual recall, safety, uncertainty, privacy, retrieval, prompt-injection, and multi-turn behavior
- one external-style baseline: `sdk_tool_agent`, a provider-SDK manual tool loop outside the repo's LangGraph agent
- repeated-run means, std, and bootstrap 95 percent confidence intervals
- sequential multi-cycle adaptation trajectories
- explicit gain, stability, and alignment-convergence fields
- judge calibration on a 56-case labeled set with exact duplicate checks in tests
- adversarial harness checks for null-agent and judge-injection failures
- exact sign tests on adaptive-vs-baseline win/loss counts
- sibling HTML report with charts and a benchmark-results index page

## Prerequisites

- `backend/.env` with `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- backend deps installed
- seeded DB available

Provider selection:

- `MODEL_PROVIDER=auto` uses an available OpenAI-compatible local/proxy endpoint first, then OpenAI, then Anthropic
- `MODEL_PROVIDER=openai` forces OpenAI
- `MODEL_PROVIDER=anthropic` forces Anthropic
- `MODEL_PROVIDER=ollama` forces the OpenAI-compatible local/proxy path

## Run

From `backend/`:

```bash
python -m app.benchmarks.run --repeats 3 --out benchmark-results/latest.json
```

Or via the installed script:

```bash
adaptive-agent-benchmark --repeats 3 --out benchmark-results/latest.json
```

Render HTML for all benchmark JSON artifacts in the directory:

```bash
adaptive-agent-benchmark-html --dir benchmark-results
```

Comparative benchmark:

```bash
adaptive-agent-compare \
  --repeats 3 \
  --adaptation-cycles 3 \
  --out benchmark-results/compare.json
```

Quick smoke run:

```bash
adaptive-agent-compare \
  --repeats 1 \
  --adaptation-cycles 1 \
  --max-train-cases 4 \
  --max-eval-cases 8 \
  --out benchmark-results/compare-smoke.json
```

Judge calibration only:

```bash
adaptive-agent-judge-calibration
```

Adversarial harness only:

```bash
adaptive-agent-adversarial --max-cases 12
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

Start here:

- `backend/benchmark-results/index.html`

That page is the human-first benchmark storyboard:

- short answer first
- one-line summary across runs
- strongest live proof first
- tabs for raw per-run reports only after the summary

Read it as a simple story:

- `compare-smoke-live`: adaptive recovery from weak baseline to strong baseline quality
- `stress-live`: accepted prompt update improves a weak setup
- `fast` and `full`: already saturated, so no prompt change is accepted
- old partial artifacts are not the core proof

Use the standalone HTML pages when you want the raw charts for one run:

- `compare-smoke-live.html`
- `stress-live.html`
- `fast.html`
- `full.html`

Good result:

- `adaptation.accepted = true`
- `delta.active_prompt_changed = true`
- `delta.mean_pass_rate_delta > 0`
- post-adaptation std not exploding
- protected failures not increasing

Good comparative result:

- `adaptive_agent` beats `direct_llm`
- `adaptive_agent` beats `weak_static_agent`
- `adaptive_agent` beats `sdk_tool_agent` or at least explains the gap
- `adaptive_agent` closes the gap to `seed_tool_agent`
- pairwise deltas are positive on the held-out split
- sign tests on win/loss counts are directionally supportive
- adaptive trajectory improves or stays flat across cycles
- protected failures and hallucinations do not regress
- null agent and injection agent stay at or near zero pass rate
- judge calibration mismatches are rare and inspectable

Bad result:

- adaptation rejected
- prompt unchanged
- no meaningful pass-rate delta
- protected or hallucination regressions
- null agent gets credit for cases
- injection agent meaningfully changes scores
- judge calibration disagrees with obvious labeled cases

## Suggested benchmark cadence

- `--repeats 3` for quick iteration
- `--repeats 5` before claiming improvement
- `--adaptation-cycles 3` is the default research pass
- use `--max-eval-cases` and `--max-train-cases` for smoke runs only
- compare JSON reports over time, not one-off best runs
- use `compare.py` when you need a leaderboard, not just a single-system health check
