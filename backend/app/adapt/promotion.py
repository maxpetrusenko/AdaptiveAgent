"""Deterministic promotion authority for bounded agent adaptations."""

import json
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite, sqrt
from statistics import fmean, stdev
from threading import Lock
from types import MappingProxyType
from typing import Literal, Mapping


@dataclass(frozen=True)
class DatasetCase:
    case_id: str
    content: str


@dataclass(frozen=True)
class DatasetBundle:
    training: tuple[DatasetCase, ...]
    validation: tuple[DatasetCase, ...]
    protected: tuple[DatasetCase, ...]

    def __post_init__(self) -> None:
        splits = {
            "training": self.training,
            "validation": self.validation,
            "protected": self.protected,
        }
        for (left_name, left), (right_name, right) in combinations(splits.items(), 2):
            left_ids = {case.case_id for case in left}
            right_ids = {case.case_id for case in right}
            if left_ids & right_ids:
                raise ValueError(
                    f"dataset case IDs overlap between {left_name} and {right_name}"
                )

            left_content = {_normalized_content(case.content) for case in left}
            right_content = {_normalized_content(case.content) for case in right}
            if left_content & right_content:
                raise ValueError(
                    f"dataset case content overlaps between {left_name} and {right_name}"
                )

    def proposal_context(self) -> tuple[DatasetCase, ...]:
        return self.training

    def dataset_hashes(self) -> dict[str, str]:
        return {
            "training": _hash_cases(self.training),
            "validation": _hash_cases(self.validation),
            "protected": _hash_cases(self.protected),
        }


def _normalized_content(content: str) -> str:
    return " ".join(content.split()).casefold()


