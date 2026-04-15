"""Prompt version management and LLM-based prompt improvement."""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import EvalCase, EvalResult, PromptVersion


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

    # Build failure analysis
    failure_analysis = []
    for eval_result, eval_case in failures:
        failure_analysis.append(
            f"- Input: {eval_case.input}\n"
            f"  Expected: {eval_case.expected_output}\n"
            f"  Actual: {eval_result.actual_output[:200]}\n"
            f"  Error: {eval_result.error or 'Did not match expected'}"
        )

    failures_text = "\n".join(failure_analysis)

    model = ChatAnthropic(
        model=settings.default_model,
        api_key=settings.anthropic_api_key,
        max_tokens=2000,
    )

    improvement_prompt = (
        "You are a prompt engineering expert. Analyze the following system prompt "
        "and its failures, then output an improved version.\n\n"
        f"CURRENT SYSTEM PROMPT:\n---\n{current_prompt}\n---\n\n"
        f"FAILURES ({len(failures)} cases failed):\n{failures_text}\n\n"
        "INSTRUCTIONS:\n"
        "1. Analyze why the current prompt led to these failures\n"
        "2. Generate an improved system prompt that addresses the failures\n"
        "3. Keep the core identity and capabilities intact\n"
        "4. Add specific instructions to handle the failure cases better\n"
        "5. Be concise - don't add unnecessary verbosity\n\n"
        "Output ONLY the improved system prompt, nothing else. "
        "No explanations, no markdown formatting, just the raw prompt text."
    )

    response = await model.ainvoke([HumanMessage(content=improvement_prompt)])
    content = response.content if isinstance(response.content, str) else str(response.content)

    return content.strip()


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
