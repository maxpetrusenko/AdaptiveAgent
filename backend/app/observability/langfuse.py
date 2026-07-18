"""Optional Langfuse wiring with metadata-only exports by default."""

from __future__ import annotations

from typing import Any


def langchain_callbacks(config: Any) -> list[Any]:
    """Create the LangChain callback only when both Langfuse keys are configured."""
    public_key = str(getattr(config, "langfuse_public_key", "") or "")
    secret_key = str(getattr(config, "langfuse_secret_key", "") or "")
    if not public_key or not secret_key:
        return []

    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=str(
            getattr(config, "langfuse_base_url", "https://cloud.langfuse.com")
        ),
        mask_otel_spans=_mask_content_attributes,
    )
    return [CallbackHandler(public_key=public_key)]


def _mask_content_attributes(*, params: Any) -> Any:
    """Redact prompt/output attributes while retaining safe timing and correlation data."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches: dict[str, Any] = {}
    sensitive_parts = ("content", "input", "message", "output", "prompt", "query")
    for identifier, span in params.spans.items():
        replacements = {
            key: "[REDACTED]"
            for key in span.attributes
            if any(part in key.casefold() for part in sensitive_parts)
        }
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches)