def _hash_cases(cases: tuple[DatasetCase, ...]) -> str:
    payload = [
        {"case_id": case.case_id, "content": case.content}
        for case in sorted(cases, key=lambda item: item.case_id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Mutation:
    kind: str
    target: str
    before: str
    after: str


@dataclass(frozen=True)
class PromotionEvidence:
    training_baseline: tuple[float, ...]
    training_candidate: tuple[float, ...]
    validation_baseline: tuple[float, ...]
    validation_candidate: tuple[float, ...]
    protected_baseline: tuple[float, ...]
    protected_candidate: tuple[float, ...]
    baseline_latency_ms: float
    candidate_latency_ms: float
    baseline_cost: float
    candidate_cost: float
    training_baseline_statuses: tuple[str, ...]
    training_candidate_statuses: tuple[str, ...]
    validation_baseline_statuses: tuple[str, ...]
    validation_candidate_statuses: tuple[str, ...]
    protected_baseline_statuses: tuple[str, ...]
    protected_candidate_statuses: tuple[str, ...]


@dataclass(frozen=True)
class PromotionPolicy:
    min_validation_delta: float = 0.05
    confidence_z: float = 1.96
    max_latency_ratio: float = 1.25
    max_cost_ratio: float = 1.25


@dataclass(frozen=True)
class PromotionDecision:
    action: Literal["promote", "reject", "rollback"]
    rationale: str
    quality_delta: float
    lower_confidence_bound: float


@dataclass(frozen=True)
class CandidateManifest:
    parent_hash: str
    candidate_hash: str
    dataset_hashes: Mapping[str, str]
    metrics: Mapping[str, float]
    rationale: str
    mutations: tuple[Mutation, ...]


class PromotionRegistry:
    def __init__(self, current_hash: str):
        self._current_hash = current_hash
        self._previous_hash: str | None = None
        self._lock = Lock()

    @property
    def current_hash(self) -> str:
        return self._current_hash

    def compare_and_swap(self, expected_parent_hash: str, candidate_hash: str) -> bool:
        with self._lock:
            if self._current_hash != expected_parent_hash:
                return False
            self._previous_hash = self._current_hash
            self._current_hash = candidate_hash
            return True

    def rollback(self, expected_candidate_hash: str) -> bool:
        with self._lock:
            if (
                self._current_hash != expected_candidate_hash
                or self._previous_hash is None
            ):
                return False
            self._current_hash = self._previous_hash
            self._previous_hash = None
            return True


def evaluate_promotion(
    evidence: PromotionEvidence,
    mutations: tuple[Mutation, ...],
    policy: PromotionPolicy | None = None,
) -> PromotionDecision:
    policy = policy or PromotionPolicy()
    invalid_kinds = sorted(
        {mutation.kind for mutation in mutations}
        - {"prompt", "tool_description"}
    )
    if invalid_kinds:
        return _decision(
            "reject",
            f"Mutation scope is not allowed: {', '.join(invalid_kinds)}",
        )

    invalid_evidence = _invalid_evidence_reason(evidence)
    if invalid_evidence:
        return _decision("reject", invalid_evidence)

    if len(evidence.validation_baseline) < 2:
        return _decision(
            "reject",
            "At least two paired validation observations are required",
        )

    if not evidence.protected_baseline:
        return _decision(
            "reject",
            "Protected evaluation suite must not be empty",
        )

    protected_status_regression = _first_status_regression(
        evidence.protected_baseline_statuses,
        evidence.protected_candidate_statuses,
    )
    if protected_status_regression is not None:
        return _decision(
            "reject",
            (
                "Protected status regression vetoed promotion at paired "
                f"observation {protected_status_regression + 1}"
            ),
        )

    validation_status_regression = _first_status_regression(
        evidence.validation_baseline_statuses,
        evidence.validation_candidate_statuses,
    )
    if validation_status_regression is not None:
        return _decision(
            "reject",
            (
                "Validation status regression vetoed promotion at paired "
                f"observation {validation_status_regression + 1}"
            ),
        )

    deltas = _paired_deltas(
        evidence.validation_baseline,
        evidence.validation_candidate,
        label="validation",
    )
    quality_delta = fmean(deltas)
    uncertainty = (
        policy.confidence_z * stdev(deltas) / sqrt(len(deltas))
        if len(deltas) > 1
        else 0.0
    )
    lower_bound = quality_delta - uncertainty

    protected_deltas = _paired_deltas(
        evidence.protected_baseline,
        evidence.protected_candidate,
        label="protected",
        allow_empty=True,
    )
    if any(delta < 0 for delta in protected_deltas):
        return _decision(
            "reject",
            "Protected evaluation regression vetoed promotion",
            quality_delta,
            lower_bound,
        )

    latency_ratio = _budget_ratio(
        evidence.baseline_latency_ms, evidence.candidate_latency_ms
    )
    if latency_ratio > policy.max_latency_ratio:
        return _decision(
            "reject",
            f"Latency budget exceeded: {latency_ratio:.3f}x",
            quality_delta,
            lower_bound,
        )

    cost_ratio = _budget_ratio(evidence.baseline_cost, evidence.candidate_cost)
    if cost_ratio > policy.max_cost_ratio:
        return _decision(
            "reject",
            f"Cost budget exceeded: {cost_ratio:.3f}x",
            quality_delta,
            lower_bound,
        )

    if quality_delta < 0:
        return _decision(
            "reject",
            f"Validation regression: {quality_delta:+.3f}",
            quality_delta,
            lower_bound,
        )

    if lower_bound < policy.min_validation_delta:
        return _decision(
            "reject",
            (
                "Validation uncertainty crosses promotion threshold: "
                f"lower bound {lower_bound:+.3f}"
            ),
            quality_delta,
            lower_bound,
        )

    return _decision(
        "promote",
        (
            "Validated quality gain cleared uncertainty, protected, latency, "
            "and cost gates"
        ),
        quality_delta,
        lower_bound,
    )


def _invalid_evidence_reason(evidence: PromotionEvidence) -> str | None:
    score_fields = (
        evidence.training_baseline,
        evidence.training_candidate,
        evidence.validation_baseline,
        evidence.validation_candidate,
        evidence.protected_baseline,
        evidence.protected_candidate,
    )
    if any(not isfinite(score) for scores in score_fields for score in scores):
        return "All evaluation scores must be finite"
    if any(not 0.0 <= score <= 1.0 for scores in score_fields for score in scores):
        return "All evaluation scores must be within [0, 1]"

    paired_fields = (
        (
            "training",
            evidence.training_baseline,
            evidence.training_candidate,
            evidence.training_baseline_statuses,
            evidence.training_candidate_statuses,
        ),
        (
            "validation",
            evidence.validation_baseline,
            evidence.validation_candidate,
            evidence.validation_baseline_statuses,
            evidence.validation_candidate_statuses,
        ),
        (
            "protected",
            evidence.protected_baseline,
            evidence.protected_candidate,
            evidence.protected_baseline_statuses,
            evidence.protected_candidate_statuses,
        ),
    )
    valid_statuses = {"pass", "fail", "error"}
    for label, baseline, candidate, baseline_statuses, candidate_statuses in paired_fields:
        lengths = {
            len(baseline),
            len(candidate),
            len(baseline_statuses),
            len(candidate_statuses),
        }
        if len(lengths) != 1:
            return f"{label.title()} evidence must contain paired scores and statuses"
        if any(
            status not in valid_statuses
            for status in (*baseline_statuses, *candidate_statuses)
        ):
            return f"{label.title()} evidence contains an invalid final status"

    resources = (
        evidence.baseline_latency_ms,
        evidence.candidate_latency_ms,
        evidence.baseline_cost,
        evidence.candidate_cost,
    )
    if any(not isfinite(value) for value in resources):
        return "Latency and cost metrics must be finite"
    if any(value < 0 for value in resources):
        return "Latency and cost metrics cannot be negative"
    return None


def _first_status_regression(
    baseline: tuple[str, ...],
    candidate: tuple[str, ...],
) -> int | None:
    rank = {"error": 0, "fail": 1, "pass": 2}
    return next(
        (
            index
            for index, (before, after) in enumerate(
                zip(baseline, candidate, strict=True)
            )
            if rank[after] < rank[before]
        ),
        None,
    )


def _paired_deltas(
    baseline: tuple[float, ...],
    candidate: tuple[float, ...],
    *,
    label: str,
    allow_empty: bool = False,
) -> tuple[float, ...]:
    if len(baseline) != len(candidate):
        raise ValueError(f"{label} evidence must contain paired observations")
    if not baseline and not allow_empty:
        raise ValueError(f"{label} evidence must not be empty")
    return tuple(after - before for before, after in zip(baseline, candidate, strict=True))


def _budget_ratio(baseline: float, candidate: float) -> float:
    if baseline == 0:
        return 1.0 if candidate == 0 else float("inf")
    return candidate / baseline


def _decision(
    action: Literal["promote", "reject", "rollback"],
    rationale: str,
    quality_delta: float = 0.0,
    lower_confidence_bound: float = 0.0,
) -> PromotionDecision:
    return PromotionDecision(
        action=action,
        rationale=rationale,
        quality_delta=quality_delta,
        lower_confidence_bound=lower_confidence_bound,
    )


def build_manifest(
    *,
    parent_content: str,
    candidate_content: str,
    datasets: DatasetBundle,
    evidence: PromotionEvidence,
    decision: PromotionDecision,
    mutations: tuple[Mutation, ...],
) -> CandidateManifest:
    metrics = {
        "validation_quality_delta": decision.quality_delta,
        "lower_confidence_bound": decision.lower_confidence_bound,
        "latency_ratio": _budget_ratio(
            evidence.baseline_latency_ms, evidence.candidate_latency_ms
        ),
        "cost_ratio": _budget_ratio(evidence.baseline_cost, evidence.candidate_cost),
    }
    return CandidateManifest(
        parent_hash=sha256(parent_content.encode()).hexdigest(),
        candidate_hash=sha256(candidate_content.encode()).hexdigest(),
        dataset_hashes=MappingProxyType(datasets.dataset_hashes()),
        metrics=MappingProxyType(metrics),
        rationale=decision.rationale,
        mutations=mutations,
    )
