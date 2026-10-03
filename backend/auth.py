"""Auth module — log into the Air Algérie eCrew portal.

Reverse-engineered from HAR capture (see NOTES.md):

- The portal uses header-based sessions, no cookies:
    eCrewHeader: <client-generated UUID>
    RequestVerificationToken: <token from the last loaded page>
- Login = POST /ecrew/Login/<token> with JSON body; password is SHA-512.
- Login URL token, winObj and the verification token all come from the
  login page HTML.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from . import config

logger = logging.getLogger(__name__)

try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None  # type: ignore[assignment,misc]


# Kept as module constants for backwards compatibility; prefer config.base_url().
BASE_URL = config.DEFAULT_BASE_URL
ORIGIN = "https://ecrew.airalgerie.dz"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

# Granular timeouts: (connect, read). Fails fast on dead hosts, allows
# slow server responses.
TIMEOUT = (10, 20)

# Pre-compiled extraction regexes (avoid recompiling per call).
# The portal HTML is minified and attributes can be unquoted or quoted with " or '.
# Attribute order (name vs value) can also vary.
_RE_TOKEN_NAME_FIRST = re.compile(
    r'<input[^>]*?name=["\']?__RequestVerificationToken["\']?[^>]*?value=["\']?([A-Za-z0-9_\-]+)',
    re.IGNORECASE,
)
_RE_TOKEN_VALUE_FIRST = re.compile(
    r'<input[^>]*?value=["\']?([A-Za-z0-9_\-]+)["\']?[^>]*?name=["\']?__RequestVerificationToken["\']?',
    re.IGNORECASE,
)
_RE_TOKEN = _RE_TOKEN_NAME_FIRST
_RE_WINOBJ = re.compile(r'winObj\s*:\s*["\']?([0-9a-fA-F]+)["\']?')
_RE_LOGIN_TOKEN = re.compile(r'["\']/ecrew/Login/([A-Za-z0-9_\-]+)["\']')
_IGNORED_LOGIN_PATHS = {
    "forgotpass",
    "getqrcode",
    "qrcodescan",
    "qrcodeauthentication",
    "changepasswordindex",
}

# Known "extra verification required" response markers (change-password,
# HOTP). The tool refuses to bypass these — fail loudly.
_BLOCKING_MARKERS = (
    "f8988e0c5cb55a2ce4071ab98182c61a7bfe716ce497d74ad03a7cf6fd14350f757e5b0b0e4ef03fc15ed66f791e08f9c92480488fb69703d17aaf12abc79fa5",
    "892ebb3364ed86229a12fd48d2a95ece31bd9019bdc66e6b9f146706991dffdf80808bde291863b0dd30ceb71987989665d7024f8986961d07ac29c94f3422f8",
    "fc2d94151a4988fbde02d9c520111f32625ae4ad84f10cd8de1fa1e6c10450319eb4b2632ed3f356fe72055f3cdee584bd066780a3e57a9f525ef3d3a371d680",
)


class AuthError(RuntimeError):
    """Raised when login fails or credentials are missing."""


class PortalChangedError(AuthError):
    """Raised when the site structure no longer matches what we expect."""


class SessionExpiredError(AuthError):
    """Raised when a previously-valid session needs re-login."""


class ConcurrentSessionError(AuthError):
    """Another eCrew session is already active for this crew id."""

    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# The portal allows a single active session per crew id and only frees the lock
# after roughly a minute. Retry delays must cover that window, otherwise every
# attempt is spent while the lock is still held and the sync can never recover.
CONFLICT_BACKOFF_SECONDS = (15, 30, 60)


_RE_HTML_DOCUMENT = re.compile(
    r"^(?:\ufeff)?\s*(?:<!doctype\s+html|<html[\s>])", re.IGNORECASE
)


def is_error_payload(text: str) -> bool:
    """True when a response body is a machine-readable error, not a page.

    Every eCrew page ships the strings "Another active session" and "Session has
    now been terminated" inside its own inline JS, so matching on the wording
    alone reports a conflict on every successful Dashboard / HomeIndex response.
    A real conflict arrives as a small JSON payload carrying one of the portal's
    error markers.
    """
    stripped = (text or "").strip()
    if not stripped or _RE_HTML_DOCUMENT.match(stripped):
        return False
    lowered = stripped.lower()
    return (
        "error_message" in lowered
        or "responsedata" in lowered
        or stripped.startswith("{")
    )


def is_concurrent_session(status_code: int, text: str) -> bool:
    """True when a response body/status means "another session already active"."""
    if not is_error_payload(text):
        return False
    lower = (text or "").lower()
    if "another active session" in lower:
        return True
    if "session has now been terminated" in lower:
        return True
    if "une autre session" in lower:
        return True
    if "session ecrew est active" in lower:
        return True
    return status_code in (400, 401, 403) and "session" in lower


def retry_after_seconds(response: requests.Response) -> int:
    raw = response.headers.get("Retry-After")
    if not raw:
        return 0
    try:
        seconds = int(str(raw).strip())
    except ValueError:
        return 0
    return seconds if seconds > 0 else 0


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> Credentials:
        # config._ensure_env() runs first so a local .env is honoured — the
        # server used to read the environment before dotenv had been loaded.
        config._ensure_env()
        username = os.environ.get("ECREW_USERNAME")
        password = os.environ.get("ECREW_PASSWORD")
        if not username or not password:
            raise AuthError(
                "Missing ECREW_USERNAME / ECREW_PASSWORD. Copy .env.example "
                "to .env and fill in your values."
            )
        return cls(username=username, password=password)


# --------------------------------------------------------------------------- #
# Page token extraction (regex — much faster than full BeautifulSoup parse
# for the common case of pulling a single hidden input).
# --------------------------------------------------------------------------- #

def _extract_verification_token(html: str) -> str:
    m = _RE_TOKEN_NAME_FIRST.search(html) or _RE_TOKEN_VALUE_FIRST.search(html)
    if m:
        return m.group(1).rstrip("\"'/> ")

    # Fallback to BeautifulSoup if regexes did not match (e.g. unexpected layout)
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("input", attrs={"name": re.compile(r"^__RequestVerificationToken$", re.I)})
        if tag and tag.get("value"):
            return str(tag["value"]).strip()
    except Exception:
        pass

    raise PortalChangedError(
        "Could not find __RequestVerificationToken in page. "
        "The portal layout may have changed — redo the recon."
    )


def _extract_winobj(html: str) -> str:
    m = _RE_WINOBJ.search(html)
    if not m:
        raise PortalChangedError("Could not find winObj in login page.")
    return m.group(1).rstrip("\"'; ")


def _extract_login_token(html: str) -> str:
    for m in _RE_LOGIN_TOKEN.finditer(html):
        candidate = m.group(1)
        if candidate.lower() not in _IGNORED_LOGIN_PATHS:
            return candidate
    raise PortalChangedError("Could not find /ecrew/Login/<token> in login page.")


def _make_session_id() -> str:
    """Site JS UID() format: 4-4-4-4-12 hex characters."""
    pattern = "1000-1000-4000-8000-100000000000"
    res = []
    for ch in pattern:
        if ch in "018":
            c = int(ch)
            r = random.randint(0, 255)
            val = c ^ (r & (15 >> (c // 4)))
            res.append(format(val, "x"))
        else:
            res.append(ch)
    return "".join(res)


# --------------------------------------------------------------------------- #
# Session construction — pooled + retrying adapter for fewer round-trips.
# --------------------------------------------------------------------------- #

def _build_adapter() -> HTTPAdapter:
    if Retry is not None:
        retry = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(("GET", "POST")),
            respect_retry_after_header=True,
        )
        return HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
    return HTTPAdapter(pool_connections=2, pool_maxsize=2)


def get_session(cookie_file: Path | None = None) -> requests.Session:
    """Return a pooled requests.Session, optionally restoring a saved session id."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "fr-FR,fr;q=0.9,en-GB;q=0.8,en;q=0.7,en-US;q=0.6,ar;q=0.5",
        "Sec-Ch-Ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    })
    adapter = _build_adapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    if cookie_file is not None and cookie_file.exists():
        state = _load_state(cookie_file)
        if state.get("session_id"):
            session.headers["eCrewHeader"] = state["session_id"]
            session.ecrew_session_id = state["session_id"]  # type: ignore[attr-defined]
        if state.get("cookies"):
            session.cookies.update(state["cookies"])
    return session


