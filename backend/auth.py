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

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None


BASE_URL = "https://ecrew.airalgerie.dz/ecrew"
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
_RE_TOKEN = re.compile(
    r'name=["\']__RequestVerificationToken["\'][^>]*value=["\']([A-Za-z0-9_\-]+)["\']',
    re.IGNORECASE,
)
_RE_WINOBJ = re.compile(r'winObj\s*:\s*"([0-9a-fA-F]+)"')
_RE_LOGIN_TOKEN = re.compile(r'"/ecrew/Login/([A-Za-z0-9]+)"')

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


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "Credentials":
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
    m = _RE_TOKEN.search(html)
    if not m:
        raise PortalChangedError(
            "Could not find __RequestVerificationToken in page. "
            "The portal layout may have changed — redo the recon."
        )
    return m.group(1)


def _extract_winobj(html: str) -> str:
    m = _RE_WINOBJ.search(html)
    if not m:
        raise PortalChangedError("Could not find winObj in login page.")
    return m.group(1)


def _extract_login_token(html: str) -> str:
    m = _RE_LOGIN_TOKEN.search(html)
    if not m:
        raise PortalChangedError("Could not find /ecrew/Login/<token> in login page.")
    return m.group(1)


def _make_session_id() -> str:
    """Site JS UID() -> random v4-style UUID; server keys the session off
    whatever UUID the client sends. Any standard UUID4 is accepted."""
    return str(uuid.uuid4())


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
    adapter = _build_adapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    if cookie_file is not None and cookie_file.exists():
        state = _load_state(cookie_file)
        if state.get("session_id"):
            session.headers["eCrewHeader"] = state["session_id"]
    return session


def get_session_id(session: requests.Session) -> str:
    return session.headers.get("eCrewHeader", "")


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #

def login(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str = BASE_URL,
    cookie_file: Path | None = None,
) -> str:
    """Log into eCrew. Returns the session id (eCrewHeader UUID).

    The returned session id must be sent as the `eCrewHeader` header on all
    subsequent calls. Raises AuthError on failure.
    """
    # 1. Load the login page and capture tokens.
    login_page = session.get(base_url, timeout=TIMEOUT)
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
        "RequestVerificationToken": verification_token,
        "Origin": ORIGIN,
        "Referer": base_url,
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
    }
    url = f"{base_url}/Login/{login_token}"
    resp = session.post(url, data=json.dumps(payload), headers=headers, timeout=TIMEOUT)

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

    session.headers["eCrewHeader"] = session_id
    if cookie_file is not None:
        _save_state(cookie_file, session_id=session_id)
    return session_id


# --------------------------------------------------------------------------- #
# State persistence
# --------------------------------------------------------------------------- #

def _save_state(cookie_file: Path, session_id: str) -> None:
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    with cookie_file.open("w", encoding="utf-8") as f:
        json.dump({"session_id": session_id}, f, indent=2)


def _load_state(cookie_file: Path) -> dict:
    try:
        with cookie_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
