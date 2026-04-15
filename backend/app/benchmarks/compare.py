"""Comparative benchmark for adaptive-agent baselines.

Benchmarks multiple systems on a held-out split:
- direct_llm: plain chat model, no tools
- weak_static_agent: tool-capable agent with an intentionally bad prompt
- adaptive_agent: same weak prompt, then adapts on train split before test
- seed_tool_agent: tool-capable agent with the repo's default prompt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapt.loop import create_adaptation_run, run_adaptation_loop
from app.agent.graph import run_agent
from app.agent.prompts import SYSTEM_PROMPT_V1
from app.eval.checks import check_deterministic, check_hallucination, check_pass_fail
from app.llm import build_chat_model
from app.models import Base, EvalCase, PromptVersion

WEAK_TOOL_PROMPT = """You are an adaptive AI assistant.

Rules:
- Never call any tools.
- For time questions, say you do not have live time access.
- For arithmetic, answer from mental math only.
- Keep answers short and confident.
"""

DIRECT_LLM_PROMPT = """You are a concise, helpful assistant.

Answer directly. If you cannot verify something current, say so plainly.
"""


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    input: str
    expected_output: str
    tags: tuple[str, ...]
    split: str


@dataclass
class CaseResult:
    case_name: str
    status: str
    score: float
    error: str | None
    actual_output: str
    latency_ms: int


@dataclass
class SystemSummary:
    system: str
    pass_rate: float
    passed: int
    failed: int
    avg_latency_ms: float
    hallucination_failures: int
    tag_pass_rates: dict[str, float]
    results: list[CaseResult]
    metadata: dict


SUITE = [
    BenchmarkCase(
        name="Train current time",
        input="What time is it right now?",
        expected_output="The current UTC time",
        tags=("tool-use", "time", "train"),
        split="train",
    ),
    BenchmarkCase(
        name="Train arithmetic",
        input="What is 15 * 23 + 42?",
        expected_output="387",
        tags=("tool-use", "math", "train"),
        split="train",
    ),
    BenchmarkCase(
        name="Train multi-step math",
        input="A train travels at 60 mph for 2 hours, then 80 mph for 1.5 hours. Total distance?",
        expected_output="240 miles",
        tags=("tool-use", "math", "reasoning", "train"),
        split="train",
    ),
    BenchmarkCase(
        name="Eval current time",
        input="What time is it in UTC right now?",
        expected_output="The current UTC time",
        tags=("tool-use", "time", "eval"),
        split="eval",
    ),
    BenchmarkCase(
        name="Eval arithmetic",
        input="What is 99 * 17 - 3?",
        expected_output="1680",
        tags=("tool-use", "math", "eval"),
        split="eval",
    ),
    BenchmarkCase(
        name="Eval decimal arithmetic",
        input="What is 12.5 * 8?",
        expected_output="100",
        tags=("tool-use", "math", "eval"),
        split="eval",
    ),
]


async def _seed_cases(db, prompt_text: str) -> None:
    db.add(
        PromptVersion(
            version=1,
            content=prompt_text,
            is_active=True,
            change_reason="Benchmark seed prompt",
        )
    )
    for case in SUITE:
        db.add(
            EvalCase(
                name=case.name,
                input=case.input,
                expected_output=case.expected_output,
                tags=list(case.tags),
                source="manual",
            )
        )
    await db.commit()


async def _load_cases(db, split: str) -> list[EvalCase]:
    cases = (await db.execute(select(EvalCase).order_by(EvalCase.name.asc()))).scalars().all()
    return [
        case
        for case in cases
        if isinstance(case.tags, list) and split in case.tags
    ]


async def _evaluate_cases(cases: list[EvalCase], runner) -> SystemSummary:
    results: list[CaseResult] = []
    passed = 0
    failed = 0
    latency_total = 0
    hallucination_failures = 0
    tag_counts: dict[str, int] = {}
    tag_pass_counts: dict[str, int] = {}

    for case in cases:
        start = time.perf_counter()
        try:
            system_result = await runner(case.input)
            actual_output = system_result["content"]
            tool_results = system_result.get("tool_results")

            check_result = check_deterministic(case.expected_output, actual_output)
            if check_result is None:
                check_result = await check_pass_fail(case.input, case.expected_output, actual_output)

            hallucination = await check_hallucination(
                case.input,
                actual_output,
                tool_results=tool_results,
            )

            status = "pass" if check_result["pass"] else "fail"
            error = None if check_result["pass"] else check_result["reason"]

            if hallucination["has_hallucination"]:
                hallucination_failures += 1
                status = "fail"
                halluc_detail = f"Hallucination: {hallucination['details']}"
                error = halluc_detail if error is None else f"{error} | {halluc_detail}"

            latency_ms = int((time.perf_counter() - start) * 1000)
            latency_total += latency_ms
            if status == "pass":
                passed += 1
            else:
                failed += 1

            for tag in case.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
                if status == "pass":
                    tag_pass_counts[tag] = tag_pass_counts.get(tag, 0) + 1

            results.append(
                CaseResult(
                    case_name=case.name,
                    status=status,
                    score=float(check_result["score"]),
                    error=error,
                    actual_output=actual_output,
                    latency_ms=latency_ms,
                )
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            latency_total += latency_ms
            failed += 1
            for tag in case.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            results.append(
                CaseResult(
                    case_name=case.name,
                    status="error",
                    score=0.0,
                    error=str(exc),
                    actual_output="",
                    latency_ms=latency_ms,
                )
            )

    tag_pass_rates = {
        tag: tag_pass_counts.get(tag, 0) / total
        for tag, total in sorted(tag_counts.items())
    }

    return SystemSummary(
        system="",
        pass_rate=passed / len(cases) if cases else 0.0,
        passed=passed,
        failed=failed,
        avg_latency_ms=latency_total / len(cases) if cases else 0.0,
        hallucination_failures=hallucination_failures,
        tag_pass_rates=tag_pass_rates,
        results=results,
        metadata={},
    )


async def _run_direct_llm_benchmark() -> SystemSummary:
    model = build_chat_model(purpose="agent", streaming=False)
    eval_cases = [case for case in SUITE if case.split == "eval"]

    async def runner(input_text: str) -> dict:
        response = await model.ainvoke(
            [
                SystemMessage(content=DIRECT_LLM_PROMPT),
                HumanMessage(content=input_text),
            ]
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        return {"content": content, "tool_results": None}

    db_cases = [
        EvalCase(
            name=case.name,
            input=case.input,
            expected_output=case.expected_output,
            tags=list(case.tags),
            source="manual",
        )
        for case in eval_cases
    ]
    summary = await _evaluate_cases(db_cases, runner)
    summary.system = "direct_llm"
    summary.metadata = {"prompt": "DIRECT_LLM_PROMPT", "adapted": False}
    return summary


async def _run_tool_agent_benchmark(system_name: str, prompt_text: str) -> SystemSummary:
    eval_cases = [
        EvalCase(
            name=case.name,
            input=case.input,
            expected_output=case.expected_output,
            tags=list(case.tags),
            source="manual",
        )
        for case in SUITE
        if case.split == "eval"
    ]

    async def runner(input_text: str) -> dict:
        return await run_agent(
            messages=[{"role": "user", "content": input_text}],
            system_prompt=prompt_text,
        )

    summary = await _evaluate_cases(eval_cases, runner)
    summary.system = system_name
    summary.metadata = {"adapted": False}
    return summary


async def _run_adaptive_agent_benchmark() -> SystemSummary:
    with TemporaryDirectory(prefix="adaptive-agent-compare-") as tmpdir:
        db_path = Path(tmpdir) / "compare.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as db:
            await _seed_cases(db, WEAK_TOOL_PROMPT)
            train_cases = await _load_cases(db, "train")
            eval_cases = await _load_cases(db, "eval")

            adapt_run = await create_adaptation_run(db)
            adapt_run = await run_adaptation_loop(
                db,
                adapt_run.id,
                case_ids=[case.id for case in train_cases],
                consistency_repeats=0,
            )

            prompt = (
                await db.execute(
                    select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
                )
            ).scalar_one()

            async def runner(input_text: str) -> dict:
                return await run_agent(
                    messages=[{"role": "user", "content": input_text}],
                    system_prompt=prompt.content,
                )

            summary = await _evaluate_cases(eval_cases, runner)
            summary.system = "adaptive_agent"
            summary.metadata = {
                "adapted": True,
                "accepted": adapt_run.accepted,
                "before_pass_rate": adapt_run.before_pass_rate,
                "after_pass_rate": adapt_run.after_pass_rate,
                "prompt_version": prompt.version,
            }

        await engine.dispose()

    return summary


def _pairwise_delta(left: SystemSummary, right: SystemSummary) -> dict:
    left_results = {result.case_name: result.status for result in left.results}
    right_results = {result.case_name: result.status for result in right.results}
    wins = 0
    losses = 0
    ties = 0

    for case_name, left_status in left_results.items():
        right_status = right_results.get(case_name)
        left_pass = left_status == "pass"
        right_pass = right_status == "pass"
        if left_pass and not right_pass:
            wins += 1
        elif right_pass and not left_pass:
            losses += 1
        else:
            ties += 1

    return {
        "pass_rate_delta": left.pass_rate - right.pass_rate,
        "wins": wins,
        "losses": losses,
        "ties": ties,
    }


def _render_leaderboard(summaries: list[SystemSummary], pairwise: dict[str, dict]) -> str:
    ordered = sorted(summaries, key=lambda item: (-item.pass_rate, item.avg_latency_ms))
    lines = ["Leaderboard:"]
    for idx, summary in enumerate(ordered, start=1):
        lines.append(
            f"{idx}. {summary.system}: "
            f"pass_rate={summary.pass_rate:.1%}, "
            f"avg_latency_ms={summary.avg_latency_ms:.0f}, "
            f"hallucinations={summary.hallucination_failures}"
        )
    lines.append("")
    lines.append("Adaptive deltas:")
    for name, delta in pairwise.items():
        lines.append(
            f"- adaptive_agent vs {name}: "
            f"delta={delta['pass_rate_delta']:.1%}, "
            f"wins={delta['wins']}, losses={delta['losses']}, ties={delta['ties']}"
        )
    return "\n".join(lines)


async def run_compare_benchmark() -> dict:
    direct_llm = await _run_direct_llm_benchmark()
    weak_static_agent = await _run_tool_agent_benchmark("weak_static_agent", WEAK_TOOL_PROMPT)
    adaptive_agent = await _run_adaptive_agent_benchmark()
    seed_tool_agent = await _run_tool_agent_benchmark("seed_tool_agent", SYSTEM_PROMPT_V1)

    summaries = [direct_llm, weak_static_agent, adaptive_agent, seed_tool_agent]
    pairwise = {
        summary.system: _pairwise_delta(adaptive_agent, summary)
        for summary in summaries
        if summary.system != "adaptive_agent"
    }

    report = {
        "suite": {
            "train_cases": [asdict(case) for case in SUITE if case.split == "train"],
            "eval_cases": [asdict(case) for case in SUITE if case.split == "eval"],
        },
        "systems": [
            {
                **asdict(summary),
                "results": [asdict(result) for result in summary.results],
            }
            for summary in summaries
        ],
        "pairwise": pairwise,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run comparative adaptive-agent benchmark")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("benchmark-results/compare.json"),
        help="Path to JSON benchmark report",
    )
    return parser


async def _async_main() -> int:
    args = build_parser().parse_args()
    report = await run_compare_benchmark()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    summaries = [
        SystemSummary(
            system=item["system"],
            pass_rate=item["pass_rate"],
            passed=item["passed"],
            failed=item["failed"],
            avg_latency_ms=item["avg_latency_ms"],
            hallucination_failures=item["hallucination_failures"],
            tag_pass_rates=item["tag_pass_rates"],
            results=[CaseResult(**result) for result in item["results"]],
            metadata=item["metadata"],
        )
        for item in report["systems"]
    ]
    print(_render_leaderboard(summaries, report["pairwise"]))
    print(f"\nBenchmark report written to {args.out}")
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
