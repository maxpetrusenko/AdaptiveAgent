"""Immutable state and artifacts for four-step research execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StepName = Literal["plan", "retrieve", "synthesize", "verify"]
StepStatus = Literal["pending", "active", "completed"]
RunStatus = Literal["active", "completed", "replan_required", "escalated"]
ExecutionMode = Literal["deterministic", "live"]

DEFAULT_ADAPTER_FINGERPRINTS: dict[ExecutionMode, str] = {
    "deterministic": "deterministic-research-v1",
    "live": "live-rag-v1",
}

STANDARD_STEPS: tuple[StepName, ...] = (
    "plan",
    "retrieve",
    "synthesize",
    "verify",
)


@dataclass(frozen=True, slots=True)
class PlanArtifact:
    queries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    citation_id: str | None
    text: str
    source_id: str | None = None
    content_hash: str | None = None
    fusion_score: float | None = None
    dense_score: float | None = None
    lexical_score: float | None = None
    dense_rank: int | None = None
    lexical_rank: int | None = None
    index_version: str | None = None
    embedding_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class SynthesisArtifact:
    answer: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    evidence_citation_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ResearchArtifacts:
    plan: PlanArtifact | None = None
    retrieval: tuple[RetrievedChunk, ...] = ()
    synthesis: SynthesisArtifact | None = None
    verification: VerificationResult | None = None


@dataclass(frozen=True, slots=True)
class ResearchStep:
    name: StepName
    status: StepStatus
    attempt: int = 1


@dataclass(frozen=True, slots=True)
class ResearchRun:
    id: str
    goal: str
    execution_mode: ExecutionMode
    adapter_fingerprint: str
    steps: tuple[ResearchStep, ...]
    status: RunStatus
    cursor: int
    version: int
    plan_version: int
    action_budget: int
    actions_used: int
    artifacts: ResearchArtifacts
    terminal_reason: str | None = None


def create_research_run(
    *,
    run_id: str,
    goal: str,
    action_budget: int = 8,
    execution_mode: ExecutionMode = "deterministic",
    adapter_fingerprint: str | None = None,
) -> ResearchRun:
    if not run_id.strip():
        raise ValueError("run_id is required")
    if not goal.strip():
        raise ValueError("goal is required")
    if action_budget < 1:
        raise ValueError("action_budget must be positive")
    if execution_mode not in DEFAULT_ADAPTER_FINGERPRINTS:
        raise ValueError("execution_mode is invalid")
    resolved_fingerprint = (
        DEFAULT_ADAPTER_FINGERPRINTS[execution_mode]
        if adapter_fingerprint is None
        else adapter_fingerprint.strip()
    )
    if not resolved_fingerprint:
        raise ValueError("adapter_fingerprint is required")
    steps = tuple(
        ResearchStep(name=name, status="active" if index == 0 else "pending")
        for index, name in enumerate(STANDARD_STEPS)
    )
    return ResearchRun(
        id=run_id,
        goal=goal,
        execution_mode=execution_mode,
        adapter_fingerprint=resolved_fingerprint,
        steps=steps,
        status="active",
        cursor=0,
        version=0,
        plan_version=1,
        action_budget=action_budget,
        actions_used=0,
        artifacts=ResearchArtifacts(),
    )
