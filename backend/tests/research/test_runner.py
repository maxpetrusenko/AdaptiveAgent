from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from app.research.ports import LeaseGrant
from app.research.runner import (
    InjectedCrashError,
    LeaseUnavailableError,
    ResearchRunner,
)
from app.research.types import (
    PlanArtifact,
    ResearchRun,
    RetrievedChunk,
    SynthesisArtifact,
    VerificationResult,
    create_research_run,
)


class FakeRunStore:
    def __init__(self, run: ResearchRun):
        self.runs = {run.id: deepcopy(run)}

    def load(self, run_id: str) -> ResearchRun:
        return deepcopy(self.runs[run_id])

    def compare_and_set(
        self,
        run: ResearchRun,
        *,
        expected_version: int,
        lease: LeaseGrant | None = None,
    ) -> bool:
        del lease
        current = self.runs[run.id]
        if current.version != expected_version:
            return False
        self.runs[run.id] = deepcopy(replace(run, version=expected_version + 1))
        return True


class FakeEffectJournal:
    def __init__(self):
        self.effects: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return deepcopy(self.effects.get(key))

    def seal(
        self,
        key: str,
        value: Any,
        *,
        lease: LeaseGrant | None = None,
    ) -> Any:
        del lease
        self.effects.setdefault(key, deepcopy(value))
        return deepcopy(self.effects[key])


class FakeLeasePort:
    def __init__(self):
        self.holders: dict[str, LeaseGrant] = {}
        self.fences: dict[str, int] = {}
        self.renew_calls = 0

    def acquire(
        self,
        run_id: str,
        worker_id: str,
        *,
        ttl_seconds: float,
    ) -> LeaseGrant | None:
        del ttl_seconds
        holder = self.holders.get(run_id)
        if holder is not None and holder.worker_id != worker_id:
            return None
        if holder is not None:
            return holder
        token = self.fences.get(run_id, 0) + 1
        self.fences[run_id] = token
        grant = LeaseGrant(run_id=run_id, worker_id=worker_id, fence_token=token)
        self.holders[run_id] = grant
        return grant

    def renew(self, lease: LeaseGrant, *, ttl_seconds: float) -> bool:
        del ttl_seconds
        if self.holders.get(lease.run_id) != lease:
            return False
        self.renew_calls += 1
        return True

    def is_current(self, lease: LeaseGrant) -> bool:
        return self.holders.get(lease.run_id) == lease

    def release(self, lease: LeaseGrant) -> None:
        if self.holders.get(lease.run_id) == lease:
            del self.holders[lease.run_id]


class FakePlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, goal: str) -> PlanArtifact:
        self.calls += 1
        return PlanArtifact(queries=(goal,))


class FakeRetriever:
    def __init__(self, chunks: tuple[RetrievedChunk, ...] | None = None):
        self.calls = 0
        self.chunks = chunks or (
            RetrievedChunk(citation_id="doc-1#chunk-1", text="Verified source"),
        )

    def retrieve(self, queries: tuple[str, ...]) -> tuple[RetrievedChunk, ...]:
        assert queries
        self.calls += 1
        return self.chunks


class FakeSynthesizer:
    def __init__(self, citations: tuple[str, ...] = ("doc-1#chunk-1",)):
        self.calls = 0
        self.citations = citations

    def synthesize(
        self,
        goal: str,
        chunks: tuple[RetrievedChunk, ...],
    ) -> SynthesisArtifact:
        assert goal
        assert chunks
        self.calls += 1
        return SynthesisArtifact(answer="Grounded answer", citation_ids=self.citations)


class FakeVerifier:
    def __init__(
        self,
        result: VerificationResult | None = None,
    ):
        self.calls = 0
        self.result = result or VerificationResult(
            passed=True,
            evidence_citation_ids=("doc-1#chunk-1",),
            reason="Citations support the answer",
        )

    def verify(
        self,
        goal: str,
        synthesis: SynthesisArtifact,
        chunks: tuple[RetrievedChunk, ...],
    ) -> VerificationResult:
        assert goal
        assert synthesis.answer
        assert chunks
        self.calls += 1
        return self.result


def build_runner(
    *,
    action_budget: int = 8,
    retriever: FakeRetriever | None = None,
    synthesizer: FakeSynthesizer | None = None,
    verifier: FakeVerifier | None = None,
    fault_hook=None,
):
    run = create_research_run(
        run_id="run-1",
        goal="Find the supported answer",
        action_budget=action_budget,
    )
    store = FakeRunStore(run)
    effects = FakeEffectJournal()
    leases = FakeLeasePort()
    planner = FakePlanner()
    retriever = retriever or FakeRetriever()
    synthesizer = synthesizer or FakeSynthesizer()
    verifier = verifier or FakeVerifier()
    runner = ResearchRunner(
        runs=store,
        effects=effects,
        leases=leases,
        planner=planner,
        retriever=retriever,
        synthesizer=synthesizer,
        verifier=verifier,
        fault_hook=fault_hook,
    )
    return runner, store, effects, leases, planner, retriever, synthesizer, verifier


