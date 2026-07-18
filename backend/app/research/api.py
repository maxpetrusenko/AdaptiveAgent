"""Dependency-injected API router for durable research proof runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from app.research.adapters import DeterministicResearchAdapters
from app.research.persistence import (
    ResearchRunExistsError,
    SqliteResearchRepository,
)
from app.research.runner import (
    InjectedCrashError,
    InvalidResearchStateError,
    LeaseUnavailableError,
    ResearchRunner,
)
from app.research.types import (
    DEFAULT_ADAPTER_FINGERPRINTS,
    ExecutionMode,
    ResearchRun,
    create_research_run,
)


class CreateResearchRunRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=4_000)
    action_budget: int = Field(default=8, ge=1, le=1_000)
    mode: ExecutionMode = "deterministic"


class ExecuteResearchRunRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    inject_crash_after: Literal["retrieve"] | None = None
    mode: ExecutionMode | None = None


class ReplanResearchRunRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)


def build_research_router(
    *,
    repository: SqliteResearchRepository,
    operator_guard: Callable[..., Any],
    adapters: DeterministicResearchAdapters | None = None,
    live_adapters: Any | None = None,
    proof_mode: bool = False,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/research",
        tags=["research"],
        dependencies=[Depends(operator_guard)],
    )
    services = adapters or DeterministicResearchAdapters()

    @router.post(
        "/{tenant_id}/runs",
        status_code=status.HTTP_201_CREATED,
    )
    def create_run(
        request: CreateResearchRunRequest,
        tenant_id: str = Path(min_length=1, max_length=128),
    ) -> dict[str, Any]:
        tenant = repository.for_tenant(tenant_id)
        adapter_source = services if request.mode == "deterministic" else live_adapters
        adapter_fingerprint = _adapter_fingerprint(adapter_source, request.mode)
        try:
            created = tenant.create(
                create_research_run(
                    run_id=request.run_id,
                    goal=request.goal,
                    action_budget=request.action_budget,
                    execution_mode=request.mode,
                    adapter_fingerprint=adapter_fingerprint,
                )
            )
        except ResearchRunExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return asdict(created)

    @router.get("/{tenant_id}/runs/{run_id}")
    def detail_run(
        tenant_id: str = Path(min_length=1, max_length=128),
        run_id: str = Path(min_length=1, max_length=128),
    ) -> dict[str, Any]:
        try:
            return asdict(repository.for_tenant(tenant_id).load(run_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Research run not found") from error

    @router.post("/{tenant_id}/runs/{run_id}/run")
    def execute_run(
        request: ExecuteResearchRunRequest,
        tenant_id: str = Path(min_length=1, max_length=128),
        run_id: str = Path(min_length=1, max_length=128),
    ) -> dict[str, Any]:
        if request.inject_crash_after is not None and not proof_mode:
            raise HTTPException(
                status_code=403,
                detail="Crash injection is available only in proof mode",
            )
        tenant = repository.for_tenant(tenant_id)
        try:
            persisted = tenant.load(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Research run not found") from error
        if request.mode is not None and request.mode != persisted.execution_mode:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "research_mode_mismatch",
                    "message": (
                        f"Run uses {persisted.execution_mode} mode; "
                        f"received {request.mode}"
                    ),
                },
            )
        selected_services = _services_for_run(
            persisted,
            tenant_id=tenant_id,
            deterministic=services,
            live=live_adapters,
        )
        crash_once = False

        def fault_hook(step: str, effect_key: str) -> None:
            nonlocal crash_once
            if step == request.inject_crash_after and not crash_once:
                crash_once = True
                raise InjectedCrashError(effect_key)

        runner = _build_runner(
            tenant,
            selected_services,
            fault_hook=fault_hook if request.inject_crash_after else None,
        )
        try:
            return asdict(runner.run(run_id, worker_id=request.worker_id))
        except InjectedCrashError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Injected proof crash after sealed effect",
                    "step": request.inject_crash_after,
                    "effect_key": str(error),
                },
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Research run not found") from error
        except LeaseUnavailableError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/{tenant_id}/runs/{run_id}/replan")
    def replan_run(
        request: ReplanResearchRunRequest,
        tenant_id: str = Path(min_length=1, max_length=128),
        run_id: str = Path(min_length=1, max_length=128),
    ) -> dict[str, Any]:
        tenant = repository.for_tenant(tenant_id)
        try:
            persisted = tenant.load(run_id)
            selected_services = _services_for_run(
                persisted,
                tenant_id=tenant_id,
                deterministic=services,
                live=live_adapters,
            )
            runner = _build_runner(tenant, selected_services)
            return asdict(runner.replan(run_id, worker_id=request.worker_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Research run not found") from error
        except (InvalidResearchStateError, LeaseUnavailableError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router


def _adapter_fingerprint(source: Any | None, mode: ExecutionMode) -> str:
    fingerprint = getattr(source, "fingerprint", None)
    if isinstance(fingerprint, str) and fingerprint.strip():
        return fingerprint.strip()
    return DEFAULT_ADAPTER_FINGERPRINTS[mode]


def _services_for_run(
    run: ResearchRun,
    *,
    tenant_id: str,
    deterministic: Any,
    live: Any | None,
) -> Any:
    if run.execution_mode == "live":
        if live is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "live_research_unavailable",
                    "message": "Live research adapters are not configured",
                },
            )
        source = live
    else:
        source = deterministic
    current_fingerprint = _adapter_fingerprint(source, run.execution_mode)
    if current_fingerprint != run.adapter_fingerprint:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "research_adapter_mismatch",
                "message": (
                    f"Run requires adapter {run.adapter_fingerprint}; "
                    f"configured adapter is {current_fingerprint}"
                ),
            },
        )
    return (
        live.for_tenant(tenant_id)
        if run.execution_mode == "live"
        else deterministic
    )


def _build_runner(
    tenant,
    adapters: Any,
    *,
    fault_hook=None,
) -> ResearchRunner:
    return ResearchRunner(
        runs=tenant,
        effects=tenant,
        leases=tenant,
        planner=adapters.planner,
        retriever=adapters.retriever,
        synthesizer=adapters.synthesizer,
        verifier=adapters.verifier,
        fault_hook=fault_hook,
    )
