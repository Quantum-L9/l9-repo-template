"""Smoke tests for Core facade + Repo.mk product / gov-* surfaces."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _make(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["make", "-C", str(REPO), *args],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
    )


def test_makefile_matches_template() -> None:
    makefile = (REPO / "Makefile").read_bytes()
    template = (REPO / "tools" / "l9_repo" / "Makefile.template").read_bytes()
    assert makefile == template


def test_help_lists_product_and_facade() -> None:
    proc = _make("help")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "verify" in out
    assert "hygiene-check" in out
    assert "pr-check" in out
    assert "gov-pr-check" in out
    assert "agent-check" in out or "Common targets" in out


def test_repo_mk_gov_wrappers_use_ws() -> None:
    text = (REPO / "Repo.mk").read_text(encoding="utf-8")
    assert 'WS="$(CURDIR)"' in text
    for target in ("gov-pr-check", "gov-pr", "gov-start", "gov-wiring-check"):
        assert f"{target}:" in text
    assert "OPEN_PR ?= 0" in text


def test_gov_wrapper_skips_when_gov_root_missing() -> None:
    missing = REPO / ".gov-root-missing-for-test"
    proc = _make("gov-pr-check", env={"GOV_ROOT": str(missing)})
    assert proc.returncode == 0, proc.stderr
    assert "gov: skip" in proc.stdout or "gov: skip" in proc.stderr


def test_inventory_check_target() -> None:
    proc = _make("inventory-check")
    assert proc.returncode == 0, proc.stderr + proc.stdout
