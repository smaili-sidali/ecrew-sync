"""API auth (Phase 3).

The service is designed to be self-hosted, but the API is unauthenticated by
default — fine on a LAN, unsafe on the internet, because it serves your roster
and lets anyone trigger a real portal login (repeated failed logins can get an
account rate-limited or locked).

Set ``ECREW_API_TOKEN`` to require a bearer token. The token may be presented
as ``Authorization: Bearer <token>`` or as ``?token=<token>`` — the query form
exists because calendar apps that subscribe to a ``webcal://`` feed cannot send
custom headers.

The comparison is constant-time to avoid leaking the token byte by byte.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Request, status

from backend import config

logger = logging.getLogger(__name__)

# Routes reachable without a token even when auth is on. Health is used by the
# container healthcheck and by uptime monitors; the contract-check endpoint is
# read-only diagnostics with no roster data in it.
PUBLIC_PATHS = frozenset({"/api/health"})


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    if header and " " not in header:
        # Bare token in Authorization.
        return header.strip()
    # Calendar subscriptions cannot set headers.
    return request.query_params.get("token")


def require_token(request: Request) -> None:
    """FastAPI dependency: raise 401 unless a valid token is present."""
    if not config.require_auth():
        return
    if request.url.path in PUBLIC_PATHS:
        return

    expected = config.api_token() or ""
    provided = _token_from_request(request)

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API token. Send 'Authorization: Bearer <token>' "
            "or append ?token=<token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(provided, expected):
        logger.warning(
            "Rejected request with an invalid API token (path=%s)", request.url.path
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token.",
        )
