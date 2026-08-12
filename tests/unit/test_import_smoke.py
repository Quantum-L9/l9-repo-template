"""Import smoke for the museum example package."""

from __future__ import annotations

from l9_example_pkg import __version__
from l9_example_pkg.app import app
from l9_example_pkg.errors import ErrorCode, PackageError
from l9_example_pkg.health import health_check
from l9_example_pkg.settings import get_example_config


def test_version() -> None:
    assert __version__ == "0.1.0"


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
    assert result.capability


def test_package_error() -> None:
    err = PackageError("boom", code=ErrorCode.RUNTIME_FAILURE, context={"k": 1})
    assert err.code == "EXAMPLE_RUNTIME_FAILURE"
    assert err.context["k"] == 1
