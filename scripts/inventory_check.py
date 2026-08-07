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
)

# tools/ is allowed only for the Core runtime surface.
TOOLS_ALLOW = frozenset({"l9_repo", "check_workflow_integrity.py"})

REQUIRED = (
    ".l9/ci-pin",
    ".l9/repo-workflow.json",
    ".l9/repo-workflow.schema.json",
    ".l9/architecture.yaml",
    ".l9/ownership.yaml",
    ".l9/sdk-compatibility.yaml",
    ".l9-template-version",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "Repo.mk",
    "MANIFEST.sha256",
    "requirements-repo-runtime.txt",
    "LICENSE",
    "README.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "TEMPLATE_INVENTORY.md",
    "docs/repository-execution-runtime.md",
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
    "scripts/regenerate_runtime_manifest.py",
    "tools/l9_repo/Makefile.template",
    "tools/l9_repo/__main__.py",
    "tools/check_workflow_integrity.py",
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
    tools = ROOT / "tools"
    if tools.exists():
        if not tools.is_dir():
            errors.append("tools must be a directory when present")
        else:
            for child in sorted(tools.iterdir()):
                if child.name in {"__pycache__", ".DS_Store"}:
                    continue
                if child.name not in TOOLS_ALLOW:
                    errors.append(f"deny tools entry (not runtime surface): tools/{child.name}")
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")
    pin = ROOT / ".l9" / "ci-pin"
    if pin.is_file():
        text = pin.read_text(encoding="utf-8")
        for key in ("ORG_GITHUB_SHA", "L9_CI_CORE_PIN", "L9_REPO_RUNTIME_PIN"):
            if f"{key}=" not in text:
                errors.append(f".l9/ci-pin missing {key}")
        for line in text.splitlines():
            if line.startswith("ORG_GITHUB_SHA="):
                sha = line.split("=", 1)[1].strip()
                if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                    errors.append(f"ORG_GITHUB_SHA must be 40-char hex, got {sha!r}")
            if line.startswith("L9_REPO_RUNTIME_PIN="):
                sha = line.split("=", 1)[1].strip()
                if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                    errors.append(f"L9_REPO_RUNTIME_PIN must be 40-char hex, got {sha!r}")
    makefile = ROOT / "Makefile"
    template = ROOT / "tools" / "l9_repo" / "Makefile.template"
    if makefile.is_file() and template.is_file():
        if makefile.read_bytes() != template.read_bytes():
            errors.append("Makefile must be byte-identical to tools/l9_repo/Makefile.template")
    if errors:
        for err in errors:
            print(f"inventory-check FAIL: {err}", file=sys.stderr)
        return 1
    print("inventory-check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
