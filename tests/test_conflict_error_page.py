"""The portal's "Another active session" error page must be detected as a conflict.

The portal serves that error as an HTML document whose message is injected by the
page's own JavaScript into `<div class='error_message'>` inside
`<div class='error_content'>`. Every page that *succeeds* already contains the
sentence "Another active session is currently open" in its inline JS, so matching
on the wording alone reports a conflict on every successful HomeIndex - that was
the original bug. The wrapper class names appear in no successful page, so they
are the reliable discriminator.
"""

import pathlib

import pytest

from backend import auth, fetch

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
PORTAL_PAGE = FIXTURES / "portal_page_with_session_strings.html"
ROSTER_PAGE = FIXTURES / "sample_roster.html"


def _error_page() -> str:
    """Rebuild the portal's error page the way it serves it (captured live)."""
    return """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />
<style>.error_content{position:absolute;top:5%;left:50%;}
.error_icon{font-size:75px;color:#2196f3;} .error_message{font-size:14px;}</style>
</head><body><script>
var page = "\\" + "<div class='error_content'>"
    + "<i class='fad fa-sad-tear error_icon'></i>"
    + "<div class='error_message'>Another active session is currently open under your account. This session has now been terminated.</br>03/10/2026 06:17:00</div></div>";
</script></body></html>"""


def test_error_page_is_detected_as_a_conflict():
    page = _error_page()
    assert "error_content" in page
    assert auth.is_concurrent_session(400, page)
    assert auth.is_concurrent_session(200, page)


def test_successful_pages_are_still_not_conflicts():
    # Both carry the sentence in their own JS but none of the error classes.
    for path in (PORTAL_PAGE, ROSTER_PAGE):
        text = path.read_text(encoding="utf-8")
        assert "error_content" not in text
        assert not auth.is_concurrent_session(400, text)
        assert not auth.is_concurrent_session(200, text)


def test_check_for_errors_flags_the_conflict_page():
    with pytest.raises(auth.ConcurrentSessionError):
        fetch._check_for_errors(_error_page())


def test_html_without_the_error_classes_stays_a_page():
    html = "<!DOCTYPE html><html><body>Another active session is currently open</body></html>"
    assert not auth.is_concurrent_session(400, html)