def get_session_id(session: requests.Session) -> str:
    return getattr(session, "ecrew_session_id", "") or session.headers.get("eCrewHeader", "")


# --------------------------------------------------------------------------- #
# Login & Logout
# --------------------------------------------------------------------------- #

def logout(
    session: requests.Session,
    base_url: str | None = None,
    cookie_file: Path | None = None,
    session_id: str | None = None,
) -> None:
    """Explicitly release the server-side AIMS session lock via LogoutP.

    ``session_id`` forces the logout of a specific session, which is what the
    conflict path needs: the lock is held by a *previous* session, so the id of
    the current (never authenticated) session cannot release it.
    """
    sid = session_id or get_session_id(session)
    base = (base_url or config.base_url()).rstrip("/")
    app_base = base[: -len("/ecrew")] + "/eCrew" if base.endswith("/ecrew") else base
    if sid:
        with contextlib.suppress(Exception):
            session.get(f"{app_base}/Dashboard/LogoutP?eCrewHeader={sid}&sl=xslx", timeout=TIMEOUT)
    if cookie_file is not None and cookie_file.exists():
        with contextlib.suppress(OSError):
            cookie_file.unlink()
    if not session_id or session_id == get_session_id(session):
        session.headers.pop("eCrewHeader", None)
        session.headers.pop("ecrewheader", None)
        if hasattr(session, "ecrew_session_id"):
            session.ecrew_session_id = ""


