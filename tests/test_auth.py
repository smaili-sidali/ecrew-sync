"""Unit tests for backend.auth extraction and session handling."""

import types

import pytest

from backend import auth


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


LOGIN_PAGE = (
    '<input name="__RequestVerificationToken" type="hidden" value="tok-abc">'
    '<script>winObj:"a4824fbcd45766631bc59850f1d70bc0";'
    'EcallUrlAsync("/ecrew/Login/TOK123", p, "post");</script>'
)
CONFLICT_BODY = '{"error_message":"Another active session is currently open under your account."}'


def _fake_session(post_statuses):
    state = {"posts": 0, "logouts": []}

    def get(url, **kwargs):
        if "LogoutP" in url:
            state["logouts"].append(url)
            return FakeResponse(200, "")
        return FakeResponse(200, LOGIN_PAGE)

    def post(url, **kwargs):
        status = post_statuses[min(state["posts"], len(post_statuses) - 1)]
        state["posts"] += 1
        if status == 200:
            return FakeResponse(status, "")
        if status == 400:
            return FakeResponse(status, CONFLICT_BODY)
        return FakeResponse(status, "<html>upstream failure</html>")

    session = types.SimpleNamespace(get=get, post=post, headers={}, cookies=types.SimpleNamespace(get_dict=dict))
    return session, state


@pytest.mark.parametrize(
    "status,text",
    [
        (200, CONFLICT_BODY),
        (200, "Session has now been terminated for you."),
        (200, "Une autre session eCrew est active sur votre compte."),
        (401, "session expired"),
        (403, "Another active session"),
    ],
)
def test_is_concurrent_session_detects_conflict(status, text):
    assert auth.is_concurrent_session(status, text)


@pytest.mark.parametrize(
    "status,text",
    [(200, "var events = [];"), (500, ""), (200, ""), (404, "not found")],
)
def test_is_concurrent_session_ignores_normal_responses(status, text):
    assert not auth.is_concurrent_session(status, text)


def test_retry_after_seconds():
    assert auth.retry_after_seconds(FakeResponse(headers={"Retry-After": "42"})) == 42
    assert auth.retry_after_seconds(FakeResponse(headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) == 0
    assert auth.retry_after_seconds(FakeResponse(headers={})) == 0


def test_login_honours_retry_after_hint(monkeypatch):
    slept: list[int] = []
    monkeypatch.setattr(auth.time, "sleep", slept.append)

    def get(url, **kwargs):
        return FakeResponse(200, LOGIN_PAGE)

    def post(url, **kwargs):
        return FakeResponse(400, CONFLICT_BODY, {"Retry-After": "45"})

    session = types.SimpleNamespace(get=get, post=post, headers={}, cookies=types.SimpleNamespace(get_dict=dict))

    with pytest.raises(auth.ConcurrentSessionError):
        auth.login(session, "35739", "pw", base_url="https://h/ecrew", conflict_backoff=(1, 2, 3))

    assert slept == [3, 3, 3]


def test_conflict_backoff_covers_the_server_lock_window():
    assert auth.CONFLICT_BACKOFF_SECONDS[-1] >= 60


def test_login_retries_concurrent_session_until_success(monkeypatch):
    slept: list[int] = []
    monkeypatch.setattr(auth.time, "sleep", slept.append)
    session, state = _fake_session([400, 400, 200])

    sid = auth.login(session, "35739", "pw", base_url="https://h/ecrew", conflict_backoff=(15, 30))

    assert state["posts"] == 3
    assert slept == [15, 30]
    assert sid.count("-") == 4


def test_login_raises_once_backoff_is_exhausted(monkeypatch):
    slept: list[int] = []
    monkeypatch.setattr(auth.time, "sleep", slept.append)
    session, state = _fake_session([400])

    with pytest.raises(auth.ConcurrentSessionError):
        auth.login(session, "35739", "pw", base_url="https://h/ecrew", conflict_backoff=(15, 30, 60))

    assert state["posts"] == 4
    assert slept == [15, 30, 60]


def test_login_releases_the_stale_session_holding_the_lock(monkeypatch):
    monkeypatch.setattr(auth.time, "sleep", lambda _s: None)
    session, state = _fake_session([400, 200])
    session.headers["eCrewHeader"] = "stale-session-id"

    auth.login(session, "35739", "pw", base_url="https://h/ecrew", conflict_backoff=(1,))

    assert any("eCrewHeader=stale-session-id" in url for url in state["logouts"])


def test_login_does_not_retry_non_conflict_http_errors(monkeypatch):
    slept: list[int] = []
    monkeypatch.setattr(auth.time, "sleep", slept.append)
    session, state = _fake_session([500])

    with pytest.raises(auth.AuthError) as exc:
        auth.login(session, "35739", "pw", base_url="https://h/ecrew")

    assert "HTTP 500" in str(exc.value)
    assert slept == []
    assert state["posts"] == 1


def test_extract_verification_token_quoted():
    html = '<input name="__RequestVerificationToken" type="hidden" value="token123_abc-def">'
    assert auth._extract_verification_token(html) == "token123_abc-def"


def test_extract_verification_token_unquoted():
    html = '<input name=__RequestVerificationToken type=hidden value=token_unquoted-999><link rel=icon>'
    assert auth._extract_verification_token(html) == "token_unquoted-999"


def test_extract_verification_token_reversed_order():
    html = '<input value="token_val_first" type="hidden" name="__RequestVerificationToken">'
    assert auth._extract_verification_token(html) == "token_val_first"


def test_extract_verification_token_missing():
    with pytest.raises(auth.PortalChangedError):
        auth._extract_verification_token("<html><body>No token here</body></html>")


def test_extract_winobj():
    html = '... winObj:"a4824fbcd45766631bc59850f1d70bc0" ...'
    assert auth._extract_winobj(html) == "a4824fbcd45766631bc59850f1d70bc0"


def test_extract_winobj_missing():
    with pytest.raises(auth.PortalChangedError):
        auth._extract_winobj("<html><body>No winObj</body></html>")


def test_extract_login_token_with_hyphens_and_static_routes():
    html = """
    function PostLogin() {
        EcallUrlAsync("/ecrew/Login/8Oi0PezAnsBbUlRbNcxDy0ZHG66uVSe4yiMpt9ZEtwfnnm-7sAL7ZzKSCgZQg8jc", params, "post");
    }
    EcallUrlAsync("/ecrew/Login/ForgotPass", params, "post");
    EcallUrlAsync("/ecrew/Login/GetQRCode", params, "post");
    """
    assert (
        auth._extract_login_token(html)
        == "8Oi0PezAnsBbUlRbNcxDy0ZHG66uVSe4yiMpt9ZEtwfnnm-7sAL7ZzKSCgZQg8jc"
    )


def test_extract_login_token_missing():
    html = """
    EcallUrlAsync("/ecrew/Login/ForgotPass", params, "post");
    EcallUrlAsync("/ecrew/Login/GetQRCode", params, "post");
    """
    with pytest.raises(auth.PortalChangedError):
        auth._extract_login_token(html)


def test_make_session_id():
    sid = auth._make_session_id()
    assert isinstance(sid, str)
    assert len(sid) in (32, 36)
    assert sid.count("-") == 4
