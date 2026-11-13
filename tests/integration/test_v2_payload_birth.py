"""Local birth of a V2 + Biome repository-shaped payload (stages 1-5, no remote).

The interface this proves: a product payload that carries its own repository
execution contract — `.l9/repo-workflow.json` (`l9.repo-execution/v2`), a
Core-generated make-v1 `Makefile`, a repository-owned `Repo.mk` — and the
Core-stamped `biome.json` / `.biomeignore` / `.editorconfig` is born under the
`org_seeded_self_governed` class with every one of those files byte-identical to
the payload. The template's own V1 execution runtime is not carried into a
newborn that replaced the contract it serves.

Same preconditions as `test_new_repo_local_birth.py`: `uv`, a genuine
Quantum-L9/.github checkout, and a pristine template checkout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
FIXTURES = REPO / "tests" / "fixtures" / "birth_v2_payload"
CLASS = "org_seeded_self_governed"
PKG = "l9_v2_fixture"
NAME = "l9-v2-fixture"

# fixture name -> path in the payload
CORE_STAMPED = {
    "Makefile.fixture": "Makefile",
    "repo-workflow.json.fixture": ".l9/repo-workflow.json",
    "biome.json.fixture": "biome.json",
    "biomeignore.fixture": ".biomeignore",
    "editorconfig.fixture": ".editorconfig",
}
EXECUTION_SURFACES = (*CORE_STAMPED.values(), "Repo.mk")

# The template's V1 runtime: must not survive into a newborn whose payload
# replaced `.l9/repo-workflow.json`.
V1_RUNTIME = (
    "tools/l9_repo/__main__.py",
    "tools/l9_repo/Makefile.template",
    "tools/check_workflow_integrity.py",
    ".l9/repo-workflow.schema.json",
    ".l9/runtime-provenance.yaml",
    "MANIFEST.sha256",
    "requirements-repo-runtime.txt",
    "docs/repository-execution-runtime.md",
    "scripts/regenerate_runtime_manifest.py",
)


def _org_checkout() -> Path | None:
    candidates = []
    env_src = os.environ.get("L9_ORG_GITHUB_SRC")
    if env_src:
        candidates.append(Path(env_src))
    candidates.append(REPO.parent / ".github")
    for root in candidates:
        if (root / "ops" / "build-seed-payload.js").is_file() and (
            root / "policies" / "repo-classes.yml"
        ).is_file():
            return root.resolve()
    return None


ORG_SRC = _org_checkout()

pytestmark = [
    pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed on runner PATH"),
    pytest.mark.skipif(shutil.which("node") is None, reason="node not installed on runner PATH"),
    pytest.mark.skipif(
        not (REPO / "src" / "l9_example_pkg").is_dir(),
        reason="not a pristine l9-repo-template checkout — birth acceptance does not apply",
    ),
    pytest.mark.skipif(
        os.environ.get("L9_SKIP_BIRTH_ACCEPTANCE") == "1",
        reason="L9_SKIP_BIRTH_ACCEPTANCE=1 — nested gate, would recurse",
    ),
    pytest.mark.skipif(
        ORG_SRC is None,
        reason=(
            "no Quantum-L9/.github checkout found (set L9_ORG_GITHUB_SRC or place one "
            "beside this repo) — birth materializes org files with the org's own builder"
        ),
    ),
]

REPO_MK = """\
# Repository-owned make-v1 leaves (fixture).
PYTHON ?= python3
.PHONY: repo-setup repo-validate repo-check repo-test
repo-setup: ## Install dependencies
\t@uv sync --extra dev
repo-validate: ## Validate contracts
\t@$(PYTHON) scripts/inventory_check.py
repo-check: ## Lint and type-check
\t@uv run ruff check . && uv run mypy src
repo-test: ## Run tests
\t@uv run pytest -q
"""

# A product owns its lint policy. It has to admit the chassis Python the factory
# carries into every newborn (`scripts/**`), exactly as the template's own does.
PYPROJECT = f"""\
[build-system]
requires = ["setuptools>=75.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{NAME}"
version = "0.1.0"
description = "V2 + Biome repository-shaped birth fixture"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["mypy==2.3.1", "pytest==9.1.1", "ruff==0.16.6", "pyyaml>=6.0.2"]

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "B", "I", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
packages = ["{PKG}"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""

INVENTORY = '''\
#!/usr/bin/env python3
"""Fixture inventory check: the execution surfaces exist."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("Makefile", "Repo.mk", ".l9/repo-workflow.json", "biome.json")
missing = [p for p in REQUIRED if not (ROOT / p).is_file()]
raise SystemExit(f"missing: {missing}" if missing else 0)
'''


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _payload(root: Path) -> Path:
    for fixture, rel in CORE_STAMPED.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURES / fixture, target)
    _write(root, "Repo.mk", REPO_MK)
    _write(root, "pyproject.toml", PYPROJECT)
    _write(
        root,
        ".l9/architecture.yaml",
        f"schema: l9.architecture-spec/v1\nmetadata:\n  repository: Quantum-L9/{NAME}\n",
    )
    _write(
        root,
        f"src/{PKG}/__init__.py",
        '"""V2 fixture package."""\n\n\ndef ping() -> str:\n    return "pong"\n',
    )
    _write(
        root,
        "tests/test_ping.py",
        f'from {PKG} import ping\n\n\ndef test_ping() -> None:\n    assert ping() == "pong"\n',
    )
    _write(root, "scripts/inventory_check.py", INVENTORY)
    git = ["git", "-C", str(root), "-c", "user.email=f@x", "-c", "user.name=fixture"]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*git, "add", "--", "."], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    return root


