#!/usr/bin/env python3
"""Rename l9_example_pkg identity to a consumer package name."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".eggs",
}
SKIP_SUFFIXES = (".egg-info",)
# Keep the rename self-test fixture on the template identity strings.
SKIP_REL_PATHS = {
    "tests/test_bootstrap_rename.py",
    "scripts/bootstrap_rename.py",
}


def snake_to_kebab(name: str) -> str:
    return name.replace("_", "-")


def replace_text(content: str, snake: str, kebab: str) -> str:
    content = content.replace("l9_example_pkg", snake)
    content = content.replace("l9-example-pkg", kebab)
    return content


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if any(part.endswith(SKIP_SUFFIXES) for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel in SKIP_REL_PATHS:
            continue
        files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pkg", required=True, help="snake_case package name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)

    snake = args.pkg.strip()
    if not SNAKE_RE.match(snake):
        print(f"invalid --pkg {snake!r}: expect snake_case", file=sys.stderr)
        return 2
    if snake == "l9_example_pkg":
        print("nothing to do: already l9_example_pkg")
        return 0

    kebab = snake_to_kebab(snake)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    src_old = root / "src" / "l9_example_pkg"
    src_new = root / "src" / snake
    if not src_old.is_dir():
        print(f"missing source package dir: {src_old}", file=sys.stderr)
        return 1
    if src_new.exists():
        print(f"target package already exists: {src_new}", file=sys.stderr)
        return 1

    planned: list[str] = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = replace_text(text, snake, kebab)
        if updated != text:
            planned.append(str(path.relative_to(root)))
            if not args.dry_run:
                path.write_text(updated, encoding="utf-8")

    planned.append(f"rename src/l9_example_pkg -> src/{snake}")
    if args.dry_run:
        print("dry-run rename plan:")
        for item in planned:
            print(f"  {item}")
        return 0

    src_old.rename(src_new)
    print(f"renamed to {snake} ({kebab})")
    for item in planned:
        print(f"  {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
