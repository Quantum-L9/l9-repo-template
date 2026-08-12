"""Inventory check acceptance for museum identity."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_inventory_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "inventory_check.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_no_required_sdk_in_pyproject() -> None:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "constellation-node-sdk" not in text


def test_no_handlers_default() -> None:
    assert not (REPO / "src" / "l9_example_pkg" / "handlers.py").exists()
    assert not (REPO / "spec.yaml").exists()
