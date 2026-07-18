"""Shared authorization dependency for operator-controlled mutations."""

from ipaddress import ip_address
from secrets import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException, Request

from app.config import settings


def require_operator(
    request: Request,
    operator_token: Annotated[
        str | None,
        Header(alias="X-Operator-Token"),
    ] = None,
) -> None:
    """Require a configured token, or constrain tokenless mutations to loopback."""
    configured_token = settings.operator_api_token
    if configured_token:
        if operator_token is None or not compare_digest(
            operator_token,
            configured_token,
        ):
            raise HTTPException(
                status_code=401,
                detail="A valid X-Operator-Token is required for this mutation",
            )
        return

    client_host = request.client.host if request.client else ""
    try:
        is_loopback = ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = client_host.casefold() == "localhost"
    if not is_loopback:
        raise HTTPException(
            status_code=403,
            detail=(
                "Operator mutations are loopback-only unless "
                "OPERATOR_API_TOKEN is configured"
            ),
        )
