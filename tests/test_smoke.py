"""Smoke tests for the template example package."""

from l9_example_pkg import __version__, hello


def test_hello() -> None:
    assert hello() == "l9-example-pkg"


def test_version() -> None:
    assert __version__ == "0.1.0"
