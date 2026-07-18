"""Autonomous four-step research execution over durable ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from threading import Event, Thread
from typing import Any

from app.research.ports import (
    EffectJournal,
    LeaseFenceRejectedError,
    LeaseGrant,
    LeasePort,
    PlannerPort,
    RetrieverPort,
    RunStore,
    SynthesizerPort,
    VerifierPort,
)
from app.research.types import (
    PlanArtifact,
    ResearchArtifacts,
    ResearchRun,
    ResearchStep,
    RetrievedChunk,
    SynthesisArtifact,
    VerificationResult,
)

FaultHook = Callable[[str, str], None]


class LeaseUnavailableError(RuntimeError):
    pass


class LeaseLostError(LeaseUnavailableError):
    pass


class InvalidResearchStateError(RuntimeError):
    pass


class InjectedCrashError(RuntimeError):
    """Test and chaos-proof interruption after an effect becomes durable."""


class ResearchRunner:
    def __init__(
        self,
        *,
        runs: RunStore,
        effects: EffectJournal,
        leases: LeasePort,
        planner: PlannerPort,
        retriever: RetrieverPort,
        synthesizer: SynthesizerPort,
        verifier: VerifierPort,
        fault_hook: FaultHook | None = None,
        lease_ttl_seconds: float = 30,
        lease_heartbeat_seconds: float | None = None,
    ):
        self._runs = runs
        self._effects = effects
        self._leases = leases
        self._planner = planner
        self._retriever = retriever
        self._synthesizer = synthesizer
        self._verifier = verifier
        self._fault_hook = fault_hook
        self._lease_ttl_seconds = lease_ttl_seconds
        heartbeat_seconds = (
            lease_ttl_seconds / 3
            if lease_heartbeat_seconds is None
            else lease_heartbeat_seconds
        )
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")
        if heartbeat_seconds <= 0 or heartbeat_seconds >= lease_ttl_seconds:
            raise ValueError(
                "lease heartbeat must be positive and shorter than the lease TTL"
            )
        self._lease_heartbeat_seconds = heartbeat_seconds

    def run(self, run_id: str, *, worker_id: str) -> ResearchRun:
        lease = self._acquire(run_id, worker_id)
        heartbeat = _LeaseHeartbeat(
            leases=self._leases,
            lease=lease,
            ttl_seconds=self._lease_ttl_seconds,
            interval_seconds=self._lease_heartbeat_seconds,
        )
        heartbeat.start()
        try:
            while True:
                current = self._runs.load(run_id)
                if current.status != "active":
                    return current
                heartbeat.renew_now()
                heartbeat.assert_current()
                current = self._advance_once(current, lease, heartbeat)
                if current.status != "active":
                    return current
        finally:
            heartbeat.stop()
            self._leases.release(lease)

    def replan(self, run_id: str, *, worker_id: str) -> ResearchRun:
        lease = self._acquire(run_id, worker_id)
        heartbeat = _LeaseHeartbeat(
            leases=self._leases,
            lease=lease,
            ttl_seconds=self._lease_ttl_seconds,
            interval_seconds=self._lease_heartbeat_seconds,
        )
        heartbeat.start()
        try:
            heartbeat.renew_now()
            heartbeat.assert_current()
            current = self._runs.load(run_id)
            if current.status != "replan_required":
                raise InvalidResearchStateError(
                    "Only a run requiring replan can be replanned"
                )
            if current.cursor >= len(current.steps):
                raise InvalidResearchStateError("Completed runs have no plan suffix")

            prefix = current.steps[: current.cursor]
            suffix = tuple(
                replace(
                    step,
                    status="active" if index == 0 else "pending",
                    attempt=step.attempt + 1,
                )
                for index, step in enumerate(current.steps[current.cursor :])
            )
            candidate = replace(
                current,
                steps=prefix + suffix,
                status="active",
                plan_version=current.plan_version + 1,
                artifacts=_preserve_artifact_prefix(current),
                terminal_reason=None,
            )
            heartbeat.assert_current()
            return self._persist(
                candidate,
                expected_version=current.version,
                lease=lease,
            )
        finally:
            heartbeat.stop()
            self._leases.release(lease)

    def _advance_once(
        self,
        current: ResearchRun,
        lease: LeaseGrant,
        heartbeat: _LeaseHeartbeat,
    ) -> ResearchRun:
        if current.actions_used >= current.action_budget:
            return self._persist(
                replace(
                    current,
                    status="escalated",
                    terminal_reason="action_budget_exhausted",
                ),
                expected_version=current.version,
                lease=lease,
            )
        if current.cursor >= len(current.steps):
            raise InvalidResearchStateError("Active run has no active step")

        step = current.steps[current.cursor]
        effect_key = (
            f"research:{current.id}:{current.execution_mode}:"
            f"{current.adapter_fingerprint}:{current.plan_version}:"
            f"{step.name}:{step.attempt}"
        )
        effect = self._effects.get(effect_key)
        if effect is None:
            heartbeat.assert_current()
            produced = self._execute(current, step)
            heartbeat.assert_current()
            try:
                effect = self._effects.seal(
                    effect_key,
                    produced,
                    lease=lease,
                )
            except LeaseFenceRejectedError as error:
                raise LeaseLostError("Lease was fenced before effect seal") from error
            if self._fault_hook is not None:
                self._fault_hook(step.name, effect_key)

        heartbeat.assert_current()
        candidate = self._apply_effect(current, step, effect)
        candidate = replace(candidate, actions_used=current.actions_used + 1)
        return self._persist(
            candidate,
            expected_version=current.version,
            lease=lease,
        )

    def _execute(self, run: ResearchRun, step: ResearchStep) -> Any:
        if step.name == "plan":
            return self._planner.plan(run.goal)
        if step.name == "retrieve":
            plan = run.artifacts.plan
            if plan is None:
                raise InvalidResearchStateError("Retrieve requires a plan artifact")
            return self._retriever.retrieve(plan.queries)
        if step.name == "synthesize":
            if not run.artifacts.retrieval:
                raise InvalidResearchStateError("Synthesize requires retrieved chunks")
            return self._synthesizer.synthesize(run.goal, run.artifacts.retrieval)
        synthesis = run.artifacts.synthesis
        if synthesis is None:
            raise InvalidResearchStateError("Verify requires a synthesis artifact")
        if not synthesis.citation_ids:
            return VerificationResult(
                passed=False,
                evidence_citation_ids=(),
                reason="missing_citation_evidence",
            )
        retrieved_citations = {
            chunk.citation_id
            for chunk in run.artifacts.retrieval
            if chunk.citation_id is not None
        }
        if not set(synthesis.citation_ids) <= retrieved_citations:
            return VerificationResult(
                passed=False,
                evidence_citation_ids=(),
                reason="invalid_citation_evidence",
            )
        return self._verifier.verify(
            run.goal,
            synthesis,
            run.artifacts.retrieval,
        )

    def _apply_effect(
        self,
        run: ResearchRun,
        step: ResearchStep,
        effect: Any,
    ) -> ResearchRun:
        artifacts = run.artifacts
        if step.name == "plan":
            if not isinstance(effect, PlanArtifact) or not effect.queries:
                return _require_replan(run, "plan_produced_no_queries")
            artifacts = replace(artifacts, plan=effect)
        elif step.name == "retrieve":
            if not isinstance(effect, tuple) or not all(
                isinstance(chunk, RetrievedChunk) for chunk in effect
            ):
                raise InvalidResearchStateError("Retriever returned an invalid artifact")
            if not effect:
                return _require_replan(run, "retrieval_produced_no_evidence")
            artifacts = replace(artifacts, retrieval=effect)
        elif step.name == "synthesize":
            if not isinstance(effect, SynthesisArtifact) or not effect.answer:
                return _require_replan(run, "synthesis_produced_no_answer")
            artifacts = replace(artifacts, synthesis=effect)
        else:
            if not isinstance(effect, VerificationResult):
                raise InvalidResearchStateError("Verifier returned an invalid artifact")
            artifacts = replace(artifacts, verification=effect)
            failure = _verification_failure(run, effect)
            if failure is not None:
                return replace(
                    _require_replan(run, failure),
                    artifacts=artifacts,
                )

        return _complete_current_step(run, artifacts)

    def _persist(
        self,
        candidate: ResearchRun,
        *,
        expected_version: int,
        lease: LeaseGrant,
    ) -> ResearchRun:
        try:
            saved = self._runs.compare_and_set(
                candidate,
                expected_version=expected_version,
                lease=lease,
            )
        except LeaseFenceRejectedError as error:
            raise LeaseLostError("Lease was fenced before checkpoint") from error
        if not saved:
            return self._runs.load(candidate.id)
        return self._runs.load(candidate.id)

    def _acquire(self, run_id: str, worker_id: str) -> LeaseGrant:
        lease = self._leases.acquire(
            run_id,
            worker_id,
            ttl_seconds=self._lease_ttl_seconds,
        )
        if lease is None:
            raise LeaseUnavailableError(f"Run {run_id} is leased by another worker")
        return lease


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        leases: LeasePort,
        lease: LeaseGrant,
        ttl_seconds: float,
        interval_seconds: float,
    ):
        self._leases = leases
        self._lease = lease
        self._ttl_seconds = ttl_seconds
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._lost = Event()
        self._thread = Thread(
            target=self._beat,
            name=f"research-lease-{lease.run_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self._interval_seconds * 2))

    def assert_current(self) -> None:
        if self._lost.is_set() or not self._leases.is_current(self._lease):
            self._lost.set()
            raise LeaseLostError(
                f"Run {self._lease.run_id} lease was lost or fenced"
            )

    def renew_now(self) -> None:
        try:
            renewed = self._leases.renew(
                self._lease,
                ttl_seconds=self._ttl_seconds,
            )
        except Exception:
            renewed = False
        if not renewed:
            self._lost.set()
            raise LeaseLostError(
                f"Run {self._lease.run_id} lease could not be renewed"
            )

    def _beat(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                renewed = self._leases.renew(
                    self._lease,
                    ttl_seconds=self._ttl_seconds,
                )
            except Exception:
                renewed = False
            if not renewed:
                self._lost.set()
                return


def _complete_current_step(
    run: ResearchRun,
    artifacts: ResearchArtifacts,
) -> ResearchRun:
    steps = list(run.steps)
    steps[run.cursor] = replace(steps[run.cursor], status="completed")
    next_cursor = run.cursor + 1
    if next_cursor == len(steps):
        return replace(
            run,
            steps=tuple(steps),
            cursor=next_cursor,
            status="completed",
            artifacts=artifacts,
            terminal_reason=None,
        )
    steps[next_cursor] = replace(steps[next_cursor], status="active")
    return replace(
        run,
        steps=tuple(steps),
        cursor=next_cursor,
        artifacts=artifacts,
        terminal_reason=None,
    )


def _require_replan(run: ResearchRun, reason: str) -> ResearchRun:
    return replace(run, status="replan_required", terminal_reason=reason)


def _verification_failure(
    run: ResearchRun,
    result: VerificationResult,
) -> str | None:
    if not result.passed and result.reason in {
        "invalid_citation_evidence",
        "missing_citation_evidence",
    }:
        return result.reason
    synthesis = run.artifacts.synthesis
    if synthesis is None:
        return "missing_citation_evidence"
    permitted = set(synthesis.citation_ids)
    evidence = set(result.evidence_citation_ids)
    if not evidence:
        return "missing_citation_evidence"
    if not evidence <= permitted:
        return "invalid_citation_evidence"
    if not result.passed:
        return result.reason or "verification_failed"
    return None


def _preserve_artifact_prefix(run: ResearchRun) -> ResearchArtifacts:
    artifacts = run.artifacts
    if run.cursor <= 0:
        return ResearchArtifacts()
    if run.cursor == 1:
        return replace(artifacts, retrieval=(), synthesis=None, verification=None)
    if run.cursor == 2:
        return replace(artifacts, synthesis=None, verification=None)
    return replace(artifacts, verification=None)
