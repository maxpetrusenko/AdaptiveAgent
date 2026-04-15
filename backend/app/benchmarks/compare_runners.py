"""Execution helpers for the comparative benchmark."""

from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapt.loop import create_adaptation_run, run_adaptation_loop
from app.agent.graph import run_agent
from app.agent.tools import calculator, current_time
from app.benchmarks.compare_metrics import bootstrap_ci
from app.benchmarks.compare_suite import BenchmarkCase
from app.benchmarks.compare_types import CaseResult, SystemSummary
from app.eval.checks import check_deterministic, check_hallucination, check_pass_fail
from app.llm import build_chat_model
from app.models import Base, EvalCase, PromptVersion

TOOLS = [calculator, current_time]
TOOL_BY_NAME = {tool.name: tool for tool in TOOLS}


def extract_usage(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        usage = payload.get("usage")
        if isinstance(usage, dict):
            return {
                key: value
                for key, value in usage.items()
                if isinstance(value, (int, float))
            }
        return None

    for attr_name in ("usage", "usage_metadata", "response_metadata"):
        value = getattr(payload, attr_name, None)
        if isinstance(value, dict):
            usage = value.get("token_usage") if attr_name == "response_metadata" else value
            if isinstance(usage, dict):
                return {
                    key: value
                    for key, value in usage.items()
                    if isinstance(value, (int, float))
                }
    return None


def merge_usage(current: dict[str, float], usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            current[key] = current.get(key, 0.0) + float(value)


def case_messages(case: BenchmarkCase) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in case.messages]


def langchain_messages(
    case: BenchmarkCase,
    *,
    system_prompt: str,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=system_prompt)
    ]
    for role, content in case.messages:
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


