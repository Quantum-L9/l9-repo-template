"""Tests for scripts/render_cursor_rules.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RENDER = REPO / "scripts" / "render_cursor_rules.py"


def test_check_rules_current() -> None:
    proc = subprocess.run(
        [sys.executable, str(RENDER), "--check"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK:" in proc.stdout


def test_render_is_idempotent(tmp_path: Path) -> None:
    # Smoke: dry re-render to a temp output dir from real templates/config
    out = tmp_path / "rules"
    proc = subprocess.run(
        [
            sys.executable,
            str(RENDER),
            "--output-dir",
            str(out),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--force",
        ],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    mdc = list(out.glob("*.mdc"))
    assert mdc
    assert any("L9_RENDERED" in p.read_text(encoding="utf-8") for p in mdc)
