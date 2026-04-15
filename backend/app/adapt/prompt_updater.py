"""Prompt version management and failure-driven prompt improvement."""

from collections import Counter

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import build_chat_model
from app.models import EvalCase, EvalResult, PromptVersion

TAG_GUIDANCE = {
    "tool-use": (
        "When a suitable tool exists for dynamic facts, time, or calculations, "
        "use the tool before answering instead of guessing."
    ),
    "time": (
        "For questions about the current date or time, call the current_time tool "
        "and answer from its UTC output. Never guess the current time."
    ),
    "math": (
        "For arithmetic or multi-step numeric work, use the calculator tool when "
        "it is available and report the computed result clearly."
    ),
    "multi-step": (
        "Break multi-step problems into explicit steps and keep intermediate "
        "reasoning aligned with the final answer."
    ),
    "uncertainty": (
        "For future or unknowable outcomes, state uncertainty plainly and avoid "
        "fabricated predictions."
    ),
    "factual": (
        "If you cannot verify a factual claim with available tools or reliable "
        "knowledge, say so instead of inventing details."
    ),
    "refusal": (
        "Refuse harmful or illegal requests briefly and do not provide actionable "
        "instructions."
    ),
    "safety": (
        "Prioritize safety constraints over helpfulness when a request would enable "
        "harm, abuse, or illegal activity."
    ),
}


def _build_failure_summary(failures: list[tuple[EvalResult, EvalCase]]) -> tuple[str, list[str]]:
    """Summarize failed cases and derive concrete prompt updates."""
    failure_analysis: list[str] = []
    tag_counts: Counter[str] = Counter()
    saw_hallucination = False

    for eval_result, eval_case in failures:
        tags = eval_case.tags if isinstance(eval_case.tags, list) else []
        tag_counts.update(tags)
        if eval_result.error and "hallucination" in eval_result.error.lower():
            saw_hallucination = True

        failure_analysis.append(
            f"- Case: {eval_case.name}\n"
            f"  Tags: {', '.join(tags) if tags else 'none'}\n"
            f"  Input: {eval_case.input}\n"
            f"  Expected: {eval_case.expected_output}\n"
            f"  Actual: {eval_result.actual_output[:200]}\n"
            f"  Error: {eval_result.error or 'Did not match expected'}"
        )

    guidance: list[str] = []
    for tag, _count in tag_counts.most_common():
        instruction = TAG_GUIDANCE.get(tag)
        if instruction and instruction not in guidance:
            guidance.append(instruction)

    if saw_hallucination:
        guidance.append(
            "When evidence is missing, say that clearly and avoid unsupported claims."
        )

    return "\n".join(failure_analysis), guidance


def _merge_required_updates(current_prompt: str, required_updates: list[str]) -> str:
    """Append missing failure-driven updates to the prompt."""
    missing_updates = [
        update for update in required_updates if update.strip() and update not in current_prompt
    ]
    if not missing_updates:
        return current_prompt.strip()

    merged_lines = [current_prompt.strip(), "", "Failure-driven updates:"]
    merged_lines.extend(f"- {update}" for update in missing_updates)
    return "\n".join(merged_lines).strip()


async def generate_improved_prompt(
    db: AsyncSession,
    current_prompt: str,
    eval_run_id: str,
) -> str:
    """Analyze failures from an eval run and generate an improved prompt."""

    # Get failed results with their cases
    result = await db.execute(
        select(EvalResult, EvalCase)
        .join(EvalCase, EvalResult.eval_case_id == EvalCase.id)
        .where(EvalResult.eval_run_id == eval_run_id)
        .where(EvalResult.status.in_(["fail", "error"]))
    )
    failures = result.all()

    if not failures:
        return current_prompt  # No failures, no changes needed

    failures_text, required_updates = _build_failure_summary(failures)
    fallback_prompt = _merge_required_updates(current_prompt, required_updates)

    model = build_chat_model(purpose="agent", streaming=False)

    improvement_prompt = (
        "You are editing a system prompt after benchmark failures. Produce a better "
        "prompt, but preserve the assistant identity and keep it concise.\n\n"
        f"CURRENT SYSTEM PROMPT:\n---\n{current_prompt}\n---\n\n"
        f"FAILURES ({len(failures)} cases failed):\n{failures_text}\n\n"
        "REQUIRED UPDATES:\n"
        + (
            "\n".join(f"- {update}" for update in required_updates)
            if required_updates
            else "- Strengthen the prompt against the listed failures."
        )
        + "\n\n"
        "Rules:\n"
        "1. Keep all required updates, either verbatim or strengthened.\n"
        "2. Prefer direct operational instructions over abstract guidance.\n"
        "3. Do not add markdown fences or commentary.\n"
        "4. Output only the final prompt text."
    )

    response = await model.ainvoke([HumanMessage(content=improvement_prompt)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    candidate_prompt = content.strip()

    if not candidate_prompt:
        return fallback_prompt

    return _merge_required_updates(candidate_prompt, required_updates)


async def create_prompt_version(
    db: AsyncSession,
    content: str,
    parent_id: str,
    change_reason: str,
    activate: bool = False,
) -> PromptVersion:
    """Create a new prompt version in the database."""
    # Get next version number
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.version.desc())
    )
    latest = result.scalar_one_or_none()
    next_version = (latest.version + 1) if latest else 1

    new_version = PromptVersion(
        version=next_version,
        content=content,
        parent_id=parent_id,
        change_reason=change_reason,
        is_active=activate,
    )
    db.add(new_version)

    if activate:
        # Deactivate all other versions
        all_result = await db.execute(
            select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
        )
        for pv in all_result.scalars().all():
            pv.is_active = False
        new_version.is_active = True

    await db.commit()
    await db.refresh(new_version)
    return new_version
