"""Fetch module — retrieve the roster page after login.

Flow (verified from HAR capture):
1. Load Dashboard shell: GET /eCrew/Dashboard
2. Load HomeIndex: GET /eCrew/Dashboard/HomeIndex?eCrewHeader=<session_id>
   HomeIndex contains the embedded DayPilot calendar data:
       var events = [ ... ];
3. If HomeIndex ever lacks events, fall back to POST /eCrew/Dashboard/GetMenu {"Menu": "A1"}.

URL casing note: the portal uses /ecrew (lowercase) for the login flow and
/eCrew (capital C) for the authenticated app.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from . import auth as _auth
from . import config
from .auth import (
    ORIGIN,
    TIMEOUT,
    PortalChangedError,
    _extract_verification_token,
    get_session_id,
)

logger = logging.getLogger(__name__)

# Authenticated app root. The portal uses /ecrew (lowercase) for login and
# /eCrew (capital C) for the app; both are derived from ECREW_BASE_URL's host
# so pointing the tool at a staging portal does not require code changes.
APP_BASE = "https://ecrew.airalgerie.dz/eCrew"
MENU_SCHEDULE = "A1"  # "My Schedule"


def app_base() -> str:
    """Authenticated app root, derived from the configured base URL.

    ``https://host/ecrew`` -> ``https://host/eCrew``
    """
    base = config.base_url()
    if base.endswith("/ecrew"):
        return base[: -len("/ecrew")] + "/eCrew"
    return base


class FetchError(RuntimeError):
    pass


class SessionExpiredError(FetchError):
    """The eCrewHeader session is no longer valid — caller should re-login."""


class ConcurrentSessionError(FetchError):
    """Another active session is open under the crew account."""


def _looks_like_login_page(text: str) -> bool:
    # A true login page contains the Webix loginForm or swipecard component.
    return "loginForm" in text or "swipecardid" in text


def _check_for_errors(text: str) -> None:
    if "error_message" in text and "Another active session" in text:
        raise ConcurrentSessionError(
            "Another active session is currently open under your account. "
            "Please log out of eCrew in your browser or phone app and wait a moment before trying again."
        )
    if _looks_like_login_page(text):
        raise SessionExpiredError("Session expired (redirected to login page).")


def get_verification_token(session) -> str:
    """Return a fresh RequestVerificationToken from the app shell (Dashboard or HomeIndex)."""
    session_id = get_session_id(session)
    if not session_id:
        raise FetchError("Not logged in: no eCrewHeader session id.")

    # Try Dashboard first (contains top-level token)
    dash = session.get(
        f"{app_base()}/Dashboard",
        headers={"Referer": config.base_url()},
        timeout=TIMEOUT,
    )
    if dash.status_code == 200 and not _looks_like_login_page(dash.text):
        try:
            return _extract_verification_token(dash.text)
        except PortalChangedError:
            pass

    # Fallback to HomeIndex
    home = session.get(
        f"{app_base()}/Dashboard/HomeIndex",
        params={"eCrewHeader": session_id},
        headers={"Referer": f"{app_base()}/Dashboard"},
        timeout=TIMEOUT,
    )
    if home.status_code != 200:
        raise FetchError(f"HomeIndex returned HTTP {home.status_code}")
    _check_for_errors(home.text)

    try:
        return _extract_verification_token(home.text)
    except PortalChangedError as e:
        raise FetchError(str(e)) from e


def get_roster_page(
    session,
    date_range: tuple[str, str] | None = None,
) -> str:
    """Fetch the roster view. Returns the HTML page embedding duty data.

    The live portal embeds the full schedule array directly inside HomeIndex
    (`var events = [...]`). We visit Dashboard first, then retrieve HomeIndex.
    If HomeIndex does not contain duty events, we fall back to GetMenu A1.
    """
    session_id = get_session_id(session)
    if not session_id:
        raise FetchError("Not logged in: no eCrewHeader session id. Run auth.login() first.")

    # 1. Load Dashboard shell
    dash_headers = {
        "Referer": config.base_url(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    dash = session.get(
        f"{app_base()}/Dashboard",
        headers=dash_headers,
        timeout=TIMEOUT,
    )
    if dash.status_code == 200:
        _check_for_errors(dash.text)

    # 2. Fetch HomeIndex view (which embeds DayPilot `events = [...]`)
    home_headers = {
        "Referer": f"{app_base()}/Dashboard",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }
    home = session.get(
        f"{app_base()}/Dashboard/HomeIndex?eCrewHeader={session_id}",
        headers=home_headers,
        timeout=TIMEOUT,
    )
    _check_for_errors(home.text)
    if home.status_code == 200 and "events" in home.text:
        return home.text

    # 3. Fallback: try POST /Dashboard/GetMenu {"Menu": "A1"}
    token = get_verification_token(session)
    headers = {
        "Content-Type": "application/json",
        "eCrewHeader": session_id,
        "RequestVerificationToken": token,
        "Origin": ORIGIN,
        "Referer": f"{app_base()}/Dashboard",
        "X-Requested-With": "XMLHttpRequest",
    }
    url = f"{app_base()}/Dashboard/GetMenu"
    resp = session.post(
        url,
        data=json.dumps({"Menu": MENU_SCHEDULE}),
        headers=headers,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise FetchError(f"GetMenu returned HTTP {resp.status_code}")
    _check_for_errors(resp.text)

    return resp.text


def fetch_with_relogin(
    session,
    username: str,
    password: str,
    base_url: str | None = None,
    cookie_file: Path | None = None,
    attempts: int = 2,
) -> str:
    """Fetch the roster view, transparently re-logging in once if the session died."""
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return get_roster_page(session)
        except (SessionExpiredError, ConcurrentSessionError) as e:
            last_exc = e
            if attempt >= attempts:
                break
            logger.warning("eCrew session invalid (%s; attempt %d); re-logging in", type(e).__name__, attempt)
            session.cookies.clear()
            _auth.login(
                session,
                username,
                password,
                base_url=base_url or config.base_url(),
                cookie_file=cookie_file,
            )
    assert last_exc is not None
    raise last_exc


def is_session_alive(session) -> bool:
    """Quick check: does the current eCrewHeader session still work?"""
    session_id = get_session_id(session)
    if not session_id:
        return False
    home_headers = {
        "Referer": f"{app_base()}/Dashboard",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        probe = session.get(
            f"{app_base()}/Dashboard/HomeIndex?eCrewHeader={session_id}",
            headers=home_headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return False
    if probe.status_code != 200:
        return False
    if "error_message" in probe.text or _looks_like_login_page(probe.text):
        return False
    return "events" in probe.text

