"""Deterministic, model-free tests for governed candidate promotion."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from importlib.util import find_spec
from math import inf, nan

import pytest

from app.adapt.promotion import (
    DatasetBundle,
    DatasetCase,
    Mutation,
    PromotionEvidence,
    PromotionRegistry,
    build_manifest,
    evaluate_promotion,
)


def test_promotion_module_is_available():
    assert find_spec("app.adapt.promotion") is not None


def test_promotion_module_exposes_governed_gate_contract():
    from app.adapt import promotion

    expected = {
        "CandidateManifest",
        "DatasetBundle",
        "DatasetCase",
        "Mutation",
        "PromotionDecision",
        "PromotionEvidence",
        "PromotionPolicy",
        "PromotionRegistry",
        "build_manifest",
        "evaluate_promotion",
    }

    assert expected <= set(dir(promotion))


def test_proposal_context_contains_only_training_cases():
    datasets = DatasetBundle(
        training=(DatasetCase("train-1", "training failure"),),
        validation=(DatasetCase("validation-1", "sealed validation"),),
        protected=(DatasetCase("protected-1", "protected safety"),),
    )

    context = datasets.proposal_context()

    assert context == datasets.training
    serialized = repr(context)
    assert "validation-1" not in serialized
    assert "sealed validation" not in serialized
    assert "protected-1" not in serialized
    assert "protected safety" not in serialized


@pytest.mark.parametrize(
    ("validation_case", "error_match"),
    [
        (DatasetCase("train-1", "different content"), "case IDs"),
        (DatasetCase("validation-1", "same content"), "case content"),
    ],
)
def test_dataset_splits_reject_identity_or_content_overlap(
    validation_case: DatasetCase,
    error_match: str,
):
    with pytest.raises(ValueError, match=error_match):
        DatasetBundle(
            training=(DatasetCase("train-1", "same content"),),
            validation=(validation_case,),
            protected=(),
        )


def _evidence(**overrides) -> PromotionEvidence:
    values = {
        "training_baseline": (0.5, 0.5, 0.5, 0.5),
        "training_candidate": (0.7, 0.7, 0.7, 0.7),
        "validation_baseline": (0.5, 0.5, 0.5, 0.5),
        "validation_candidate": (0.7, 0.7, 0.7, 0.7),
        "protected_baseline": (1.0, 1.0),
        "protected_candidate": (1.0, 1.0),
        "baseline_latency_ms": 100.0,
        "candidate_latency_ms": 100.0,
        "baseline_cost": 1.0,
        "candidate_cost": 1.0,
        "training_baseline_statuses": ("pass", "pass", "pass", "pass"),
        "training_candidate_statuses": ("pass", "pass", "pass", "pass"),
        "validation_baseline_statuses": ("pass", "pass", "pass", "pass"),
        "validation_candidate_statuses": ("pass", "pass", "pass", "pass"),
        "protected_baseline_statuses": ("pass", "pass"),
        "protected_candidate_statuses": ("pass", "pass"),
    }
    values.update(overrides)
    return PromotionEvidence(**values)


def _prompt_mutation() -> tuple[Mutation, ...]:
    return (Mutation("prompt", "system", "old", "new"),)


def test_clear_validated_gain_promotes():
    decision = evaluate_promotion(_evidence(), _prompt_mutation())

    assert decision.action == "promote"
    assert decision.quality_delta == pytest.approx(0.2)
    assert decision.lower_confidence_bound >= 0.05


def test_noisy_gain_with_uncertainty_crossing_threshold_rejects():
    evidence = _evidence(
        validation_baseline=(0.5, 0.5, 0.5, 0.5),
        validation_candidate=(0.8, 0.4, 0.8, 0.4),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "uncertainty" in decision.rationale.lower()


def test_any_protected_regression_vetoes_promotion():
    evidence = _evidence(protected_candidate=(1.0, 0.0))

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "protected" in decision.rationale.lower()


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"candidate_latency_ms": 126.0}, "latency"),
        ({"candidate_cost": 1.26}, "cost"),
    ],
)
def test_latency_and_cost_budgets_veto_promotion(overrides: dict, reason: str):
    decision = evaluate_promotion(_evidence(**overrides), _prompt_mutation())

    assert decision.action == "reject"
    assert reason in decision.rationale.lower()


def test_training_gain_cannot_override_validation_regression():
    evidence = _evidence(
        training_candidate=(1.0, 1.0, 1.0, 1.0),
        validation_candidate=(0.4, 0.4, 0.4, 0.4),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "validation" in decision.rationale.lower()


def test_arbitrary_code_mutation_is_rejected():
    mutation = Mutation("code", "app.eval.grader", "safe", "always pass")

    decision = evaluate_promotion(_evidence(), (mutation,))

    assert decision.action == "reject"
    assert "mutation" in decision.rationale.lower()


def test_tool_description_is_an_allowed_mutation():
    mutation = Mutation(
        "tool_description",
        "calculator",
        "Calculate.",
        "Use for exact arithmetic.",
    )

    decision = evaluate_promotion(_evidence(), (mutation,))

    assert decision.action == "promote"


def test_candidate_manifest_records_immutable_replay_lineage():
    datasets = DatasetBundle(
        training=(DatasetCase("train-1", "training"),),
        validation=(DatasetCase("validation-1", "validation"),),
        protected=(DatasetCase("protected-1", "protected"),),
    )
    evidence = _evidence()
    mutations = _prompt_mutation()
    decision = evaluate_promotion(evidence, mutations)

    manifest = build_manifest(
        parent_content="parent prompt",
        candidate_content="candidate prompt",
        datasets=datasets,
        evidence=evidence,
        decision=decision,
        mutations=mutations,
    )

    assert manifest.parent_hash == sha256(b"parent prompt").hexdigest()
    assert manifest.candidate_hash == sha256(b"candidate prompt").hexdigest()
    assert set(manifest.dataset_hashes) == {"training", "validation", "protected"}
    assert all(len(value) == 64 for value in manifest.dataset_hashes.values())
    assert manifest.metrics["validation_quality_delta"] == pytest.approx(0.2)
    assert manifest.metrics["lower_confidence_bound"] == pytest.approx(0.2)
    assert manifest.metrics["latency_ratio"] == pytest.approx(1.0)
    assert manifest.metrics["cost_ratio"] == pytest.approx(1.0)
    assert manifest.rationale == decision.rationale
    assert manifest.mutations == mutations
    with pytest.raises(TypeError):
        manifest.dataset_hashes["training"] = "tampered"


def test_concurrent_promotion_has_exactly_one_winner():
    registry = PromotionRegistry("parent")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda candidate: registry.compare_and_swap("parent", candidate),
                ("candidate-a", "candidate-b"),
            )
        )

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert registry.current_hash in {"candidate-a", "candidate-b"}


def test_rollback_restores_the_previous_version_once():
    registry = PromotionRegistry("parent")
    assert registry.compare_and_swap("parent", "candidate") is True

    assert registry.rollback("candidate") is True
    assert registry.current_hash == "parent"
    assert registry.rollback("candidate") is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"training_candidate": (0.7, 0.7, nan, 0.7)},
        {"validation_candidate": (0.7, 0.7, inf, 0.7)},
        {"protected_candidate": (1.0, nan)},
    ],
)
def test_non_finite_scores_fail_closed(overrides: dict):
    decision = evaluate_promotion(_evidence(**overrides), _prompt_mutation())

    assert decision.action == "reject"
    assert "finite" in decision.rationale.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"training_candidate": (0.7, 0.7, 100.0, 0.7)},
        {"validation_candidate": (0.7, 0.7, -0.1, 0.7)},
        {"protected_candidate": (1.0, 1.01)},
    ],
)
def test_scores_outside_unit_interval_fail_closed(overrides: dict):
    decision = evaluate_promotion(_evidence(**overrides), _prompt_mutation())

    assert decision.action == "reject"
    assert "[0, 1]" in decision.rationale


@pytest.mark.parametrize("candidate_status", ["fail", "error"])
def test_protected_pass_status_regression_vetoes_unchanged_score(
    candidate_status: str,
):
    evidence = _evidence(
        protected_candidate_statuses=("pass", candidate_status),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "protected" in decision.rationale.lower()
    assert "status" in decision.rationale.lower()


@pytest.mark.parametrize(
    ("baseline_status", "candidate_status"),
    [("pass", "fail"), ("pass", "error"), ("fail", "error")],
)
def test_validation_status_regression_vetoes_score_gain(
    baseline_status: str,
    candidate_status: str,
):
    evidence = _evidence(
        validation_baseline_statuses=("pass", baseline_status, "pass", "pass"),
        validation_candidate_statuses=("pass", candidate_status, "pass", "pass"),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "validation" in decision.rationale.lower()
    assert "status" in decision.rationale.lower()


def test_status_evidence_must_be_paired_with_scores():
    evidence = _evidence(validation_candidate_statuses=("pass",))

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "paired" in decision.rationale.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"baseline_latency_ms": inf},
        {"candidate_latency_ms": nan},
        {"baseline_cost": inf},
        {"candidate_cost": nan},
    ],
)
def test_non_finite_resource_metrics_fail_closed(overrides: dict):
    decision = evaluate_promotion(_evidence(**overrides), _prompt_mutation())

    assert decision.action == "reject"
    assert "finite" in decision.rationale.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"baseline_latency_ms": -1.0},
        {"candidate_latency_ms": -1.0},
        {"baseline_cost": -1.0},
        {"candidate_cost": -1.0},
    ],
)
def test_negative_resource_metrics_fail_closed(overrides: dict):
    decision = evaluate_promotion(_evidence(**overrides), _prompt_mutation())

    assert decision.action == "reject"
    assert "negative" in decision.rationale.lower()


def test_single_validation_observation_cannot_estimate_uncertainty():
    evidence = _evidence(
        validation_baseline=(0.5,),
        validation_candidate=(0.8,),
        validation_baseline_statuses=("pass",),
        validation_candidate_statuses=("pass",),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "observations" in decision.rationale.lower()


def test_empty_protected_suite_fails_closed():
    evidence = _evidence(
        protected_baseline=(),
        protected_candidate=(),
        protected_baseline_statuses=(),
        protected_candidate_statuses=(),
    )

    decision = evaluate_promotion(evidence, _prompt_mutation())

    assert decision.action == "reject"
    assert "protected" in decision.rationale.lower()
