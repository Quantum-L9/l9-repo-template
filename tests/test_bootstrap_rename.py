"""Tests for scripts/bootstrap_rename.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
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
    (pkg / "handlers.py").write_text(
        'ACTION = "example"  # l9_example_pkg\n',
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
    handlers = (tmp_path / "src" / "smoke_pkg" / "handlers.py").read_text(encoding="utf-8")
    assert "smoke_pkg" in handlers
    assert "l9_example_pkg" not in handlers
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "smoke-pkg" in readme
    assert "l9-example-pkg" not in readme
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "smoke_pkg.app:app" in dockerfile
    assert "l9_example_pkg" not in dockerfile
    repo_mk = (tmp_path / "Repo.mk").read_text(encoding="utf-8")
    assert "smoke_pkg.app:app" in repo_mk


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
