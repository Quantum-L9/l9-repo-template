#!/usr/bin/env python3
"""Regenerate MANIFEST.sha256 for repository-execution runtime surfaces."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATHS = (
    "Makefile",
    "Repo.mk",
    "MANIFEST.sha256",  # placeholder; rewritten below without self
    "requirements-repo-runtime.txt",
    "docs/repository-execution-runtime.md",
    "tools/check_workflow_integrity.py",
    ".l9/repo-workflow.json",
    ".l9/repo-workflow.schema.json",
    ".l9/architecture.yaml",
    ".l9/ownership.yaml",
    ".l9/sdk-compatibility.yaml",
)


def iter_runtime_files() -> list[str]:
    files: list[str] = []
    for rel in PATHS:
        if rel == "MANIFEST.sha256":
            continue
        path = ROOT / rel
        if path.is_file():
            files.append(rel)
    l9_repo = ROOT / "tools" / "l9_repo"
    for path in sorted(l9_repo.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files.append(path.relative_to(ROOT).as_posix())
    return sorted(set(files))


def main() -> int:
    lines = []
    for rel in iter_runtime_files():
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    (ROOT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote MANIFEST.sha256 ({len(lines)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
