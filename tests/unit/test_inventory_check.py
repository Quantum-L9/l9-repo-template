"""Inventory check acceptance for museum identity."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

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


LEGACY_CI_SURFACES = [
    ".l9/ci-pin",
    "scripts/sync_ci_from_pack.py",
    "requirements-consumer-ci.txt",
    ".github/workflows/l9-analysis.yml",
    ".github/workflows/l9-lint-test.yml",
    ".github/workflows/on-org-update.yml",
    ".github/workflows/governance.yml",
    ".github/governance",
]


@pytest.mark.parametrize("surface", LEGACY_CI_SURFACES)
def test_legacy_ci_surface_rejected(tmp_path: Path, surface: str) -> None:
    """Reintroducing any legacy distributed-CI surface fails inventory."""
    path = tmp_path / surface
    if surface.endswith("/"):
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")
    env = {**os.environ, "L9_INVENTORY_ROOT": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "inventory_check.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert "legacy CI distribution surface" in proc.stderr


def test_repo_mk_ci_facade_required(tmp_path: Path) -> None:
    """A repository-execution contract without a Repo.mk ci target fails."""
    (tmp_path / "Repo.mk").write_text("verify: true\n", encoding="utf-8")
    env = {**os.environ, "L9_INVENTORY_ROOT": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "inventory_check.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 1, proc.stderr + proc.stdout
    assert "Repo.mk must define a ci target" in proc.stderr
