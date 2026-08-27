"""Negative tests: optional-tool failures must not convert into success."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _fake_tool(tmp_path: Path, name: str, exit_code: int = 1) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    tool = bindir / name
    tool.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    tool.chmod(0o755)
    return bindir


def _make(tmp_path: Path, target: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env}
    return subprocess.run(
        ["make", "-C", str(REPO), target],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
    )


def test_install_dev_fails_when_uv_present_but_failing(tmp_path: Path) -> None:
    """uv present + uv sync failing must fail install-dev (no pip fallback)."""
    bindir = _fake_tool(tmp_path, "uv")
    env = {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    proc = _make(tmp_path, "install-dev", env)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "not falling back to pip" in proc.stderr


def test_pr_check_fails_when_lock_check_fails(tmp_path: Path) -> None:
    """A failing uv lock --check must fail pr-check, not be swallowed."""
    bindir = _fake_tool(tmp_path, "uv")
    # The nested pr-check runs the verify ladder (which re-runs pytest); ignore
    # this file there so the negative test cannot recurse into itself, and mark
    # the run nested so the birth acceptance test does not run a ~40s birth
    # inside it.
    env = {
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "PYTEST_ADDOPTS": "--ignore=tests/unit/test_fail_closed_make.py",
        "L9_SKIP_BIRTH_ACCEPTANCE": "1",
    }
    proc = _make(tmp_path, "pr-check", env)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "lock state is stale" in proc.stderr
