"""The version string must agree everywhere.

Four files used to carry a hardcoded version and all four disagreed:
pyproject.toml said 0.2.0, package.json said 1.0.0, twa-manifest.json said
1.0.0, and the outgoing NOAA User-Agent claimed "eCrewSync/2.0". The result was
an API advertising a version nobody could map to an APK they had installed.

``backend.config.APP_VERSION`` is now the single source of truth, and this
module is what stops it from drifting again.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.config import APP_VERSION, app_version

ROOT = Path(__file__).resolve().parent.parent


def _load_toml_version() -> str:
    """Read ``[project] version`` without tomllib (3.11+; this project is 3.10)."""
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', source, re.MULTILINE)
    assert match, "no version = \"...\" found in pyproject.toml"
    return match.group(1)


def _load_json_version(path: Path, key: str) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))[key])


def test_pyproject_matches_config() -> None:
    """pyproject.toml is the canonical file."""
    assert _load_toml_version() == APP_VERSION


def test_package_json_matches_config() -> None:
    assert _load_json_version(ROOT / "package.json", "version") == APP_VERSION


def test_twa_manifest_matches_config() -> None:
    manifest = json.loads((ROOT / "twa" / "twa-manifest.json").read_text(encoding="utf-8"))
    assert manifest["appVersion"] == APP_VERSION


def test_api_advertises_config_version() -> None:
    """The FastAPI app must not hardcode its own version string."""
    from server.api import app

    assert app.version == app_version()


def test_weather_user_agent_tracks_version() -> None:
    """The NOAA User-Agent is derived, not hardcoded.

    Guards the regression where it claimed "eCrewSync/2.0" while the project was
    on a different version entirely.
    """
    source = (ROOT / "backend" / "weather.py").read_text(encoding="utf-8")
    # No hardcoded "eCrewSync/<literal>" version may reappear.
    assert not re.search(r"eCrewSync/\d+\.\d+", source), (
        "weather.py hardcodes a version in its User-Agent; use app_version()"
    )
    assert 'f"eCrewSync/{app_version()}' in source


def test_app_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION), (
        f"{APP_VERSION!r} is not a plain MAJOR.MINOR.PATCH version"
    )
