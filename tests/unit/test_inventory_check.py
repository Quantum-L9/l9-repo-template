"""Inventory check acceptance for museum identity."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
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
    # Assert the denial NAMES the surface and gives the ownership reason, rather
    # than an exact phrase: `dea22b4` reworded this message and left the old
    # wording asserted here, which failed every plain birth in stage 5.
    assert surface in proc.stderr
    assert "CI/control surface present" in proc.stderr
    assert "l9-ci-core" in proc.stderr


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


# ─── Born repositories ──────────────────────────────────────────────────────
# The checker runs in the template AND, renamed, in every repository it births
# (stage 5). What is true of the template's own identity, or of a surface the
# organization owns in a newborn, must not be demanded of a newborn.


def _inventory_module():
    spec = importlib.util.spec_from_file_location(
        "l9_inventory_check_under_test", REPO / "scripts" / "inventory_check.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ownership():
    spec = importlib.util.spec_from_file_location(
        "l9_payload_ownership_for_inventory",
        REPO / "scripts" / "birth-runner" / "payload_ownership.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_ownership(REPO)


def _is_product(patterns: list[str], rel: str) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**") and rel.startswith(pattern[:-2]):
            return True
        if rel == pattern:
            return True
    return False


_MACHINE_STATE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "node_modules",
    "*.egg-info",
)


def _tree_copy(dest: Path) -> Path:
    """The working tree as files. Not `git ls-files`: this suite also runs inside a
    newborn during stage 5, before the newborn's first commit exists."""
    shutil.copytree(REPO, dest, ignore=_MACHINE_STATE, symlinks=True)
    return dest


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "inventory_check.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "L9_INVENTORY_ROOT": str(root)},
    )


def _born(root: Path, mode: str) -> None:
    receipt = {"schema": "l9.birth-receipt/v1", "payload_mode": mode}
    (root / ".l9" / "birth-receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


def _authoritative_newborn(tmp_path: Path) -> Path:
    """The template tree as an authoritative birth leaves it: no example product,
    an organization-owned .coderabbit.yaml, governance's llm.txt."""
    root = _tree_copy(tmp_path / "newborn")
    for rel in _inventory_module().EXAMPLE_PRODUCT:
        (root / rel).unlink(missing_ok=True)
    (root / ".coderabbit.yaml").write_text("language: en-US\n", encoding="utf-8")
    if (root / "llms.txt").is_file():  # a newborn already carries governance's name
        (root / "llms.txt").replace(root / "llm.txt")
    (root / "README.md").write_text("# l9-state\n", encoding="utf-8")
    _born(root, "authoritative")
    return root


def test_example_product_entries_are_product_surfaces() -> None:
    """The exemption covers exactly what the ownership contract says the product owns."""
    product = _ownership()["product"]
    for rel in _inventory_module().EXAMPLE_PRODUCT:
        assert _is_product(product, rel), rel


def test_authoritative_newborn_passes_without_the_example_product(tmp_path: Path) -> None:
    proc = _run(_authoritative_newborn(tmp_path))
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_the_same_tree_without_a_birth_receipt_is_held_to_the_template(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    (root / ".l9" / "birth-receipt.json").unlink()
    proc = _run(root)
    assert proc.returncode == 1
    assert "missing required file: Dockerfile" in proc.stderr
    assert "README.md must mention 'repository birth factory'" in proc.stderr
    assert ".coderabbit.yaml must mention 'AGENTS.md'" in proc.stderr


def test_additive_newborn_still_requires_the_example_product(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    _born(root, "additive")
    proc = _run(root)
    assert proc.returncode == 1
    assert "missing required file: Dockerfile" in proc.stderr
    # The org-owned .coderabbit.yaml is not the template's to word, in any newborn.
    assert ".coderabbit.yaml must mention" not in proc.stderr


def test_unreadable_birth_receipt_is_refused_not_exempted(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    (root / ".l9" / "birth-receipt.json").write_text("{not json", encoding="utf-8")
    proc = _run(root)
    assert proc.returncode == 1
    assert "declares no readable payload_mode" in proc.stderr
    assert "missing required file: Dockerfile" in proc.stderr


def test_agent_wiring_is_still_checked_in_a_newborn(tmp_path: Path) -> None:
    """Born or not, AGENTS.md must point agents at the repository's own contracts."""
    root = _authoritative_newborn(tmp_path)
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    proc = _run(root)
    assert proc.returncode == 1
    assert "AGENTS.md must mention '.l9/architecture.yaml'" in proc.stderr


def test_a_newborn_needs_one_of_the_agent_manifest_names(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    (root / "llm.txt").unlink()
    proc = _run(root)
    assert proc.returncode == 1
    assert "missing required file: llms.txt or llm.txt" in proc.stderr


def test_template_execution_docs_are_the_ownership_contracts_bound_files() -> None:
    bound = _ownership()["execution_runtime"]["bound"]
    assert sorted(_inventory_module().TEMPLATE_EXECUTION_DOCS) == sorted(bound)


def test_authoritative_newborn_owns_its_repo_mk_and_execution_docs(tmp_path: Path) -> None:
    """A product's own V2 Repo.mk needs the four leaves, not the template's `ci`."""
    root = _authoritative_newborn(tmp_path)
    for rel in _inventory_module().TEMPLATE_EXECUTION_DOCS:
        (root / rel).unlink(missing_ok=True)
    (root / "Repo.mk").write_text(
        "repo-setup:\n\ttrue\nrepo-validate:\n\ttrue\nrepo-check:\n\ttrue\nrepo-test:\n\ttrue\n",
        encoding="utf-8",
    )
    proc = _run(root)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_v2_leaves_are_still_required_of_an_authoritative_newborn(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    (root / "Repo.mk").write_text("repo-setup:\n\ttrue\n", encoding="utf-8")
    proc = _run(root)
    assert proc.returncode == 1
    assert "missing Repository Execution V2 leaf repo-test" in proc.stderr


def test_additive_newborn_still_owes_the_template_execution_contract(tmp_path: Path) -> None:
    root = _authoritative_newborn(tmp_path)
    _born(root, "additive")
    (root / "Repo.mk").write_text(
        "repo-setup:\n\ttrue\nrepo-validate:\n\ttrue\nrepo-check:\n\ttrue\nrepo-test:\n\ttrue\n",
        encoding="utf-8",
    )
    proc = _run(root)
    assert proc.returncode == 1
    assert "Repo.mk must define a ci target" in proc.stderr
