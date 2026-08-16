#!/usr/bin/env python3
"""Fail closed if museum inventory invariants are violated."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Env override exists so tests can run the checker against a fixture tree.
ROOT = Path(os.environ.get("L9_INVENTORY_ROOT") or Path(__file__).resolve().parents[1])

DENY_DIRS = (
    "engine",
    "chassis",
    "domains",
    "client",
    "database",
    "deploy",
    "example_service",
    "contracts",
)

DENY_FILES = ("Justfile", "justfile", "nodespec.yaml", "spec.yaml")

# Legacy org CI distribution surfaces must not reappear: CI orchestration
# belongs to l9-ci-core and organization CI control to l9-ci-control-plane.
DENY_CI_DISTRIBUTION = (
    ".l9/ci-pin",
    "scripts/sync_ci_from_pack.py",
    "requirements-consumer-ci.txt",
    ".github/workflows/l9-analysis.yml",
    ".github/workflows/l9-lint-test.yml",
    ".github/workflows/on-org-update.yml",
    ".github/workflows/governance.yml",
    ".github/governance",
)

TOOLS_ALLOW = frozenset({"l9_repo", "check_workflow_integrity.py"})

REQUIRED = (
    ".l9/runtime-provenance.yaml",
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
    "docs/WHEN_TO_USE.md",
    "docs/VALIDATION.md",
    "docs/LIFECYCLE.md",
    "docs/repository-execution-runtime.md",
    "docs/ops/REPO_BIRTH.md",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
    "src/l9_example_pkg/__init__.py",
    "src/l9_example_pkg/app.py",
    "src/l9_example_pkg/settings.py",
    "src/l9_example_pkg/health.py",
    "scripts/bootstrap_rename.py",
    "scripts/inventory_check.py",
    "scripts/repo_hygiene_audit.py",
    "scripts/render_cursor_rules.py",
    "scripts/wait_for_http.py",
    "scripts/preflight_local_env.py",
    "scripts/regenerate_runtime_manifest.py",
    "scripts/birth-runner/README.md",
    "scripts/birth-runner/01_preflight.sh",
    "scripts/birth-runner/02_bootstrap.sh",
    "scripts/birth-runner/03_verify.sh",
    "tools/l9_repo/Makefile.template",
    "tools/l9_repo/__main__.py",
    "tools/check_workflow_integrity.py",
    "plugin-config.yaml",
    ".semgrep/semgrep-rules.yaml",
    "observability/docker-compose.observability.yml",
    ".cursor/rules/templates/l9-python-repo.mdc.template",
    ".cursor/rules/templates/fastapi.mdc.template",
    # Inherited organization defaults
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/labels.yml",
)

MENTION_CHECKS = (
    ("README.md", ("L9-Node-Template", "Constellation.PackageTemplate", "outside")),
    ("docs/WHEN_TO_USE.md", ("L9-Node-Template", "Constellation.PackageTemplate")),
    ("AGENTS.md", (".l9/architecture.yaml", ".l9/ownership.yaml")),
)


def main() -> int:
    errors: list[str] = []
    for name in DENY_DIRS:
        if (ROOT / name).exists():
            errors.append(f"deny directory present: {name}/")
    for name in DENY_FILES:
        if (ROOT / name).exists():
            errors.append(f"deny file present: {name}")
    for name in DENY_CI_DISTRIBUTION:
        if (ROOT / name).exists():
            errors.append(
                f"legacy CI distribution surface present: {name} — "
                "CI orchestration belongs to l9-ci-core / l9-ci-control-plane"
            )
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
    if (ROOT / "src" / "l9_example_pkg" / "handlers.py").exists():
        errors.append("handlers.py must not exist (use L9-Node-Template for nodes)")
    pyproject_path = ROOT / "pyproject.toml"
    if not pyproject_path.is_file():
        # Already reported by the REQUIRED check; avoid an unguarded read crash.
        pyproject = ""
    else:
        pyproject = pyproject_path.read_text(encoding="utf-8")
    if "constellation-node-sdk" in pyproject:
        errors.append("pyproject.toml must not require constellation-node-sdk")
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "create_node_app" in text or "register_handler" in text:
            errors.append(
                f"Constellation node API in {path.relative_to(ROOT)} — use L9-Node-Template"
            )
    provenance = ROOT / ".l9" / "runtime-provenance.yaml"
    if provenance.is_file():
        text = provenance.read_text(encoding="utf-8")
        if "l9_ci_core_harvest_revision" not in text:
            errors.append(".l9/runtime-provenance.yaml missing l9_ci_core_harvest_revision")
    repo_mk = ROOT / "Repo.mk"
    if repo_mk.is_file():
        content = repo_mk.read_text(encoding="utf-8")
        if not re.search(r"^ci:", content, re.M):
            errors.append(
                "Repo.mk must define a ci target (make ci repository-local execution facade)"
            )
    makefile = ROOT / "Makefile"
    template = ROOT / "tools" / "l9_repo" / "Makefile.template"
    if makefile.is_file() and template.is_file():
        if makefile.read_bytes() != template.read_bytes():
            errors.append("Makefile must be byte-identical to tools/l9_repo/Makefile.template")
    for rel, needles in MENTION_CHECKS:
        path = ROOT / rel
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in content:
                errors.append(f"{rel} must mention {needle!r}")
    if errors:
        for err in errors:
            print(f"inventory-check FAIL: {err}", file=sys.stderr)
        return 1
    print("inventory-check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
