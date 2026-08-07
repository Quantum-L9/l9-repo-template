"""Hygiene audit acceptance."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_hygiene_audit_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "repo_hygiene_audit.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "hygiene OK" in proc.stdout