async def evaluate_cases(cases: list[BenchmarkCase], runner) -> SystemSummary:
    results: list[CaseResult] = []
    passed = 0
    failed = 0
    latency_total = 0
    hallucination_failures = 0
    tag_counts: dict[str, int] = {}
    tag_pass_counts: dict[str, int] = {}
    pass_values: list[float] = []
    usage_totals: dict[str, float] = {}

    for case in cases:
        start = time.perf_counter()
        try:
            system_result = await runner(case)
            actual_output = system_result["content"]
            tool_results = system_result.get("tool_results")
            usage = extract_usage(system_result)
            merge_usage(usage_totals, usage)

            check_result = check_deterministic(case.expected_output, actual_output)
            if check_result is None:
                check_result = await check_pass_fail(
                    case.input,
                    case.expected_output,
                    actual_output,
                )

            hallucination = await check_hallucination(
                case.input,
                actual_output,
                tool_results=tool_results,
                case_tags=case.tags,
                deterministic_result=check_result,
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

            pass_values.append(1.0 if status == "pass" else 0.0)
            results.append(
                CaseResult(
                    case_name=case.name,
                    status=status,
                    score=float(check_result["score"]),
                    error=error,
                    actual_output=actual_output,
                    latency_ms=latency_ms,
                    usage=usage,
                )
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            latency_total += latency_ms
            failed += 1
            for tag in case.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            pass_values.append(0.0)
            results.append(
                CaseResult(
                    case_name=case.name,
                    status="error",
                    score=0.0,
                    error=str(exc),
                    actual_output="",
                    latency_ms=latency_ms,
                    usage=None,
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
        metadata={"usage_totals": usage_totals},
        pass_rate_ci_95=bootstrap_ci(pass_values),
    )


async def seed_cases(
    db,
    prompt_text: str,
    *,
    train_cases: list[BenchmarkCase],
    eval_cases: list[BenchmarkCase],
) -> None:
    db.add(
        PromptVersion(
            version=1,
            content=prompt_text,
            is_active=True,
            change_reason="Benchmark seed prompt",
        )
    )
    for case in train_cases + eval_cases:
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


async def load_cases(db, split: str) -> list[EvalCase]:
    cases = (await db.execute(select(EvalCase).order_by(EvalCase.name.asc()))).scalars().all()
    return [case for case in cases if isinstance(case.tags, list) and split in case.tags]


async def run_direct_llm_benchmark(
    *,
    eval_cases_subset: list[BenchmarkCase],
    system_prompt: str,
) -> SystemSummary:
    model = build_chat_model(purpose="agent", streaming=False)

    async def runner(case: BenchmarkCase) -> dict[str, Any]:
        response = await model.ainvoke(langchain_messages(case, system_prompt=system_prompt))
        content = (
            response.content if isinstance(response.content, str) else str(response.content)
        )
        return {"content": content, "tool_results": None, "usage": extract_usage(response)}

    summary = await evaluate_cases(eval_cases_subset, runner)
    summary.system = "direct_llm"
    summary.metadata = {**summary.metadata, "prompt": "DIRECT_LLM_PROMPT", "adapted": False}
    return summary


async def run_tool_agent_benchmark(
    *,
    system_name: str,
    prompt_text: str,
    eval_cases_subset: list[BenchmarkCase],
) -> SystemSummary:
    async def runner(case: BenchmarkCase) -> dict[str, Any]:
        return await run_agent(messages=case_messages(case), system_prompt=prompt_text)

    summary = await evaluate_cases(eval_cases_subset, runner)
    summary.system = system_name
    summary.metadata = {**summary.metadata, "adapted": False}
    return summary


async def _invoke_tool(name: str, args: dict[str, Any]) -> str:
    tool = TOOL_BY_NAME[name]
    result = await tool.ainvoke(args)
    return result if isinstance(result, str) else str(result)


async def run_sdk_tool_baseline(
    *,
    prompt_text: str,
    eval_cases_subset: list[BenchmarkCase],
    max_steps: int = 4,
) -> SystemSummary:
    model = build_chat_model(purpose="agent", streaming=False).bind_tools(TOOLS)

    async def runner(case: BenchmarkCase) -> dict[str, Any]:
        conversation = langchain_messages(case, system_prompt=prompt_text)
        tool_results: list[dict[str, str]] = []
        usage_totals: dict[str, float] = {}
        final_content = ""

        for _ in range(max_steps):
            response = await model.ainvoke(conversation)
            usage = extract_usage(response)
            merge_usage(usage_totals, usage)
            content = (
                response.content if isinstance(response.content, str) else str(response.content)
            )
            conversation.append(response)
            final_content = content

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                break

            for tool_call in tool_calls:
                tool_name = str(tool_call.get("name", ""))
                args = tool_call.get("args", {})
                tool_output = await _invoke_tool(tool_name, args)
                tool_results.append({"name": tool_name, "output": tool_output})
                conversation.append(ToolMessage(content=tool_output, tool_call_id=tool_call["id"]))

        return {
            "content": final_content,
            "tool_results": tool_results or None,
            "usage": usage_totals or None,
        }

    summary = await evaluate_cases(eval_cases_subset, runner)
    summary.system = "sdk_tool_agent"
    summary.metadata = {
        **summary.metadata,
        "adapted": False,
        "implementation": "provider_sdk_manual_tool_loop",
    }
    return summary


def cycle_snapshot(
    *,
    cycle: int,
    prompt_version: int,
    accepted: bool,
    adapt_run_before: float,
    adapt_run_after: float,
    eval_summary: SystemSummary,
    initial_eval_rate: float,
    previous_eval_rate: float,
) -> dict[str, Any]:
    eval_rate = eval_summary.pass_rate
    protected_pass_rate = eval_summary.tag_pass_rates.get("protected", 1.0)
    hallucination_rate = (
        eval_summary.hallucination_failures / len(eval_summary.results)
        if eval_summary.results
        else 0.0
    )
    return {
        "cycle": cycle,
        "prompt_version": prompt_version,
        "accepted": accepted,
        "train_pass_rate_before": adapt_run_before,
        "train_pass_rate_after": adapt_run_after,
        "gain": {
            "train_pass_rate_delta": adapt_run_after - adapt_run_before,
            "eval_pass_rate_delta_from_start": eval_rate - initial_eval_rate,
        },
        "stability": {
            "eval_pass_rate_delta_from_previous": eval_rate - previous_eval_rate,
            "stable": eval_rate >= previous_eval_rate,
        },
        "alignment": {
            "hallucination_failures": eval_summary.hallucination_failures,
            "hallucination_rate": hallucination_rate,
            "protected_pass_rate": protected_pass_rate,
        },
        "eval": {
            "pass_rate": eval_summary.pass_rate,
            "pass_rate_ci_95": list(eval_summary.pass_rate_ci_95),
            "avg_latency_ms": eval_summary.avg_latency_ms,
            "hallucination_failures": eval_summary.hallucination_failures,
            "tag_pass_rates": eval_summary.tag_pass_rates,
            "usage_totals": eval_summary.metadata.get("usage_totals", {}),
        },
    }


async def run_adaptive_agent_benchmark(
    *,
    weak_prompt: str,
    adaptation_cycles: int,
    consistency_repeats: int,
    eval_cases_subset: list[BenchmarkCase],
    train_cases_subset: list[BenchmarkCase],
) -> tuple[SystemSummary, dict[str, Any]]:
    with TemporaryDirectory(prefix="adaptive-agent-compare-") as tmpdir:
        db_path = Path(tmpdir) / "compare.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        trajectory_run: dict[str, Any] = {"initial": {}, "cycles": []}

        async with session_factory() as db:
            await seed_cases(
                db,
                weak_prompt,
                train_cases=train_cases_subset,
                eval_cases=eval_cases_subset,
            )
            train_db_cases = await load_cases(db, "train")

            prompt = (
                await db.execute(select(PromptVersion).where(PromptVersion.is_active.is_(True)))
            ).scalar_one()

            async def runner_for_prompt(prompt_text: str):
                async def runner(case: BenchmarkCase) -> dict[str, Any]:
                    return await run_agent(messages=case_messages(case), system_prompt=prompt_text)

                return runner

            initial_eval = await evaluate_cases(
                eval_cases_subset,
                await runner_for_prompt(prompt.content),
            )
            trajectory_run["initial"] = {
                "prompt_version": prompt.version,
                "eval": {
                    "pass_rate": initial_eval.pass_rate,
                    "pass_rate_ci_95": list(initial_eval.pass_rate_ci_95),
                    "avg_latency_ms": initial_eval.avg_latency_ms,
                    "hallucination_failures": initial_eval.hallucination_failures,
                    "tag_pass_rates": initial_eval.tag_pass_rates,
                    "usage_totals": initial_eval.metadata.get("usage_totals", {}),
                },
            }

            previous_eval_rate = initial_eval.pass_rate
            active_prompt = prompt
            final_eval = initial_eval
            last_adapt_run: Any = None

            for cycle in range(1, adaptation_cycles + 1):
                adapt_run = await create_adaptation_run(db)
                adapt_run = await run_adaptation_loop(
                    db,
                    adapt_run.id,
                    case_ids=[case.id for case in train_db_cases],
                    consistency_repeats=consistency_repeats,
                )
                last_adapt_run = adapt_run
                active_prompt = (
                    await db.execute(select(PromptVersion).where(PromptVersion.is_active.is_(True)))
                ).scalar_one()
                final_eval = await evaluate_cases(
                    eval_cases_subset,
                    await runner_for_prompt(active_prompt.content),
                )
                trajectory_run["cycles"].append(
                    cycle_snapshot(
                        cycle=cycle,
                        prompt_version=active_prompt.version,
                        accepted=bool(adapt_run.accepted),
                        adapt_run_before=float(adapt_run.before_pass_rate or 0.0),
                        adapt_run_after=float(adapt_run.after_pass_rate or 0.0),
                        eval_summary=final_eval,
                        initial_eval_rate=initial_eval.pass_rate,
                        previous_eval_rate=previous_eval_rate,
                    )
                )
                previous_eval_rate = final_eval.pass_rate

            summary = final_eval
            summary.system = "adaptive_agent"
            summary.metadata = {
                **summary.metadata,
                "adapted": True,
                "accepted": bool(last_adapt_run.accepted) if last_adapt_run is not None else False,
                "before_pass_rate": (
                    float(last_adapt_run.before_pass_rate or 0.0) if last_adapt_run else 0.0
                ),
                "after_pass_rate": (
                    float(last_adapt_run.after_pass_rate or 0.0) if last_adapt_run else 0.0
                ),
                "prompt_version": active_prompt.version,
                "adaptation_cycles": adaptation_cycles,
                "train_case_count": len(train_cases_subset),
                "eval_case_count": len(eval_cases_subset),
            }

        await engine.dispose()

    return summary, trajectory_run
