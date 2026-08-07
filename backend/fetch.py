"""Fetch module — retrieve the roster page after login.

Flow (from NOTES.md): the roster ("My Schedule") is menu item A1, loaded via
    POST /eCrew/Dashboard/GetMenu   {"Menu": "A1"}
which returns an HTML fragment. The verification token must come from the
HomeIndex page (it rotates after login).

URL casing note: the portal uses /ecrew (lowercase) for the login flow and
/eCrew (capital C) for the authenticated app.
"""

from __future__ import annotations

import json
from typing import Optional

import requests

from .auth import (
    ORIGIN,
    TIMEOUT,
    PortalChangedError,
    _extract_verification_token,
    get_session_id,
)

APP_BASE = "https://ecrew.airalgerie.dz/eCrew"
MENU_SCHEDULE = "A1"  # "My Schedule"


class FetchError(RuntimeError):
    pass


class SessionExpiredError(FetchError):
    """The eCrewHeader session is no longer valid — caller should re-login."""


def _looks_like_login_page(text: str) -> bool:
    # Login pages contain both the token hidden input and an <html> tag.
    return "<html" in text[:1000].lower() and "__RequestVerificationToken" in text


def get_verification_token(session) -> str:
    """Return a fresh RequestVerificationToken from the app shell.

    Only HomeIndex is fetched — it already contains the token used by the
    site's own XHR hook. Dashboard GET is skipped (it also navigates to
    HomeIndex in the live UI).
    """
    session_id = get_session_id(session)
    if not session_id:
        raise FetchError("Not logged in: no eCrewHeader session id.")

    home = session.get(
        f"{APP_BASE}/Dashboard/HomeIndex",
        params={"eCrewHeader": session_id},
        timeout=TIMEOUT,
    )
    if home.status_code != 200:
        raise FetchError(f"HomeIndex returned HTTP {home.status_code}")
    if _looks_like_login_page(home.text):
        raise SessionExpiredError("Session expired (HomeIndex redirected to login).")

    try:
        return _extract_verification_token(home.text)
    except PortalChangedError as e:
        raise FetchError(str(e)) from e


def get_roster_page(
    session,
    date_range: Optional[tuple[str, str]] = None,
) -> str:
    """Fetch the "My Schedule" view (menu A1). Returns the HTML fragment.

    NOTE: this is the schedule VIEW (calendar container). The actual duty
    rows may be loaded by a follow-up AJAX call inside that view — that
    endpoint is still unknown. See NOTES.md.
    """
    session_id = get_session_id(session)
    if not session_id:
        raise FetchError("Not logged in: no eCrewHeader session id. Run auth.login() first.")

    token = get_verification_token(session)

    headers = {
        "Content-Type": "application/json",
        "eCrewHeader": session_id,
        "RequestVerificationToken": token,
        "Origin": ORIGIN,
        "Referer": f"{APP_BASE}/Dashboard",
        "X-Requested-With": "XMLHttpRequest",
    }
    url = f"{APP_BASE}/Dashboard/GetMenu"
    resp = session.post(
        url,
        data=json.dumps({"Menu": MENU_SCHEDULE}),
        headers=headers,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise FetchError(f"GetMenu returned HTTP {resp.status_code}")
    if _looks_like_login_page(resp.text):
        raise SessionExpiredError("Session expired (GetMenu returned login page).")

    return resp.text


def is_session_alive(session) -> bool:
    """Quick check: does the current eCrewHeader session still work?

    Used by the scheduler to skip re-login when a cached session id is
    still valid.
    """
    if not get_session_id(session):
        return False
    try:
        probe = session.get(
            f"{APP_BASE}/Dashboard/HomeIndex",
            params={"eCrewHeader": get_session_id(session)},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return False
    return probe.status_code == 200 and not _looks_like_login_page(probe.text)
