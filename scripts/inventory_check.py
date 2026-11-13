#!/usr/bin/env python3
"""Fail closed if repository chassis inventory invariants are violated.

This checker describes the CHASSIS, not the product. It never classifies the
product kind of the repository it runs in: a Node, a Dependency, an engine, a
contract library or a Gate-routed worker are all legitimate products of the
birth factory, and their surfaces are not denied here merely by shape. Product
kind is owned upstream (Quantum-L9/.github semantics/) and arrives resolved.

What IS denied: organization CI distribution surfaces (CI execution belongs to
l9-ci-core; targeting to the central control plane), a second task runner, and
duplicated chassis configuration.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Env override exists so tests can run the checker against a fixture tree.
ROOT = Path(os.environ.get("L9_INVENTORY_ROOT") or Path(__file__).resolve().parents[1])

# Chassis hygiene only: a second task runner beside `make`, and a sample file
# superseded by the activated root configuration.
DENY_FILES = (
    "Justfile",
    "justfile",
    "docs/examples/coderabbit.yaml",
)

# Repository-local CI orchestration must not reappear. Execution semantics belong
# to l9-ci-core and organization targeting/enforcement belongs to the central
# control plane. Repo-local shared CodeQL query policy is also forbidden.
DENY_CI_DISTRIBUTION = (
    ".l9/ci-pin",
    "scripts/sync_ci_from_pack.py",
    "requirements-consumer-ci.txt",
    ".github/workflows/l9-analysis.yml",
    ".github/workflows/l9-lint-test.yml",
    ".github/workflows/l9-lint-test-node.yml",
    ".github/workflows/on-org-update.yml",
    ".github/workflows/governance.yml",
    ".github/workflows/codeql.yml",
    ".github/governance",
    ".github/codeql/codeql-config.yml",
)

# Repository Execution V2 (l9.repo-execution/v2): the execution runtime is
# Core-owned and never vendored. `tools/` was only ever the vendored V1 runtime,
# so it must not reappear.
V2_CONTRACT = {
    "schema": "l9.repo-execution/v2",
    "facade": "make-v1",
    "required_phases": ["setup", "validate", "check", "test"],
}
FACADE_HEADER = "# GENERATED repository execution facade: make-v1. DO NOT EDIT."
FACADE_VERBS = ("help", "setup", "validate", "check", "test")
V2_LEAVES = ("repo-setup", "repo-validate", "repo-check", "repo-test")
RETIRED_V1_RUNTIME = (
    "tools",
    ".l9/repo-workflow.schema.json",
    ".l9/runtime-provenance.yaml",
    "MANIFEST.sha256",
    "requirements-repo-runtime.txt",
    "scripts/regenerate_runtime_manifest.py",
)

REQUIRED = (
    ".l9/repo-workflow.json",
    ".l9/architecture.yaml",
    ".l9/ownership.yaml",
    ".l9/org-birth-profile.yaml",
    ".l9/sdk-compatibility.yaml",
    ".l9/ci.json",
    ".l9-template-version",
    ".python-version",
    ".gitattributes",
    ".pre-commit-config.yaml",
    ".gitleaks.toml",
    ".coderabbit.yaml",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "Repo.mk",
    "bootstrap.sh",
    "llms.txt",
    "LICENSE",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
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
    "scripts/reconcile_plugin_config.py",
    "scripts/wait_for_http.py",
    "scripts/preflight_local_env.py",
    "scripts/birth-runner/README.md",
    "scripts/birth-runner/new_repo.py",
    "scripts/birth-runner/birth_provenance.py",
    "scripts/birth-runner/verify_birth_integrity.py",
    "scripts/birth-runner/canonical_ci.py",
    "scripts/birth-runner/payload_ownership.py",
    "scripts/birth-runner/compile_birth_payload.py",
    "scripts/birth-runner/verify_birth_payload.py",
    "scripts/birth-runner/schemas/birth-payload.schema.json",
    "scripts/birth-runner/l9_birth_adapter.py",
    "scripts/birth-runner/package_birth_handoff.py",
    "scripts/birth-runner/product_resolution.py",
    "scripts/birth-runner/semantic-compiler.pin.json",
    "scripts/birth-runner/schemas/l9-product-birth-binding.schema.json",
    "scripts/birth-runner/schemas/superseded/README.md",
    "scripts/birth-runner/payload-ownership.yaml",
    "scripts/birth-runner/01_preflight.sh",
    "scripts/birth-runner/02_bootstrap.sh",
    "scripts/birth-runner/03_verify.sh",
    "plugin-config.yaml",
    ".semgrep/semgrep-rules.yaml",
    "observability/docker-compose.observability.yml",
    ".cursor/rules/templates/l9-python-repo.mdc.template",
    ".cursor/rules/templates/fastapi.mdc.template",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/labels.yml",
)

# Agent/security discovery wiring: the authority surfaces must point at each
# other. These anchors describe the chassis identity, never a product kind.
MENTION_CHECKS = (
    ("README.md", ("repository birth factory", "docs/ops/REPO_BIRTH.md")),
    ("docs/WHEN_TO_USE.md", ("repository birth factory", "ProductKind")),
    ("AGENTS.md", (".l9/architecture.yaml", ".l9/ownership.yaml")),
    ("CLAUDE.md", ("AGENTS.md", ".l9/architecture.yaml", ".l9/org-birth-profile.yaml")),
    ("llms.txt", ("AGENTS.md", "CLAUDE.md", ".l9/architecture.yaml", "bootstrap.sh")),
    ("bootstrap.sh", ("make", "setup")),
    (".gitleaks.toml", ("[extend]", "useDefault = true")),
    (".coderabbit.yaml", ("AGENTS.md", ".l9/architecture.yaml", ".l9/ownership.yaml")),
)


def main() -> int:
    errors: list[str] = []
    for name in DENY_FILES:
        if (ROOT / name).exists():
            errors.append(f"deny file present: {name}")
    for name in DENY_CI_DISTRIBUTION:
        if (ROOT / name).exists():
            errors.append(
                f"repository-local CI/control surface present: {name} — "
                "CI execution belongs to l9-ci-core / central targeting"
            )
    for name in RETIRED_V1_RUNTIME:
        if (ROOT / name).exists():
            errors.append(
                f"retired V1 execution runtime present: {name} — the repository "
                "execution contract is l9.repo-execution/v2 and its runtime is Core-owned"
            )
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")
    license_path = ROOT / "LICENSE"
    if license_path.is_file():
        text = license_path.read_text(encoding="utf-8")
        if "applies only to the Quantum-L9/.github repository" in text:
            errors.append(
                "LICENSE carries the .github-specific repository notice — this file is "
                "copied into every repository born from this template and would disclaim "
                "the repository it governs"
            )
    marker = ROOT / ".l9" / "org-birth-profile.yaml"
    if marker.is_file():
        text = marker.read_text(encoding="utf-8")
        if not re.search(r"^profile:[ \t]*[\"']?[A-Za-z0-9_-]+[\"']?[ \t]*$", text, re.M):
            errors.append(
                ".l9/org-birth-profile.yaml declares no parseable `profile:` — "
                "Quantum-L9/.github resolves an unreadable marker to the default class"
            )
    contract = ROOT / ".l9" / "repo-workflow.json"
    if contract.is_file():
        try:
            declared = json.loads(contract.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f".l9/repo-workflow.json is not valid JSON: {error}")
        else:
            if declared != V2_CONTRACT:
                errors.append(
                    ".l9/repo-workflow.json must be exactly the three-field "
                    "l9.repo-execution/v2 contract"
                )
    repo_mk = ROOT / "Repo.mk"
    if repo_mk.is_file():
        content = repo_mk.read_text(encoding="utf-8")
        if not re.search(r"^ci:", content, re.M):
            errors.append(
                "Repo.mk must define a ci target (make ci repository-local execution facade)"
            )
        for verb in FACADE_VERBS:
            if re.search(rf"^{verb}[ \t]*::?(?!=)", content, re.M):
                errors.append(f"Repo.mk redefines facade target {verb!r}; implement repo-{verb}")
        for leaf in V2_LEAVES:
            if not re.search(rf"^{leaf}[ \t]*:", content, re.M):
                errors.append(f"Repo.mk is missing Repository Execution V2 leaf {leaf}")
    makefile = ROOT / "Makefile"
    if makefile.is_file():
        # Byte-exactness against the released facade is Core's check
        # (run-repository-verification); this only catches a hand-written runner.
        lines = makefile.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != FACADE_HEADER or "include Repo.mk" not in lines:
            errors.append(
                "Makefile must be the Core-generated make-v1 facade "
                "(python3 -m tools.l9_repo --workspace <repo> reconcile from l9-ci-core)"
            )
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
