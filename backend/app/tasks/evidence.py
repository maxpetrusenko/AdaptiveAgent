"""Trust-boundary helpers for task evidence."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from app.tasks.schemas import AdvanceCommand, TrustedVerificationResult

TRUSTED_SOURCES = frozenset({"ci", "review", "runtime"})
TRUSTED_VERIFIERS = frozenset({"pytest", "maintainer", "system"})


class InvalidEvidenceError(Exception):
    pass


def _dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def trusted_request_hash(
    command: AdvanceCommand,
    trusted_results: tuple[TrustedVerificationResult, ...],
) -> str:
    payload = {
        "command": command.model_dump(mode="json", exclude={"idempotency_key"}),
        "trusted_results": [
            {
                "criterion_id": result.criterion_id,
                "summary": result.summary,
                "artifact_ref": result.artifact_ref,
                "source": result.source,
                "verifier": result.verifier,
            }
            for result in trusted_results
        ],
    }
    return sha256(_dump(payload).encode()).hexdigest()


def apply_evidence(
    criteria: list[dict[str, Any]],
    command: AdvanceCommand,
    recorded_at: str,
    trusted_results: tuple[TrustedVerificationResult, ...] = (),
) -> None:
    criteria_by_id = {criterion["id"]: criterion for criterion in criteria}
    unknown = [
        evidence.criterion_id
        for evidence in [*command.evidence, *trusted_results]
        if evidence.criterion_id not in criteria_by_id
    ]
    if unknown:
        raise InvalidEvidenceError(f"Unknown acceptance criteria: {', '.join(unknown)}")

    for evidence in command.evidence:
        criteria_by_id[evidence.criterion_id]["evidence"].append(
            {
                "summary": evidence.summary,
                "artifact_ref": evidence.artifact_ref,
                "digest": evidence.digest,
                "source": "public_claim",
                "verifier": "none",
                "status": "unverified",
                "recorded_at": recorded_at,
            }
        )

    for result in trusted_results:
        artifact_ref = result.artifact_ref.strip()
        criterion_id = result.criterion_id.strip()
        summary = result.summary.strip()
        if (
            not criterion_id
            or not summary
            or not artifact_ref
            or result.source not in TRUSTED_SOURCES
            or result.verifier not in TRUSTED_VERIFIERS
        ):
            raise InvalidEvidenceError("Invalid trusted verification result")
        digest_payload = _dump(
            {
                "artifact_ref": artifact_ref,
                "criterion_id": criterion_id,
                "source": result.source,
                "summary": summary,
                "verifier": result.verifier,
            }
        )
        criteria_by_id[criterion_id]["evidence"].append(
            {
                "summary": summary,
                "artifact_ref": artifact_ref,
                "digest": sha256(digest_payload.encode()).hexdigest(),
                "source": result.source,
                "verifier": result.verifier,
                "status": "verified",
                "recorded_at": recorded_at,
            }
        )


def missing_criteria(criteria: list[dict[str, Any]]) -> list[str]:
    return [
        criterion["id"]
        for criterion in criteria
        if not any(
            evidence.get("status") == "verified"
            and bool(str(evidence.get("artifact_ref") or "").strip())
            and bool(str(evidence.get("digest") or "").strip())
            and evidence.get("source") in TRUSTED_SOURCES
            and evidence.get("verifier") in TRUSTED_VERIFIERS
            for evidence in criterion["evidence"]
        )
    ]
