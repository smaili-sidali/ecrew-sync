"""Regression test: a successful eCrew HTML page must NOT look like a session conflict.

Ground truth: every eCrew page (login, Dashboard, HomeIndex) embeds the literal
strings "Another active session" and "Session has now been terminated" in its own
inline JS. A bare substring match therefore reported a conflict on every
successful sync, released the freshly established session and finally surfaced
"Une autre session eCrew est active sur votre compte".

The captured live login page is used as the fixture.
"""

import json
import pathlib
import urllib.request

from backend import auth, fetch

LIVE_PAGE = pathlib.Path(
    r"C:\Users\PC\AppData\Local\Temp\opencode\loginpage.html"
)
HAR = pathlib.Path(r"C:\Users\PC\Downloads\ecrew.airalgerie.dz.har")


def _live_login_page() -> str:
    if LIVE_PAGE.exists():
        return LIVE_PAGE.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        "https://ecrew.airalgerie.dz/eCrew",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _captured_homeindex() -> str:
    har = json.loads(HAR.read_text(encoding="utf-8"))
    for entry in har["log"]["entries"]:
        if "/Dashboard/HomeIndex" in entry["request"]["url"]:
            return entry["response"]["content"].get("text", "") or ""
    raise AssertionError("HomeIndex not present in the reference HAR")


def test_fixture_really_contains_the_poison_strings():
    page = _live_login_page().lower()
    assert "another active session" in page, "portal no longer ships the string; re-verify"
    assert "session has now been terminated" in page
    assert "error_message" not in page, "if this changed, is_error_payload's guard needs review"


def test_live_portal_page_is_not_a_conflict():
    page = _live_login_page()
    assert not auth.is_error_payload(page)
    assert not auth.is_concurrent_session(200, page)
    assert not auth.is_concurrent_session(400, page)


def test_captured_homeindex_is_not_a_conflict():
    home = _captured_homeindex()
    assert home.strip(), "HAR HomeIndex body missing"
    assert not auth.is_error_payload(home)
    assert not auth.is_concurrent_session(200, home)
    assert not auth.is_concurrent_session(400, home)


def test_check_for_errors_does_not_raise_on_a_real_dashboard_page():
    # _check_for_errors only ever sees Dashboard/HomeIndex/GetMenu bodies, never
    # the login page (which legitimately trips the "looks like a login page" check).
    fetch._check_for_errors(_captured_homeindex())


def test_check_for_errors_still_raises_on_a_real_conflict_payload():
    payload = json.dumps(
        {"error_message": "Another active session is currently open under your account."}
    )
    try:
        fetch._check_for_errors(payload)
    except auth.ConcurrentSessionError:
        return
    raise AssertionError("a genuine conflict payload must still raise")


def test_bare_json_conflict_is_detected():
    assert auth.is_concurrent_session(400, '{"error_message":"Another active session is currently open."}')


def test_french_conflict_wording_is_detected():
    assert auth.is_concurrent_session(400, '{"error_message":"Une autre session eCrew est active."}')


def test_login_does_not_report_conflict_on_html_error_page():
    html = "<!DOCTYPE html><html><body>Another active session</body></html>"
    assert not auth.is_concurrent_session(400, html)


def test_empty_and_plain_bodies_are_not_conflicts():
    assert not auth.is_concurrent_session(400, "")
    assert not auth.is_concurrent_session(400, "var events = [];")
    assert not auth.is_error_payload("var events = [];")
