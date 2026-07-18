from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


class AcceptanceCriterionCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)

    _normalize_id = field_validator("id")(_required_text)
    _normalize_description = field_validator("description")(_required_text)


class StepCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)

    _normalize_title = field_validator("title")(_required_text)


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    artifact_ref: str | None = Field(default=None, max_length=1000)
    digest: str | None = Field(default=None, max_length=1000)

    _normalize_required = field_validator(
        "criterion_id",
        "summary",
    )(_required_text)

    @field_validator("artifact_ref", "digest")
    @classmethod
    def normalize_optional_proof(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


TrustedSource = Literal["ci", "review", "runtime"]
TrustedVerifier = Literal["pytest", "maintainer", "system"]


@dataclass(frozen=True)
class TrustedVerificationResult:
    """Internal verifier output; never used as a FastAPI request model."""

    criterion_id: str
    summary: str
    artifact_ref: str
    source: TrustedSource
    verifier: TrustedVerifier


class TaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterionCreate] = Field(min_length=1)
    steps: list[StepCreate] = Field(min_length=1)
    stall_threshold: int = Field(default=3, ge=1, le=100)
    action_budget: int = Field(default=25, ge=1, le=10_000)

    _normalize_goal = field_validator("goal")(_required_text)

    @field_validator("constraints")
    @classmethod
    def normalize_constraints(cls, values: list[str]) -> list[str]:
        return [_required_text(value) for value in values]

    @model_validator(mode="after")
    def criterion_ids_are_unique(self):
        ids = [criterion.id for criterion in self.acceptance_criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("acceptance criterion ids must be unique")
        return self

class AdvanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=200)
    progress: bool
    evidence: list[EvidenceCreate] = Field(default_factory=list)


class ReplanCommand(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)
    steps: list[StepCreate] = Field(min_length=1)


class EvidenceResponse(BaseModel):
    summary: str
    artifact_ref: str | None = None
    digest: str | None = None
    source: str
    verifier: str
    status: Literal["unverified", "verified"]
    recorded_at: datetime


class AcceptanceCriterionResponse(BaseModel):
    id: str
    description: str
    evidence: list[EvidenceResponse]


class StepResponse(BaseModel):
    id: str
    title: str
    status: str


class CheckpointResponse(BaseModel):
    sequence: int
    operation: str
    idempotency_key: str | None
    updated_at: datetime


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    goal: str
    constraints: list[str]
    acceptance_criteria: list[AcceptanceCriterionResponse]
    steps: list[StepResponse]
    status: str
    plan_version: int
    current_step_index: int
    stall_count: int
    stall_threshold: int
    action_budget: int
    actions_used: int
    replan_reason: str | None
    escalation_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    checkpoint: CheckpointResponse


class EffectResponse(BaseModel):
    idempotency_key: str
    operation: str
    created_at: datetime
