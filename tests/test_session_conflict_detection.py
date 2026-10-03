"""Regression test: a successful eCrew HTML page must NOT look like a session conflict.

Every eCrew page (login, Dashboard, HomeIndex) embeds the literal strings
"Another active session" and "Session has now been terminated" in its own inline
JS, plus "Invalid credentials". A conflict detector that greps a response body
for that wording therefore reports a conflict on every *successful* sync: the app
releases the session it just established, retries, and finally surfaces
"Une autre session eCrew est active sur votre compte".

``tests/fixtures/portal_page_with_session_strings.html`` is a trimmed capture of
that page (the live one also carries a UTF-8 BOM, which the fixture reproduces).
``tests/fixtures/sample_roster.html`` stands in for a successful HomeIndex body.
"""

import json
import pathlib

import pytest

from backend import auth, fetch

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PORTAL_PAGE = FIXTURES / "portal_page_with_session_strings.html"
ROSTER_PAGE = FIXTURES / "sample_roster.html"
REFERENCE_HAR = pathlib.Path(r"C:\Users\PC\Downloads\ecrew.airalgerie.dz.har")


def _bom(text: str) -> str:
    return "\ufeff" + text


def test_fixture_really_contains_the_poison_strings():
    page = PORTAL_PAGE.read_text(encoding="utf-8").lower()
    assert "another active session" in page, "fixture no longer reproduces the portal"
    assert "session has now been terminated" in page
    assert "invalid credentials" in page
    assert "error_message" not in page, "portal pages do not carry the JSON error marker"


@pytest.mark.parametrize("prefix", ["", "\ufeff"])
@pytest.mark.parametrize("status", [200, 400])
def test_portal_page_is_never_a_conflict(prefix, status):
    page = prefix + PORTAL_PAGE.read_text(encoding="utf-8")
    assert not auth.is_error_payload(page)
    assert not auth.is_concurrent_session(status, page)


@pytest.mark.parametrize("status", [200, 400])
def test_roster_fragment_is_never_a_conflict(status):
    assert not auth.is_error_payload(ROSTER_PAGE.read_text(encoding="utf-8"))
    assert not auth.is_concurrent_session(status, ROSTER_PAGE.read_text(encoding="utf-8"))


def test_check_for_errors_accepts_a_real_dashboard_page():
    # _check_for_errors only ever sees Dashboard/HomeIndex/GetMenu bodies, never
    # the login page (which legitimately trips the "looks like a login page" check).
    fetch._check_for_errors(ROSTER_PAGE.read_text(encoding="utf-8"))


def test_check_for_errors_still_raises_on_a_real_conflict_payload():
    payload = json.dumps(
        {"error_message": "Another active session is currently open under your account."}
    )
    with pytest.raises(auth.ConcurrentSessionError):
        fetch._check_for_errors(payload)


@pytest.mark.parametrize(
    "body",
    [
        '{"error_message":"Another active session is currently open under your account."}',
        '{"error_message":"Session has now been terminated for you."}',
        '{"error_message":"Une autre session eCrew est active sur votre compte."}',
        '{"responsedata":"Another active session"}',
    ],
)
def test_genuine_conflict_payloads_are_detected(body):
    assert auth.is_error_payload(body)
    assert auth.is_concurrent_session(400, body)


@pytest.mark.parametrize(
    "status,body",
    [
        (200, ""),
        (200, "var events = [];"),
        (404, "not found"),
        (500, "<html><body>Another active session</body></html>"),
        # The wording alone, outside an error payload, is not a conflict.
        (200, "Another active session is currently open under your account."),
        (401, "session expired"),
    ],
)
def test_non_payload_bodies_are_not_conflicts(status, body):
    assert not auth.is_concurrent_session(status, body)


@pytest.mark.skipif(not REFERENCE_HAR.exists(), reason="reference HAR not available")
@pytest.mark.parametrize("status", [200, 400])
def test_captured_homeindex_from_reference_har_is_not_a_conflict(status):
    har = json.loads(REFERENCE_HAR.read_text(encoding="utf-8"))
    bodies = [
        entry["response"]["content"].get("text", "") or ""
        for entry in har["log"]["entries"]
        if "/Dashboard/HomeIndex" in entry["request"]["url"]
    ]
    assert bodies, "HomeIndex missing from the reference HAR"
    for body in bodies:
        assert not auth.is_concurrent_session(status, body)
        fetch._check_for_errors(body)
