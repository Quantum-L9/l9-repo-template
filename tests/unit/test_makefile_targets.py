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


def test_public_birth_target_forwards_the_adapter_bundle() -> None:
    """`make birth` is the advertised front door; it must carry the adapter paths."""
    proc = _make(
        "-n",
        "birth",
        "REPO=demo",
        "PKG=demo",
        "DESC=demo",
        "PRODUCT_BIRTH_BINDING_PATH=birth/binding.json",
        "PRODUCT_MANIFEST_PATH=birth/manifest.json",
        "REPO_BIRTH_CONTRACT_PATH=birth/contract.json",
    )
    assert proc.returncode == 0, proc.stderr
    assert '--product-birth-binding-path "birth/binding.json"' in proc.stdout
    assert '--product-manifest-path "birth/manifest.json"' in proc.stdout
    assert "--repo-birth-contract-path" not in proc.stdout, (
        "the retired contract has no Make surface"
    )


def test_direct_birth_target_forwards_the_adapter_bundle() -> None:
    proc = _make(
        "-n",
        "new-repo",
        "REPO=demo",
        "PKG=demo",
        "DESC=demo",
        "PRODUCT_BIRTH_BINDING=/x/binding.json",
        "PRODUCT_MANIFEST=/x/manifest.json",
        "SEMANTIC_COMPILER_SRC=/x/engine",
        "REPO_BIRTH_CONTRACT=/x/contract.json",
    )
    assert proc.returncode == 0, proc.stderr
    assert '--product-birth-binding "/x/binding.json"' in proc.stdout
    assert '--product-manifest "/x/manifest.json"' in proc.stdout
    assert '--semantic-compiler-src "/x/engine"' in proc.stdout
    assert "--repo-birth-contract" not in proc.stdout, "the retired contract has no Make surface"


def test_birth_targets_forward_no_adapter_flags_by_default() -> None:
    for target in ("birth", "new-repo"):
        proc = _make("-n", target, "REPO=demo", "PKG=demo", "DESC=demo")
        assert proc.returncode == 0, proc.stderr
        assert "--product-" not in proc.stdout
        assert "--semantic-compiler-src" not in proc.stdout
