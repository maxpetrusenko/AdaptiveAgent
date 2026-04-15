"""Evaluation checks: pass/fail, hallucination, consistency."""

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from app.config import settings


def _parse_json(content: str) -> dict | None:
    """Extract and parse JSON from LLM response text."""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            return None
    return None


def _get_judge_model() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=settings.anthropic_api_key,
        max_tokens=200,
    )


async def check_pass_fail(
    input_text: str,
    expected_output: str,
    actual_output: str,
) -> dict:
    """Use LLM-as-judge to check if actual output matches expected semantically."""
    model = _get_judge_model()

    judge_prompt = (
        "You are an evaluation judge. Compare the actual output to the expected output "
        "for the given input.\n\n"
        f"Input: {input_text}\n"
        f"Expected Output: {expected_output}\n"
        f"Actual Output: {actual_output}\n\n"
        "Does the actual output satisfy the expected output? "
        "Consider semantic meaning, not exact wording.\n"
        'Respond with ONLY a JSON object: '
        '{"pass": true/false, "score": 0.0-1.0, "reason": "brief explanation"}'
    )

    try:
        response = await model.ainvoke([HumanMessage(content=judge_prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        result = _parse_json(content)
        if result:
            return {
                "pass": bool(result.get("pass", False)),
                "score": float(result.get("score", 0.0)),
                "reason": str(result.get("reason", "")),
            }
    except Exception as e:
        return {"pass": False, "score": 0.0, "reason": f"Judge error: {e}"}

    return {"pass": False, "score": 0.0, "reason": "Could not parse judge response"}


async def check_hallucination(
    input_text: str,
    actual_output: str,
) -> dict:
    """Check if the output contains hallucinated/unsupported claims."""
    model = _get_judge_model()

    judge_prompt = (
        "Analyze the following AI response for hallucinations "
        "(fabricated facts, unsupported claims, false information).\n\n"
        f"Input question: {input_text}\n"
        f"AI Response: {actual_output}\n\n"
        "Respond with ONLY a JSON object: "
        '{"has_hallucination": true/false, "confidence": 0.0-1.0, "details": "explanation"}'
    )

    try:
        response = await model.ainvoke([HumanMessage(content=judge_prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        result = _parse_json(content)
        if result:
            return {
                "has_hallucination": bool(result.get("has_hallucination", False)),
                "confidence": float(result.get("confidence", 0.0)),
                "details": str(result.get("details", "")),
            }
    except Exception as e:
        return {"has_hallucination": False, "confidence": 0.0, "details": f"Check error: {e}"}

    return {"has_hallucination": False, "confidence": 0.0, "details": "Could not parse response"}


async def check_consistency(
    input_text: str,
    outputs: list[str],
) -> dict:
    """Check consistency across multiple runs of the same input."""
    if len(outputs) < 2:
        return {"consistent": True, "variance": 0.0, "details": "Need multiple outputs to check"}

    model = _get_judge_model()

    outputs_text = "\n---\n".join([f"Response {i + 1}: {o}" for i, o in enumerate(outputs)])

    judge_prompt = (
        "Compare these multiple responses to the same input for consistency.\n\n"
        f"Input: {input_text}\n\n"
        f"{outputs_text}\n\n"
        "Are the responses consistent in their core meaning/facts?\n"
        "Respond with ONLY a JSON object: "
        '{"consistent": true/false, "variance": 0.0-1.0, "details": "explanation"}'
    )

    try:
        response = await model.ainvoke([HumanMessage(content=judge_prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        result = _parse_json(content)
        if result:
            return {
                "consistent": bool(result.get("consistent", True)),
                "variance": float(result.get("variance", 0.0)),
                "details": str(result.get("details", "")),
            }
    except Exception as e:
        return {"consistent": True, "variance": 0.0, "details": f"Check error: {e}"}

    return {"consistent": True, "variance": 0.0, "details": "Could not parse response"}
