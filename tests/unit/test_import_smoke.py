"""Import smoke for the born IdeaOS package."""

from __future__ import annotations

from ideaos import __version__
from ideaos.app import app
from ideaos.health import health_check
from ideaos.settings import get_example_config


def test_version() -> None:
    assert __version__ == "11.4.1"


def test_app_routes_exist() -> None:
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/v1/health" in paths
    assert "/" in paths


def test_settings_safe() -> None:
    cfg = get_example_config()
    assert cfg.enabled is True
    assert cfg.validate_safe() == []


def test_health_ok() -> None:
    result = health_check()
    assert result.is_ok()
    assert result.capability == "ideaos"
