"""Shared data structures for comparative benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CaseResult:
    case_name: str
    status: str
    score: float
    error: str | None
    actual_output: str
    latency_ms: int
    usage: dict[str, Any] | None = None


@dataclass
class SystemSummary:
    system: str
    pass_rate: float
    passed: int
    failed: int
    avg_latency_ms: float
    hallucination_failures: int
    tag_pass_rates: dict[str, float]
    results: list[CaseResult]
    metadata: dict[str, Any]
    pass_rate_ci_95: tuple[float, float] = (0.0, 0.0)