def login(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str | None = None,
    cookie_file: Path | None = None,
    conflict_backoff: Sequence[int] = CONFLICT_BACKOFF_SECONDS,
) -> str:
    """Log into eCrew. Returns the session id (eCrewHeader UUID).

    The returned session id must be sent as the `eCrewHeader` header on all
    subsequent calls. Raises AuthError on failure.

    ``base_url`` defaults to the configured value (resolved lazily, so a local
    .env is honoured) rather than a module constant captured at import.

    A concurrent session (the portal allows only one) is retried with the
    ``conflict_backoff`` delays, releasing the stale lock via LogoutP first.
    ``ConcurrentSessionError`` is raised once the schedule is exhausted.
    """
    for index in range(len(conflict_backoff) + 1):
        try:
            return _login_once(session, username, password, base_url, cookie_file)
        except ConcurrentSessionError as exc:
            if index >= len(conflict_backoff):
                raise
            stale_session_id = get_session_id(session)
            delay = max(conflict_backoff[index], min(exc.retry_after, conflict_backoff[-1]))
            if stale_session_id:
                logout(session, base_url=base_url, session_id=stale_session_id)
            logout(session, base_url=base_url, cookie_file=cookie_file)
            logger.warning(
                "eCrew reports a concurrent session (%s); waiting %ds before retry %d/%d",
                exc,
                delay,
                index + 2,
                len(conflict_backoff) + 1,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def _login_once(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str | None = None,
    cookie_file: Path | None = None,
) -> str:
    base_url = (base_url or config.base_url()).rstrip("/")

    # 1. Load the login page and capture tokens.
    login_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    login_page = session.get(base_url, headers=login_headers, timeout=TIMEOUT)
    if login_page.status_code in (502, 503, 504, 522):
        time.sleep(2)
        login_page = session.get(base_url, headers=login_headers, timeout=TIMEOUT)

    if login_page.status_code != 200:
        raise AuthError(f"Login page returned HTTP {login_page.status_code}")
    html = login_page.text

    verification_token = _extract_verification_token(html)
    winobj = _extract_winobj(html)
    login_token = _extract_login_token(html)
    session_id = _make_session_id()

    # 2. POST credentials. Body keys are fixed (the randomized webix form
    #    field names are only used by the site's own JS to read values
    #    client-side; the wire payload uses these fixed keys).
    payload = {
        "crewid": str(username).strip(),
        "password": hashlib.sha512(password.encode()).hexdigest(),
        "chk": "",
        "cio": "",
        "alias": "",
        "rad": "",
        "winObj": winobj,
        "hotp": "",
    }
    headers = {
        "Content-Type": "application/json",
        "eCrewHeader": session_id,
        "ecrewheader": session_id,
        "RequestVerificationToken": verification_token,
        "Origin": ORIGIN,
        "Referer": base_url,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    url = f"{base_url}/Login/{login_token}"
    resp = session.post(url, data=json.dumps(payload), headers=headers, timeout=TIMEOUT)

    if is_concurrent_session(resp.status_code, resp.text or ""):
        raise ConcurrentSessionError(
            "Another active session is currently open under your account. "
            "Log out of eCrew (browser or phone app) and retry.",
            retry_after=retry_after_seconds(resp),
        )
    if resp.status_code != 200:
        raise AuthError(f"Login POST returned HTTP {resp.status_code}")

    text = resp.text or ""
    if "Invalid Credentials" in text:
        raise AuthError("Invalid credentials (Invalid Credentials).")
    if any(marker in text for marker in _BLOCKING_MARKERS):
        raise AuthError(
            "Portal asks for a password change or additional verification "
            "(HOTP/2FA). Open it in a browser, complete the step there, and "
            "retry. The tool refuses to bypass this."
        )
    # The portal signals success with HTTP 200 + an empty body. Anything else
    # means the contract changed (captcha, redirect, error page) and the caller
    # must not treat the session as valid.
    if text.strip():
        raise PortalChangedError(
            "Login returned an unexpected non-empty body; the portal flow may "
            "have changed. Run `python -m cli.main login-test` to inspect it."
        )

    session.headers["eCrewHeader"] = session_id
    session.ecrew_session_id = session_id  # type: ignore[attr-defined]
    if cookie_file is not None:
        _save_state(cookie_file, session_id=session_id, cookies=session.cookies.get_dict())
    return session_id


# --------------------------------------------------------------------------- #
# State persistence
# --------------------------------------------------------------------------- #

def _save_state(cookie_file: Path, session_id: str, cookies: dict | None = None) -> None:
    """Persist the session id and cookies atomically.

    A crash mid-write would leave a truncated JSON file. ``_load_state`` treats
    that as "no session" and the next run simply logs in again, but writing via
    a temp file + os.replace closes the window entirely.
    """
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cookie_file.with_name(cookie_file.name + ".tmp")
    data: dict[str, Any] = {"session_id": session_id}
    if cookies:
        data["cookies"] = cookies
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, cookie_file)


def _load_state(cookie_file: Path) -> dict:
    try:
        with cookie_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
