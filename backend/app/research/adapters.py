"""Deterministic proof adapters for the provider-neutral research runner."""

from __future__ import annotations

from hashlib import sha256

from app.research.types import (
    PlanArtifact,
    RetrievedChunk,
    SynthesisArtifact,
    VerificationResult,
)


class DeterministicPlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, goal: str) -> PlanArtifact:
        self.calls += 1
        return PlanArtifact(queries=(goal.strip(),))


class DeterministicRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve(self, queries: tuple[str, ...]) -> tuple[RetrievedChunk, ...]:
        self.calls += 1
        query = " | ".join(queries)
        digest = sha256(query.encode()).hexdigest()[:12]
        return (
            RetrievedChunk(
                citation_id=f"fixture://research/{digest}#chunk-1",
                text=f"Deterministic evidence for: {query}",
            ),
        )


class DeterministicSynthesizer:
    def __init__(self):
        self.calls = 0

    def synthesize(
        self,
        goal: str,
        chunks: tuple[RetrievedChunk, ...],
    ) -> SynthesisArtifact:
        self.calls += 1
        citations = tuple(
            chunk.citation_id
            for chunk in chunks
            if chunk.citation_id is not None
        )
        return SynthesisArtifact(
            answer=f"{goal}: {chunks[0].text}",
            citation_ids=citations,
        )


class DeterministicVerifier:
    def __init__(self, *, passed: bool = True):
        self.calls = 0
        self.passed = passed

    def verify(
        self,
        goal: str,
        synthesis: SynthesisArtifact,
        chunks: tuple[RetrievedChunk, ...],
    ) -> VerificationResult:
        del goal, chunks
        self.calls += 1
        return VerificationResult(
            passed=self.passed,
            evidence_citation_ids=synthesis.citation_ids,
            reason=(
                "Deterministic citations verified"
                if self.passed
                else "Deterministic verifier rejected the answer"
            ),
        )


class DeterministicResearchAdapters:
    fingerprint = "deterministic-research-v1"

    def __init__(self, *, verification_passed: bool = True):
        self.planner = DeterministicPlanner()
        self.retriever = DeterministicRetriever()
        self.synthesizer = DeterministicSynthesizer()
        self.verifier = DeterministicVerifier(passed=verification_passed)
