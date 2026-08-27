"""Tests for scripts/bootstrap_rename.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RENAME = REPO / "scripts" / "bootstrap_rename.py"


def _seed_tree(tmp: Path) -> None:
    pkg = tmp / "src" / "l9_example_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        '"""pkg"""\n\n__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (pkg / "app.py").write_text(
        'app = "l9_example_pkg.app:app"\n',
        encoding="utf-8",
    )
    (pkg / "settings.py").write_text(
        'SERVICE = "l9_example_pkg"\n',
        encoding="utf-8",
    )
    (tmp / "pyproject.toml").write_text(
        'name = "l9-example-pkg"\npackages = ["l9_example_pkg"]\n',
        encoding="utf-8",
    )
    (tmp / "Dockerfile").write_text(
        'CMD ["uvicorn", "l9_example_pkg.app:app"]\n',
        encoding="utf-8",
    )
    (tmp / "Repo.mk").write_text("PKG_APP ?= l9_example_pkg.app:app\n", encoding="utf-8")
    (tmp / "README.md").write_text("l9-example-pkg / l9_example_pkg\n", encoding="utf-8")


def test_dry_run_does_not_rename(tmp_path: Path) -> None:
    _seed_tree(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(RENAME), "--pkg", "smoke_pkg", "--dry-run", "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert (tmp_path / "src" / "l9_example_pkg").is_dir()
    assert not (tmp_path / "src" / "smoke_pkg").exists()
    assert "dry-run" in proc.stdout


def test_rename_rewrites_and_moves(tmp_path: Path) -> None:
    _seed_tree(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(RENAME), "--pkg", "smoke_pkg", "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "src" / "l9_example_pkg").exists()
    assert (tmp_path / "src" / "smoke_pkg" / "app.py").is_file()
    app = (tmp_path / "src" / "smoke_pkg" / "app.py").read_text(encoding="utf-8")
    assert "smoke_pkg.app:app" in app
    assert "l9_example_pkg" not in app
    settings = (tmp_path / "src" / "smoke_pkg" / "settings.py").read_text(encoding="utf-8")
    assert "smoke_pkg" in settings
    assert "l9_example_pkg" not in settings
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "smoke-pkg" in readme
    assert "l9-example-pkg" not in readme
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "smoke_pkg.app:app" in dockerfile
    assert "l9_example_pkg" not in dockerfile
    repo_mk = (tmp_path / "Repo.mk").read_text(encoding="utf-8")
    assert "smoke_pkg.app:app" in repo_mk


def _seed_identity(tmp: Path) -> None:
    (tmp / ".l9").mkdir(parents=True)
    (tmp / ".l9" / "architecture.yaml").write_text(
        "schema: l9.architecture-spec/v1\n"
        "metadata:\n"
        "  repository: Quantum-L9/l9-repo-template\n"
        "  status: authoritative\n",
        encoding="utf-8",
    )
    (tmp / ".l9" / "ownership.yaml").write_text(
        "schema: l9.ownership-spec/v1\nrepository: Quantum-L9/l9-repo-template\n",
        encoding="utf-8",
    )
    (tmp / ".l9" / "sdk-compatibility.yaml").write_text(
        "schema: l9.sdk-compatibility/v1\nrepository: Quantum-L9/l9-repo-template\n",
        encoding="utf-8",
    )
    (tmp / "scripts").mkdir(parents=True)
    (tmp / "scripts" / "birth-runner").mkdir(parents=True)
    (tmp / "scripts" / "birth-runner" / "config.template.yaml").write_text(
        'template_repo: "Quantum-L9/l9-repo-template"  # provenance\n',
        encoding="utf-8",
    )


def _rename(tmp: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RENAME), "--pkg", "smoke_pkg", "--root", str(tmp), *extra],
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_identity_rewrite(tmp_path: Path) -> None:
    """--org/--repo stamp authoritative metadata; provenance refs stay."""
    _seed_tree(tmp_path)
    _seed_identity(tmp_path)
    proc = _rename(tmp_path, "--org", "Example", "--repo", "born-svc")
    assert proc.returncode == 0, proc.stderr
    for rel in (".l9/architecture.yaml", ".l9/ownership.yaml", ".l9/sdk-compatibility.yaml"):
        text = (tmp_path / rel).read_text(encoding="utf-8")
        assert "repository: Example/born-svc" in text, rel
        assert "Quantum-L9/l9-repo-template" not in text, rel
    provenance = (tmp_path / "scripts" / "birth-runner" / "config.template.yaml").read_text(
        encoding="utf-8"
    )
    assert "Quantum-L9/l9-repo-template" in provenance  # provenance preserved


def test_identity_requires_both_org_and_repo(tmp_path: Path) -> None:
    _seed_tree(tmp_path)
    proc = _rename(tmp_path, "--org", "Example")
    assert proc.returncode == 2
    assert "--org and --repo must be provided together" in proc.stderr


def test_identity_rewrite_leaves_custom_identity_untouched(tmp_path: Path) -> None:
    """A repo whose identity was already stamped is never clobbered."""
    _seed_tree(tmp_path)
    _seed_identity(tmp_path)
    arch = tmp_path / ".l9" / "architecture.yaml"
    text = arch.read_text(encoding="utf-8")
    arch.write_text(
        text.replace("Quantum-L9/l9-repo-template", "Acme/other-svc"),
        encoding="utf-8",
    )
    proc = _rename(tmp_path, "--org", "Example", "--repo", "born-svc")
    assert proc.returncode == 0, proc.stderr
    assert "Acme/other-svc" in arch.read_text(encoding="utf-8")
    assert "Example/born-svc" not in arch.read_text(encoding="utf-8")


def test_refuse_existing_target(tmp_path: Path) -> None:
    _seed_tree(tmp_path)
    (tmp_path / "src" / "smoke_pkg").mkdir()
    proc = subprocess.run(
        [sys.executable, str(RENAME), "--pkg", "smoke_pkg", "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


# `l9_example_pkg` appears in two different roles across the tree:
#
#   identity  — this repository's package (src/, imports, inventory REQUIRED).
#               Rename MUST rewrite these.
#   sentinel  — the string the birth tooling compares against to recognize a
#               pristine template. Rename MUST NOT rewrite these: a renamed
#               new_repo.py rejects the very package name it was just given.
#
# Only the second set belongs in SKIP_REL_PATHS, and the failure is invisible
# until someone runs the tests inside a repository born from the template.
SENTINEL_FILES = (
    "scripts/bootstrap_rename.py",
    "scripts/birth-runner/new_repo.py",
    "tests/unit/test_bootstrap_rename.py",
    "tests/unit/test_new_repo_orchestrator.py",
    "tests/integration/test_new_repo_local_birth.py",
)


def _rename_tree_containing(
    tmp_path: Path, rels: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    _seed_tree(tmp_path)
    for rel in rels:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO / rel).read_bytes())
    return subprocess.run(
        [sys.executable, str(RENAME), "--pkg", "smoke_pkg", "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_sentinel_files_survive_rename_byte_for_byte(tmp_path: Path) -> None:
    proc = _rename_tree_containing(tmp_path, SENTINEL_FILES)
    assert proc.returncode == 0, proc.stderr
    for rel in SENTINEL_FILES:
        assert (tmp_path / rel).read_bytes() == (REPO / rel).read_bytes(), (
            f"{rel} carries the template sentinel and must be in SKIP_REL_PATHS"
        )
    # Identity references elsewhere are still rewritten.
    assert "smoke_pkg" in (tmp_path / "Repo.mk").read_text(encoding="utf-8")


def test_renamed_orchestrator_still_rejects_the_sentinel(tmp_path: Path) -> None:
    """The behavioral form of the invariant above.

    If rename rewrites the sentinel inside new_repo.py, the renamed copy starts
    rejecting the new package name and accepting `l9_example_pkg` — exactly
    backwards.
    """
    proc = _rename_tree_containing(tmp_path, ("scripts/birth-runner/new_repo.py",))
    assert proc.returncode == 0, proc.stderr

    probe = (
        "import importlib.util, sys;"
        f"spec = importlib.util.spec_from_file_location('probe', r'{tmp_path}/scripts/birth-runner/new_repo.py');"
        "m = importlib.util.module_from_spec(spec);"
        "sys.modules['probe'] = m;"
        "spec.loader.exec_module(m);"
        "ok = m.validate_package_name('smoke_pkg');"
        "rejected = False\n"
        "try:\n"
        "    m.validate_package_name('l9_example_pkg')\n"
        "except m.BirthError:\n"
        "    rejected = True\n"
        "print(ok, rejected)"
    )
    out = subprocess.run([sys.executable, "-c", probe], check=False, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "smoke_pkg True", out.stdout + out.stderr
