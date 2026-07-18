"""Narrow ports for wiring the research runner to durable infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.research.types import (
    PlanArtifact,
    ResearchRun,
    RetrievedChunk,
    SynthesisArtifact,
    VerificationResult,
)


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    run_id: str
    worker_id: str
    fence_token: int


class LeaseFenceRejectedError(RuntimeError):
    pass


class RunStore(Protocol):
    def load(self, run_id: str) -> ResearchRun: ...

    def compare_and_set(
        self,
        run: ResearchRun,
        *,
        expected_version: int,
        lease: LeaseGrant | None = None,
    ) -> bool: ...


class EffectJournal(Protocol):
    def get(self, key: str) -> Any | None: ...

    def seal(
        self,
        key: str,
        value: Any,
        *,
        lease: LeaseGrant | None = None,
    ) -> Any: ...


class LeasePort(Protocol):
    def acquire(
        self,
        run_id: str,
        worker_id: str,
        *,
        ttl_seconds: float,
    ) -> LeaseGrant | None: ...

    def renew(
        self,
        lease: LeaseGrant,
        *,
        ttl_seconds: float,
    ) -> bool: ...

    def is_current(self, lease: LeaseGrant) -> bool: ...

    def release(self, lease: LeaseGrant) -> None: ...


class PlannerPort(Protocol):
    def plan(self, goal: str) -> PlanArtifact: ...


class RetrieverPort(Protocol):
    def retrieve(self, queries: tuple[str, ...]) -> tuple[RetrievedChunk, ...]: ...


class SynthesizerPort(Protocol):
    def synthesize(
        self,
        goal: str,
        chunks: tuple[RetrievedChunk, ...],
    ) -> SynthesisArtifact: ...


class VerifierPort(Protocol):
    def verify(
        self,
        goal: str,
        synthesis: SynthesisArtifact,
        chunks: tuple[RetrievedChunk, ...],
    ) -> VerificationResult: ...
