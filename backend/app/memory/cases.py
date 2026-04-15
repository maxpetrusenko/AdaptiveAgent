"""Failure to eval case conversion."""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import EvalCase


async def failure_to_eval_case(
    db: AsyncSession,
    failure: dict,
) -> EvalCase:
    """Convert a failure into a new eval test case using LLM."""
    model = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=settings.anthropic_api_key,
        max_tokens=500,
    )

    prompt = (
        "Given this agent failure, generate a clear test case.\n\n"
        f"Failure:\n"
        f"- Input: {failure['input']}\n"
        f"- Expected: {failure['expected']}\n"
        f"- Actual: {failure['actual']}\n"
        f"- Error: {failure.get('error', 'N/A')}\n\n"
        "Generate a test case in this exact JSON format:\n"
        '{"name": "descriptive name", "input": "the test input", '
        '"expected_output": "what correct output looks like", "tags": ["tag1", "tag2"]}'
    )

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)

        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            case = EvalCase(
                name=data.get("name", "Generated case"),
                input=data.get("input", failure["input"]),
                expected_output=data.get("expected_output", failure["expected"]),
                tags=data.get("tags", ["generated"]),
                source="generated",
            )
            db.add(case)
            await db.commit()
            await db.refresh(case)
            return case
    except Exception:
        pass

    # Fallback: create directly from failure
    case = EvalCase(
        name=f"Regression: {failure.get('case_name', 'unknown')}",
        input=failure["input"],
        expected_output=failure["expected"],
        tags=["generated", "regression"],
        source="generated",
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case
