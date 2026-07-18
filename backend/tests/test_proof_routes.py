from app.main import app


def test_proof_routes_are_part_of_the_shipped_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/knowledge/ingest" in paths
    assert "/api/knowledge/search" in paths
    assert "/api/knowledge/index/health" in paths
    assert "/api/research/{tenant_id}/runs" in paths
    assert "/api/research/{tenant_id}/runs/{run_id}/run" in paths
