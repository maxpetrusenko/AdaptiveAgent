from __future__ import annotations

import threading
import time

import pytest

from app.research.adapters import (
    DeterministicPlanner,
    DeterministicSynthesizer,
    DeterministicVerifier,
)
from app.research.persistence import SqliteResearchRepository
from app.research.runner import LeaseUnavailableError, ResearchRunner
from app.research.types import RetrievedChunk, create_research_run


class SlowRetriever:
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()

    def retrieve(self, queries: tuple[str, ...]) -> tuple[RetrievedChunk, ...]:
        self.calls += 1
        self.started.set()
        time.sleep(0.5)
        return (
            RetrievedChunk(
                citation_id="fixture://slow#chunk-1",
                text=f"Evidence for {queries[0]}",
            ),
        )


def build_runner(repository, retriever: SlowRetriever) -> ResearchRunner:
    return ResearchRunner(
        runs=repository,
        effects=repository,
        leases=repository,
        planner=DeterministicPlanner(),
        retriever=retriever,
        synthesizer=DeterministicSynthesizer(),
        verifier=DeterministicVerifier(),
        lease_ttl_seconds=0.2,
        lease_heartbeat_seconds=0.02,
    )


def test_heartbeat_and_fence_exclude_second_worker_during_slow_effect(
    tmp_path,
) -> None:
    repository = SqliteResearchRepository(tmp_path / "research.db").for_tenant(
        "tenant-a"
    )
    repository.create(
        create_research_run(
            run_id="run-1",
            goal="Research a slow source",
            action_budget=8,
        )
    )
    retriever = SlowRetriever()
    first_runner = build_runner(repository, retriever)
    second_runner = build_runner(repository, retriever)
    first_result = []
    first_errors = []

    def run_first_worker() -> None:
        try:
            first_result.append(first_runner.run("run-1", worker_id="worker-1"))
        except Exception as error:  # pragma: no cover - asserted through first_errors
            first_errors.append(error)

    worker_thread = threading.Thread(target=run_first_worker)
    worker_thread.start()
    assert retriever.started.wait(timeout=1)
    time.sleep(0.3)

    with pytest.raises(LeaseUnavailableError):
        second_runner.run("run-1", worker_id="worker-2")

    worker_thread.join(timeout=2)

    assert not worker_thread.is_alive()
    assert first_errors == []
    assert first_result[0].status == "completed"
    assert repository.load("run-1").status == "completed"
    assert retriever.calls == 1
    assert repository.count_effects(step="retrieve") == 1
    assert repository.acquire("run-1", "worker-3", ttl_seconds=0.2)
