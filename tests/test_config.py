"""Tests for backend.config and the config-derived fetch helpers.

Regression coverage for two real bugs:

* ``ECREW_*`` values were read at *module import*, before ``load_dotenv()`` ran.
  A local ``.env`` was therefore ignored by both the API and the scheduler, and
  the bug was invisible in Docker (where compose exports real env vars).
* The CLI defaulted the session file to ``cookies.json`` while the scheduler
  defaulted to ``session_state.json`` — two files, two sessions, and only one of
  them covered by ``.gitignore``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend import config, fetch

_ALL_KEYS = (
    "ECREW_BASE_URL",
    "ECREW_DB_FILE",
    "ECREW_COOKIE_FILE",
    "ECREW_TZ",
    "ECREW_SYNC_INTERVAL_H",
    "ECREW_SYNC_MIN_GAP_S",
    "ECREW_ENABLE_DOCS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults():
    assert config.base_url() == config.DEFAULT_BASE_URL
    assert config.db_file().name == config.DEFAULT_DB_FILE
    assert config.session_file().name == config.DEFAULT_SESSION_FILE
    assert config.sync_interval_h() == 6
    assert config.sync_min_gap_s() == 300
    assert config.docs_enabled() is False


def test_session_file_default_is_shared_by_cli_and_scheduler():
    """One default, used by both entry points."""
    assert config.session_file().name == "session_state.json"
    from cli import main as cli_main

    assert cli_main.config.session_file().name == config.session_file().name


def test_reads_env(monkeypatch):
    monkeypatch.setenv("ECREW_DB_FILE", "/tmp/xyz/roster.json")
    monkeypatch.setenv("ECREW_SYNC_INTERVAL_H", "12")
    monkeypatch.setenv("ECREW_ENABLE_DOCS", "1")
    assert str(config.db_file()).endswith("roster.json")
    assert config.sync_interval_h() == 12
    assert config.docs_enabled() is True


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("ECREW_BASE_URL", "https://example.test/ecrew/")
    assert config.base_url() == "https://example.test/ecrew"


def test_blank_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ECREW_BASE_URL", "   ")
    assert config.base_url() == config.DEFAULT_BASE_URL


def test_bad_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ECREW_SYNC_INTERVAL_H", "not-a-number")
    assert config.sync_interval_h() == 6


def test_int_is_clamped_to_sane_minimum(monkeypatch):
    monkeypatch.setenv("ECREW_SYNC_INTERVAL_H", "0")
    assert config.sync_interval_h() == 1
    monkeypatch.setenv("ECREW_SYNC_MIN_GAP_S", "-5")
    assert config.sync_min_gap_s() == 0


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("true", True), ("YES", True), ("on", True),
     ("0", False), ("false", False), ("no", False), ("off", False)],
)
def test_bool_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("ECREW_ENABLE_DOCS", raw)
    assert config.docs_enabled() is expected


def test_local_tz_is_aware_and_algiers_offset():
    tz = config.local_tz()
    from datetime import datetime

    # Algiers is UTC+1 year-round.
    assert datetime(2026, 8, 15, 12, 0, tzinfo=tz).utcoffset().total_seconds() == 3600


def test_local_tz_honours_override(monkeypatch):
    monkeypatch.setenv("ECREW_TZ", "UTC")
    from datetime import datetime

    tz = config.local_tz()
    assert datetime(2026, 8, 15, 12, 0, tzinfo=tz).utcoffset().total_seconds() == 0


# --- fetch.app_base() ----------------------------------------------------- #


def test_app_base_derives_from_configured_base_url(monkeypatch):
    monkeypatch.setenv("ECREW_BASE_URL", "https://staging.test/ecrew")
    assert fetch.app_base() == "https://staging.test/eCrew"


def test_app_base_without_ecrew_suffix(monkeypatch):
    monkeypatch.setenv("ECREW_BASE_URL", "https://staging.test")
    assert fetch.app_base() == "https://staging.test"
