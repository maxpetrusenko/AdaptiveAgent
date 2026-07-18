import json
import sqlite3
from dataclasses import replace

from app.research.persistence import SqliteResearchRepository
from app.research.types import (
    PlanArtifact,
    ResearchArtifacts,
    RetrievedChunk,
    create_research_run,
)


def test_run_survives_repository_restart(tmp_path) -> None:
    database_path = tmp_path / "research.db"
    first = SqliteResearchRepository(database_path).for_tenant("tenant-a")
    run = create_research_run(run_id="shared-run", goal="First goal")
    first.create(run)
    assert first.compare_and_set(
        replace(run, terminal_reason="checkpoint"),
        expected_version=0,
    )

    restarted = SqliteResearchRepository(database_path).for_tenant("tenant-a")
    loaded = restarted.load("shared-run")

    assert loaded.goal == "First goal"
    assert loaded.version == 1
    assert loaded.terminal_reason == "checkpoint"


def test_execution_mode_and_adapter_fingerprint_survive_restart(tmp_path) -> None:
    database_path = tmp_path / "research.db"
    first = SqliteResearchRepository(database_path).for_tenant("tenant-a")
    first.create(
        create_research_run(
            run_id="live-run",
            goal="Use live evidence",
            execution_mode="live",
            adapter_fingerprint="live-rag-v2",
        )
    )

    loaded = SqliteResearchRepository(database_path).for_tenant("tenant-a").load(
        "live-run"
    )

    assert loaded.execution_mode == "live"
    assert loaded.adapter_fingerprint == "live-rag-v2"


def test_retrieval_lineage_survives_checkpoint_and_restart(tmp_path) -> None:
    database_path = tmp_path / "research.db"
    first = SqliteResearchRepository(database_path).for_tenant("tenant-a")
    run = create_research_run(run_id="lineage-run", goal="Keep exact evidence")
    chunk = RetrievedChunk(
        citation_id="chunk-1",
        text="Sealed evidence",
        source_id="source-1",
        content_hash="content-hash-1",
        fusion_score=0.03,
        dense_score=0.91,
        lexical_score=1.4,
        dense_rank=1,
        lexical_rank=2,
        index_version="index-v3",
        embedding_fingerprint="embedding-v2",
    )
    first.create(run)
    assert first.compare_and_set(
        replace(run, artifacts=ResearchArtifacts(retrieval=(chunk,))),
        expected_version=0,
    )

    loaded = SqliteResearchRepository(database_path).for_tenant("tenant-a").load(
        "lineage-run"
    )

    assert loaded.artifacts.retrieval == (chunk,)


def test_legacy_run_payload_migrates_to_deterministic_execution(tmp_path) -> None:
    database_path = tmp_path / "research.db"
    tenant = SqliteResearchRepository(database_path).for_tenant("tenant-a")
    tenant.create(create_research_run(run_id="legacy-run", goal="Legacy goal"))
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json FROM research_runs
            WHERE tenant_id = ? AND run_id = ?
            """,
            ("tenant-a", "legacy-run"),
        ).fetchone()
        payload = json.loads(row[0])
        payload.pop("execution_mode")
        payload.pop("adapter_fingerprint")
        connection.execute(
            """
            UPDATE research_runs SET payload_json = ?
            WHERE tenant_id = ? AND run_id = ?
            """,
            (json.dumps(payload), "tenant-a", "legacy-run"),
        )

    loaded = tenant.load("legacy-run")

    assert loaded.execution_mode == "deterministic"
    assert loaded.adapter_fingerprint == "deterministic-research-v1"


def test_same_run_and_effect_keys_are_isolated_by_tenant(tmp_path) -> None:
    repository = SqliteResearchRepository(tmp_path / "research.db")
    tenant_a = repository.for_tenant("tenant-a")
    tenant_b = repository.for_tenant("tenant-b")
    tenant_a.create(create_research_run(run_id="same-run", goal="Tenant A goal"))
    tenant_b.create(create_research_run(run_id="same-run", goal="Tenant B goal"))

    assert tenant_a.seal("same-effect", PlanArtifact(("alpha",))) == PlanArtifact(
        ("alpha",)
    )
    assert tenant_b.seal("same-effect", PlanArtifact(("beta",))) == PlanArtifact(
        ("beta",)
    )

    assert tenant_a.load("same-run").goal == "Tenant A goal"
    assert tenant_b.load("same-run").goal == "Tenant B goal"
    assert tenant_a.get("same-effect") == PlanArtifact(("alpha",))
    assert tenant_b.get("same-effect") == PlanArtifact(("beta",))
    assert tenant_a.acquire("same-run", "worker-a", ttl_seconds=30)
    assert tenant_b.acquire("same-run", "worker-b", ttl_seconds=30)


def test_sealed_effect_is_immutable_and_survives_restart(tmp_path) -> None:
    database_path = tmp_path / "research.db"
    first = SqliteResearchRepository(database_path).for_tenant("tenant-a")

    original = first.seal("effect-1", PlanArtifact(("original",)))
    replay = first.seal("effect-1", PlanArtifact(("replacement",)))
    restarted = SqliteResearchRepository(database_path).for_tenant("tenant-a")

    assert original == replay == PlanArtifact(("original",))
    assert restarted.get("effect-1") == PlanArtifact(("original",))
    assert restarted.count_effects() == 1
