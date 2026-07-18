"""Trace metadata construction with content minimization and secret redaction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.observability.context import TraceContext, correlation_fields

REDACTED = "[REDACTED]"

_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)
_CONTENT_KEYS = {
    "content",
    "document",
    "input",
    "messages",
    "output",
    "prompt",
    "query",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\b(?:sk|pk)-(?:ant-)?[A-Za-z0-9_-]{8,}"),
)


def build_trace_metadata(
    *,
    context: TraceContext,
    attributes: Mapping[str, Any] | None = None,
    content: Any = None,
    capture_content: bool = False,
) -> dict[str, Any]:
    """Build SDK-neutral metadata; payload content is excluded unless opted in."""
    metadata = _sanitize_mapping(attributes or {}, allow_content=False)
    metadata.update(correlation_fields(context))
    if capture_content and content is not None:
        metadata["content"] = _sanitize(content, allow_content=True)
    return metadata


def _sanitize_mapping(
    value: Mapping[str, Any],
    *,
    allow_content: bool,
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).strip().casefold().replace("-", "_")
        if any(part in normalized_key for part in _SECRET_KEY_PARTS):
            sanitized[str(key)] = REDACTED
        elif not allow_content and normalized_key in _CONTENT_KEYS:
            continue
        else:
            sanitized[str(key)] = _sanitize(item, allow_content=allow_content)
    return sanitized


def _sanitize(value: Any, *, allow_content: bool) -> Any:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, allow_content=allow_content)
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, allow_content=allow_content) for item in value]
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
    ):
        return REDACTED
    return value
