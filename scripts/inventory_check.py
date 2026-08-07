#!/usr/bin/env python3
"""Fail closed if museum inventory invariants are violated."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DENY_DIRS = (
    "engine",
    "chassis",
    "domains",
    "client",
    "database",
    "deploy",
    "example_service",
    "tools",
)

REQUIRED = (
    ".l9/ci-pin",
    ".l9-template-version",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "LICENSE",
    "README.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "TEMPLATE_INVENTORY.md",
    "spec.yaml",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    "src/l9_example_pkg/__init__.py",
    "src/l9_example_pkg/app.py",
    "src/l9_example_pkg/handlers.py",
    "scripts/sync_ci_from_pack.py",
    "scripts/bootstrap_rename.py",
    "scripts/inventory_check.py",
    "scripts/render_cursor_rules.py",
    "scripts/wait_for_http.py",
    "scripts/preflight_local_env.py",
    "plugin-config.yaml",
    ".semgrep/semgrep-rules.yaml",
    "observability/docker-compose.observability.yml",
)


def main() -> int:
    errors: list[str] = []
    for name in DENY_DIRS:
        path = ROOT / name
        if path.exists():
            errors.append(f"deny directory present: {name}/")
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")
    pin = ROOT / ".l9" / "ci-pin"
    if pin.is_file():
        text = pin.read_text(encoding="utf-8")
        if "ORG_GITHUB_SHA=" not in text:
            errors.append(".l9/ci-pin missing ORG_GITHUB_SHA")
        else:
            for line in text.splitlines():
                if line.startswith("ORG_GITHUB_SHA="):
                    sha = line.split("=", 1)[1].strip()
                    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                        errors.append(f"ORG_GITHUB_SHA must be 40-char hex, got {sha!r}")
    if errors:
        for err in errors:
            print(f"inventory-check FAIL: {err}", file=sys.stderr)
        return 1
    print("inventory-check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