def test_runner_autonomously_advances_all_four_steps() -> None:
    runner, _, _, _, planner, retriever, synthesizer, verifier = build_runner()

    completed = runner.run("run-1", worker_id="worker-1")

    assert completed.status == "completed"
    assert completed.cursor == 4
    assert [step.status for step in completed.steps] == ["completed"] * 4
    assert completed.actions_used == 4
    assert planner.calls == retriever.calls == synthesizer.calls == verifier.calls == 1


def test_resume_after_crash_reuses_the_sealed_retrieval_effect() -> None:
    crashed = False

    def crash_after_retrieval(step: str, effect_key: str) -> None:
        nonlocal crashed
        assert effect_key
        if step == "retrieve" and not crashed:
            crashed = True
            raise InjectedCrashError("process stopped after sealing retrieval")

    runner, store, effects, leases, planner, retriever, synthesizer, verifier = build_runner(
        fault_hook=crash_after_retrieval
    )

    with pytest.raises(InjectedCrashError):
        runner.run("run-1", worker_id="worker-1")

    assert retriever.calls == 1
    assert any(":retrieve:" in key for key in effects.effects)
    assert leases.holders == {}

    resumed = ResearchRunner(
        runs=store,
        effects=effects,
        leases=leases,
        planner=planner,
        retriever=retriever,
        synthesizer=synthesizer,
        verifier=verifier,
    ).run("run-1", worker_id="worker-2")

    assert resumed.status == "completed"
    assert retriever.calls == 1


def test_effect_lineage_is_bound_to_mode_and_adapter_fingerprint() -> None:
    run = create_research_run(
        run_id="live-run",
        goal="Find live evidence",
        execution_mode="live",
        adapter_fingerprint="live-rag-v2",
    )
    store = FakeRunStore(run)
    effects = FakeEffectJournal()
    runner = ResearchRunner(
        runs=store,
        effects=effects,
        leases=FakeLeasePort(),
        planner=FakePlanner(),
        retriever=FakeRetriever(),
        synthesizer=FakeSynthesizer(),
        verifier=FakeVerifier(),
    )

    runner.run("live-run", worker_id="worker-1")

    assert effects.effects
    assert all(":live:live-rag-v2:" in key for key in effects.effects)


def test_existing_lease_excludes_a_second_worker() -> None:
    runner, store, _, leases, *_ = build_runner()
    assert leases.acquire("run-1", "worker-1", ttl_seconds=30)

    with pytest.raises(LeaseUnavailableError):
        runner.run("run-1", worker_id="worker-2")

    assert store.load("run-1").cursor == 0


def test_runner_renews_the_lease_before_every_effect() -> None:
    runner, _, _, leases, *_ = build_runner()

    completed = runner.run("run-1", worker_id="worker-1")

    assert completed.status == "completed"
    assert leases.renew_calls == 4


def test_replan_preserves_completed_prefix_and_resets_only_suffix() -> None:
    verifier = FakeVerifier(
        VerificationResult(
            passed=False,
            evidence_citation_ids=(),
            reason="Insufficient support",
        )
    )
    runner, store, *_ = build_runner(verifier=verifier)
    blocked = runner.run("run-1", worker_id="worker-1")
    completed_prefix = blocked.steps[:3]

    replanned = runner.replan("run-1", worker_id="worker-1")

    assert blocked.status == "replan_required"
    assert replanned.status == "active"
    assert replanned.plan_version == blocked.plan_version + 1
    assert replanned.steps[:3] == completed_prefix
    assert replanned.steps[3].name == "verify"
    assert replanned.steps[3].status == "active"
    assert replanned.steps[3].attempt == blocked.steps[3].attempt + 1
    assert store.load("run-1") == replanned


def test_action_budget_escalates_before_starting_an_unfunded_step() -> None:
    runner, _, _, _, planner, retriever, synthesizer, verifier = build_runner(
        action_budget=2
    )

    escalated = runner.run("run-1", worker_id="worker-1")

    assert escalated.status == "escalated"
    assert escalated.terminal_reason == "action_budget_exhausted"
    assert escalated.actions_used == 2
    assert escalated.cursor == 2
    assert planner.calls == retriever.calls == 1
    assert synthesizer.calls == verifier.calls == 0


def test_missing_citation_evidence_blocks_completion() -> None:
    verifier = FakeVerifier(
        VerificationResult(
            passed=True,
            evidence_citation_ids=(),
            reason="Answer reads well but has no proof",
        )
    )
    runner, _, _, _, _, _, _, verifier = build_runner(verifier=verifier)

    blocked = runner.run("run-1", worker_id="worker-1")

    assert verifier.calls == 1
    assert blocked.status == "replan_required"
    assert blocked.cursor == 3
    assert blocked.terminal_reason == "missing_citation_evidence"
    assert blocked.steps[3].status == "active"


def test_fabricated_citation_cannot_complete_the_run() -> None:
    synthesizer = FakeSynthesizer(citations=("invented#citation",))
    verifier = FakeVerifier(
        VerificationResult(
            passed=True,
            evidence_citation_ids=("invented#citation",),
            reason="Self-consistent but not retrieved",
        )
    )
    runner, _, _, _, _, _, _, verifier = build_runner(
        synthesizer=synthesizer,
        verifier=verifier,
    )

    blocked = runner.run("run-1", worker_id="worker-1")

    assert verifier.calls == 0
    assert blocked.status == "replan_required"
    assert blocked.terminal_reason == "invalid_citation_evidence"
