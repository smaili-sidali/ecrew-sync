"""Unit tests for backend.auth extraction and session handling."""

import pytest
from backend import auth


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