@pytest.fixture(scope="module")
def born(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    tmp = tmp_path_factory.mktemp("v2birth")
    payload = _payload(tmp / "payload")
    contract = tmp / "payload.json"
    compiled = subprocess.run(
        [
            sys.executable,
            str(BIRTH_RUNNER / "compile_birth_payload.py"),
            "--source",
            str(payload),
            "--source-repository",
            f"Quantum-L9/{NAME}",
            "--require-mode",
            "authoritative",
            "--out",
            str(contract),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["L9_SKIP_BIRTH_ACCEPTANCE"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            str(BIRTH_RUNNER / "new_repo.py"),
            "--repo",
            NAME,
            "--pkg",
            PKG,
            "--desc",
            "V2 Biome fixture",
            "--work-dir",
            str(tmp / "work"),
            "--org-profile-src",
            str(ORG_SRC),
            "--repo-class",
            CLASS,
            "--payload",
            str(payload),
            "--payload-contract",
            str(contract),
            "--no-remote",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc, tmp / "work" / NAME, payload


def test_birth_passes(born: tuple[subprocess.CompletedProcess[str], Path, Path]) -> None:
    proc, _, _ = born
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BIRTH: PASS" in proc.stdout
    assert "FAIL" not in proc.stdout


@pytest.mark.parametrize("rel", EXECUTION_SURFACES)
def test_execution_surfaces_pass_through_byte_for_byte(
    born: tuple[subprocess.CompletedProcess[str], Path, Path], rel: str
) -> None:
    _, dest, payload = born
    assert (dest / rel).read_bytes() == (payload / rel).read_bytes(), rel


def test_template_v1_contract_is_not_overlaid(
    born: tuple[subprocess.CompletedProcess[str], Path, Path],
) -> None:
    _, dest, _ = born
    contract = json.loads((dest / ".l9/repo-workflow.json").read_text(encoding="utf-8"))
    assert "schema_version" not in contract
    assert (dest / "Makefile").read_bytes() != (
        REPO / "tools" / "l9_repo" / "Makefile.template"
    ).read_bytes()


@pytest.mark.parametrize("rel", V1_RUNTIME)
def test_template_v1_runtime_is_retired(
    born: tuple[subprocess.CompletedProcess[str], Path, Path], rel: str
) -> None:
    _, dest, _ = born
    assert not (dest / rel).exists(), f"stale V1 runtime survived: {rel}"


def test_class_is_stamped(born: tuple[subprocess.CompletedProcess[str], Path, Path]) -> None:
    _, dest, _ = born
    receipt = json.loads((dest / ".l9" / "birth-receipt.json").read_text(encoding="utf-8"))
    assert receipt["repo_class"] == CLASS
    assert receipt["payload_mode"] == "authoritative"
    marker = (dest / ".l9" / "org-birth-profile.yaml").read_text(encoding="utf-8")
    assert f"profile: {CLASS}" in marker


def test_class_materializes_rendered_dependabot(
    born: tuple[subprocess.CompletedProcess[str], Path, Path],
) -> None:
    """`org_seeded_self_governed` seeds a per-repository Dependabot render; the
    newborn's uv.lock is what it must have been rendered from."""
    _, dest, _ = born
    dependabot = (dest / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "uv"' in dependabot or "package-ecosystem: uv" in dependabot
    assert not (dest / ".github" / "workflows" / "governance.yml").exists()


def test_facade_routes_to_repo_mk(
    born: tuple[subprocess.CompletedProcess[str], Path, Path],
) -> None:
    _, dest, _ = born
    proc = subprocess.run(
        ["make", "validate"], cwd=dest, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
