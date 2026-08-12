#!/usr/bin/env python3
"""Generic repo hygiene audit for the non-Constellation museum template.

Enforces eval/exec/print bans in src/ and accidental reintroduction of
Constellation node/dep scaffolding (Justfile, contracts/, enginehandlers).
Does NOT encode PacketEnvelope/Gate peer-routing laws (those belong to
L9-Node-Template / Gate_SDK).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

FORBIDDEN_ROOT_FILES = ("Justfile", "justfile")
FORBIDDEN_ROOT_DIRS = ("contracts", "engine", "chassis", "domains")
FORBIDDEN_REL_SUFFIXES = ("enginehandlers.py", "nodespec.yaml")


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.findings: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "print"}:
            self.findings.append(f"{self.rel}:{node.lineno}: forbidden call {node.func.id}()")
        self.generic_visit(node)


def audit_src() -> list[str]:
    findings: list[str] = []
    if not SRC.is_dir():
        return ["missing src/"]
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            findings.append(f"{rel}: syntax error: {exc}")
            continue
        visitor = _Visitor(rel)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def audit_scaffold() -> list[str]:
    findings: list[str] = []
    for name in FORBIDDEN_ROOT_FILES:
        if (ROOT / name).exists():
            findings.append(f"forbidden root file present: {name}")
    for name in FORBIDDEN_ROOT_DIRS:
        if (ROOT / name).exists():
            findings.append(f"forbidden root directory present: {name}/")
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.endswith(suf) or rel == suf for suf in FORBIDDEN_REL_SUFFIXES):
            findings.append(f"forbidden constellation scaffolding path: {rel}")
    return findings


def main() -> int:
    findings = audit_scaffold() + audit_src()
    if findings:
        for item in findings:
            print(f"hygiene FAIL: {item}", file=sys.stderr)
        return 1
    print("hygiene OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
