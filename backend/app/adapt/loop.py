"""Self-improving loop orchestrator.

Implements the Karpathy autoresearch pattern:
1. Run eval suite with current prompt
2. Analyze failures
3. Generate improved prompt
4. Run eval suite with new prompt
5. Accept if improvement, reject otherwise
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapt.prompt_updater import create_prompt_version, generate_improved_prompt
from app.eval.runner import run_eval_suite
from app.models import AdaptationRun, PromptVersion


async def run_adaptation_loop(db: AsyncSession, adaptation_run_id: str) -> AdaptationRun:
    """Execute the full self-improving loop."""

    # Load the adaptation run
    result = await db.execute(
        select(AdaptationRun).where(AdaptationRun.id == adaptation_run_id)
    )
    adapt_run = result.scalar_one_or_none()
    if not adapt_run:
        raise ValueError(f"Adaptation run {adaptation_run_id} not found")

    try:
        # Step 1: Get current active prompt
        prompt_result = await db.execute(
            select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
        )
        current_prompt = prompt_result.scalar_one_or_none()
        if not current_prompt:
            raise ValueError("No active prompt version found")

        # Step 2: Run eval suite with current prompt
        before_eval = await run_eval_suite(db)
        before_pass_rate = before_eval.pass_rate or 0.0

        adapt_run.before_pass_rate = before_pass_rate
        adapt_run.before_version_id = current_prompt.id
        await db.commit()

        # Step 3: Analyze failures and generate improved prompt
        improved_content = await generate_improved_prompt(
            db, current_prompt.content, before_eval.id
        )

        # If prompt didn't change, mark as completed with no improvement
        if improved_content.strip() == current_prompt.content.strip():
            adapt_run.status = "completed"
            adapt_run.completed_at = datetime.now(timezone.utc)
            adapt_run.after_pass_rate = before_pass_rate
            adapt_run.accepted = False
            await db.commit()
            await db.refresh(adapt_run)
            return adapt_run

        # Step 4: Create new prompt version (don't activate yet)
        new_prompt = await create_prompt_version(
            db,
            content=improved_content,
            parent_id=current_prompt.id,
            change_reason=(
                f"Auto-improvement from adaptation run. "
                f"Before pass rate: {before_pass_rate:.0%}"
            ),
            activate=False,
        )

        # Step 5: Temporarily activate new prompt and run eval
        current_prompt.is_active = False
        new_prompt.is_active = True
        await db.commit()

        after_eval = await run_eval_suite(db)
        after_pass_rate = after_eval.pass_rate or 0.0

        # Step 6: Accept or reject
        improved = after_pass_rate > before_pass_rate

        if improved:
            # Accept: keep new prompt active
            adapt_run.accepted = True
            adapt_run.after_version_id = new_prompt.id
        else:
            # Reject: revert to old prompt
            new_prompt.is_active = False
            current_prompt.is_active = True
            adapt_run.accepted = False
            adapt_run.after_version_id = new_prompt.id

        adapt_run.status = "completed"
        adapt_run.completed_at = datetime.now(timezone.utc)
        adapt_run.after_pass_rate = after_pass_rate

        await db.commit()
        await db.refresh(adapt_run)
        return adapt_run

    except Exception:
        adapt_run.status = "failed"
        adapt_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def create_adaptation_run(db: AsyncSession) -> AdaptationRun:
    """Create a new adaptation run record."""
    # Get current active prompt
    prompt_result = await db.execute(
        select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
    )
    current_prompt = prompt_result.scalar_one_or_none()

    adapt_run = AdaptationRun(
        status="running",
        before_version_id=current_prompt.id if current_prompt else "",
        before_pass_rate=0.0,
    )
    db.add(adapt_run)
    await db.commit()
    await db.refresh(adapt_run)
    return adapt_run
