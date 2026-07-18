"""Stable identifiers for source, chunk, and embedding lineage."""

from __future__ import annotations

import json
import unicodedata
from hashlib import sha256


def normalize_text(text: str) -> str:
    """Normalize equivalent source text without changing meaningful whitespace."""
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.splitlines()).strip()


def _digest(namespace: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"namespace": namespace, **payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


def stable_content_hash(text: str) -> str:
    return _digest("knowledge-content-v1", {"text": normalize_text(text)})


def stable_source_id(*, tenant_id: str, external_id: str) -> str:
    normalized_tenant = tenant_id.strip()
    normalized_external_id = external_id.strip()
    if not normalized_tenant or not normalized_external_id:
        raise ValueError("tenant_id and external_id are required")
    return _digest(
        "knowledge-source-v1",
        {
            "tenant_id": normalized_tenant,
            "external_id": normalized_external_id,
        },
    )


def stable_chunk_id(source_id: str, *, ordinal: int, text: str) -> str:
    if ordinal < 0:
        raise ValueError("chunk ordinal must be non-negative")
    return _digest(
        "knowledge-chunk-v1",
        {
            "source_id": source_id,
            "ordinal": ordinal,
            "content_hash": stable_content_hash(text),
        },
    )


def embedding_fingerprint(
    *,
    provider: str,
    model: str,
    dimensions: int,
    revision: str,
) -> str:
    if dimensions <= 0:
        raise ValueError("embedding dimensions must be positive")
    return _digest(
        "knowledge-embedding-v1",
        {
            "provider": provider.strip().lower(),
            "model": model.strip(),
            "dimensions": dimensions,
            "revision": revision.strip(),
        },
    )
