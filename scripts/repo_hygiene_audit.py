#!/usr/bin/env python3
"""Generic repository hygiene audit for the L9 repository chassis.

Enforces the eval/exec/print ban in src/ and the single-task-runner rule
(no Justfile beside `make`). It does not classify the product kind of the
repository: engines, handlers, contracts, nodespecs, Gate or SDK surfaces are
legitimate products of the birth factory and are not hygiene findings.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# One task runner. `make` is the chassis facade; a second runner is drift.
FORBIDDEN_ROOT_FILES = ("Justfile", "justfile")


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.findings: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "print"}:
            self.findings.append(f"{self.rel}:{node.lineno}: forbidden call {node.func.id}()")
        self.generic_visit(node)


def audit_src(root: Path | None = None) -> list[str]:
    root = ROOT if root is None else root
    findings: list[str] = []
    src = root / "src"
    if not src.is_dir():
        return ["missing src/"]
    for path in sorted(src.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            findings.append(f"{rel}: syntax error: {exc}")
            continue
        visitor = _Visitor(rel)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def audit_scaffold(root: Path | None = None) -> list[str]:
    root = ROOT if root is None else root
    findings: list[str] = []
    for name in FORBIDDEN_ROOT_FILES:
        if (root / name).exists():
            findings.append(f"forbidden root file present: {name}")
    return findings


def main(argv: list[str] | None = None) -> int:
    # `--root` lets the factory audit a newborn FROM the factory, so a product
    # repository never has to carry the auditor to be audited at birth.
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--root", type=Path, default=None, help="repository to audit")
    given = parser.parse_args(argv).root
    root = ROOT if given is None else given.resolve()
    findings = audit_scaffold(root) + audit_src(root)
    if findings:
        for item in findings:
            print(f"hygiene FAIL: {item}", file=sys.stderr)
        return 1
    print("hygiene OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
