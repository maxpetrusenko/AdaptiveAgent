"""Evaluation runner: executes test cases against the current agent."""

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import run_agent
from app.eval.checks import check_hallucination, check_pass_fail
from app.models import EvalCase, EvalResult, EvalRun, PromptVersion


async def run_eval_suite(db: AsyncSession, eval_run_id: str | None = None) -> EvalRun:
    """Run all eval cases against the current agent and store results.

    If eval_run_id is provided, uses that existing run. Otherwise creates a new one.
    """
    # Get active prompt version
    result = await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
    active_prompt = result.scalar_one_or_none()
    if not active_prompt:
        raise ValueError("No active prompt version found")

    # Get all eval cases
    cases_result = await db.execute(select(EvalCase))
    cases = cases_result.scalars().all()

    if not cases:
        raise ValueError("No eval cases found")

    # Get or create eval run
    if eval_run_id:
        run_result = await db.execute(select(EvalRun).where(EvalRun.id == eval_run_id))
        eval_run = run_result.scalar_one_or_none()
        if not eval_run:
            raise ValueError(f"Eval run {eval_run_id} not found")
    else:
        eval_run = EvalRun(
            prompt_version_id=active_prompt.id,
            status="running",
            total=len(cases),
        )
        db.add(eval_run)
        await db.commit()
        await db.refresh(eval_run)

    passed = 0
    failed = 0

    for case in cases:
        start_time = time.time()

        try:
            # Run agent with the case input
            agent_result = await run_agent(
                messages=[{"role": "user", "content": case.input}],
                system_prompt=active_prompt.content,
            )

            actual_output = agent_result["content"]
            latency_ms = int((time.time() - start_time) * 1000)

            # Run pass/fail check
            check_result = await check_pass_fail(case.input, case.expected_output, actual_output)

            # Run hallucination check
            halluc_result = await check_hallucination(case.input, actual_output)

            status = "pass" if check_result["pass"] else "fail"
            error_msg = None

            if not check_result["pass"]:
                error_msg = check_result["reason"]
            if halluc_result["has_hallucination"]:
                halluc_detail = f"Hallucination: {halluc_result['details']}"
                error_msg = f"{error_msg} | {halluc_detail}" if error_msg else halluc_detail
                status = "fail"

            if status == "pass":
                passed += 1
            else:
                failed += 1

            eval_result = EvalResult(
                eval_run_id=eval_run.id,
                eval_case_id=case.id,
                status=status,
                actual_output=actual_output,
                score=check_result["score"],
                error=error_msg,
                latency_ms=latency_ms,
            )
            db.add(eval_result)

        except Exception as e:
            failed += 1
            latency_ms = int((time.time() - start_time) * 1000)
            eval_result = EvalResult(
                eval_run_id=eval_run.id,
                eval_case_id=case.id,
                status="error",
                actual_output="",
                score=0.0,
                error=str(e),
                latency_ms=latency_ms,
            )
            db.add(eval_result)

    # Update eval run
    eval_run.status = "completed"
    eval_run.completed_at = datetime.now(timezone.utc)
    eval_run.passed = passed
    eval_run.failed = failed
    eval_run.pass_rate = passed / len(cases) if cases else 0.0

    await db.commit()
    await db.refresh(eval_run)

    return eval_run
