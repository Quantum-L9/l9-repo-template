"""Smoke tests for the template worker package."""

from __future__ import annotations

import pytest

from l9_example_pkg import __version__
from l9_example_pkg.handlers import handle_example


def test_version() -> None:
    assert __version__ == "0.1.0"


@pytest.mark.asyncio
async def test_example_handler() -> None:
    result = await handle_example("tenant-a", {"entity_id": "42"})
    assert result["status"] == "completed"
    assert result["entity_id"] == "42"
