"""Shared pytest fixtures for the museum template."""

from __future__ import annotations

import pytest

from l9_example_pkg.settings import get_example_config


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_example_config.cache_clear()
