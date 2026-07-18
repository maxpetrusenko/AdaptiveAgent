from app.knowledge.lineage import (
    embedding_fingerprint,
    stable_chunk_id,
    stable_content_hash,
    stable_source_id,
)


def test_lineage_is_stable_across_equivalent_text_and_changes_with_content():
    first_hash = stable_content_hash("Alpha\r\nBeta  \n")
    equivalent_hash = stable_content_hash("Alpha\nBeta")
    changed_hash = stable_content_hash("Alpha\nGamma")

    assert first_hash == equivalent_hash
    assert first_hash != changed_hash

    first_source = stable_source_id(
        tenant_id="tenant-a",
        external_id="handbook",
    )
    assert first_source == stable_source_id(
        tenant_id="tenant-a",
        external_id="handbook",
    )
    # Source identity survives a new document version; content/chunk hashes do not.
    assert first_source == stable_source_id(
        tenant_id="tenant-a",
        external_id="handbook",
    )
    assert first_source != stable_source_id(
        tenant_id="tenant-b",
        external_id="handbook",
    )

    assert stable_chunk_id(first_source, ordinal=0, text="Alpha") == stable_chunk_id(
        first_source,
        ordinal=0,
        text="Alpha",
    )
    assert stable_chunk_id(first_source, ordinal=0, text="Alpha") != stable_chunk_id(
        first_source,
        ordinal=1,
        text="Alpha",
    )


def test_embedding_fingerprint_captures_provider_model_dimension_and_revision():
    fingerprint = embedding_fingerprint(
        provider="anthropic-compatible",
        model="semantic-v1",
        dimensions=768,
        revision="2026-07-18",
    )

    assert len(fingerprint) == 64
    assert fingerprint == embedding_fingerprint(
        provider="anthropic-compatible",
        model="semantic-v1",
        dimensions=768,
        revision="2026-07-18",
    )
    assert fingerprint != embedding_fingerprint(
        provider="anthropic-compatible",
        model="semantic-v1",
        dimensions=384,
        revision="2026-07-18",
    )
