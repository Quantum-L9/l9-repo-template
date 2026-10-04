"""Template compliance: generic birth-factory identity, product-kind-neutral checks.

The old template classified itself as the "non-Constellation Python museum" and
delegated Nodes and `constellation_*` dependencies to sibling templates. That
architecture is retired: this repository is the generic L9 repository birth
factory, and its chassis validation must not reject a product merely by shape.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INVENTORY_CHECK = REPO / "scripts" / "inventory_check.py"
HYGIENE_AUDIT = REPO / "scripts" / "repo_hygiene_audit.py"

# Active chassis law and the generated rules rendered from it. None may delegate
# a product kind to a retired sibling template or describe this repository as
# the museum.
ACTIVE_LAW = (
    "README.md",
    "ARCHITECTURE.md",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/WHEN_TO_USE.md",
    "docs/VALIDATION.md",
    "docs/PARAMETRIC_CURSOR_RULES.md",
    ".l9/architecture.yaml",
    ".l9/ownership.yaml",
    ".l9/sdk-compatibility.yaml",
    ".coderabbit.yaml",
    "plugin-config.yaml",
    "scripts/inventory_check.py",
    "scripts/repo_hygiene_audit.py",
    ".cursor/rules/templates/l9-python-repo.mdc.template",
    ".cursor/rules/templates/l9-agents.mdc.template",
    ".cursor/rules/templates/fastapi.mdc.template",
    ".cursor/rules/l9-python-repo.mdc",
    ".cursor/rules/l9-agents.mdc",
    ".cursor/rules/fastapi.mdc",
    "llms.txt",
    "docs/LIFECYCLE.md",
    "docs/ops/SECRET_ROTATION_CHECKLIST.md",
)

# Matched case-insensitively. Retired sibling routing, the museum identity, and
# product-kind-specific factory law (a rule telling a born product whether it is
# or is not a Gate worker, or which SDK it must not depend on) must not return.
RETIRED_SIBLING_TERMS = (
    "L9-Node-Template",
    "Constellation.PackageTemplate",
    "quantum-l9-python-museum",
    "museum",
    "sibling template",
    "GATE_URL",
    "constellation-node-sdk",
    "not a Gate worker",
)

# Surfaces the museum rejected as "wrong product". A generic factory must not
# deny any of them by shape: whether a born repository is a Node, a Dependency,
# an engine or a contract library is decided by its resolved product semantics
# upstream, never by this chassis.
PRODUCT_SHAPED_DIRS = ("engine", "chassis", "domains", "contracts", "client", "database", "deploy")
PRODUCT_SHAPED_FILES = ("nodespec.yaml", "spec.yaml")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_factory_identity_docs() -> None:
    for rel in ("README.md", "ARCHITECTURE.md", "docs/WHEN_TO_USE.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "birth factory" in text, f"{rel} must describe the repository birth factory"


@pytest.mark.parametrize("rel", ACTIVE_LAW)
def test_active_law_does_not_delegate_to_retired_siblings(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8").lower()
    for term in RETIRED_SIBLING_TERMS:
        assert term.lower() not in text, (
            f"{rel} still carries retired sibling-template or product-kind-specific term {term!r}"
        )


def test_product_kind_is_declared_upstream_not_inferred() -> None:
    text = (REPO / ".l9" / "architecture.yaml").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert "product_semantics" in text
    assert "upstream_input" in text
    assert "non_constellation_python" in text, "the current org birth class is preserved"
    assert "It is not a ProductKind" in flat


def test_absent_dual_runner() -> None:
    assert not (REPO / "Justfile").exists()
    assert not (REPO / "justfile").exists()


def _product_shaped_tree(root: Path) -> None:
    for name in PRODUCT_SHAPED_DIRS:
        (root / name).mkdir(parents=True)
        (root / name / "__init__.py").write_text("", encoding="utf-8")
    for name in PRODUCT_SHAPED_FILES:
        (root / name).write_text("kind: node\n", encoding="utf-8")
    pkg = root / "src" / "node_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "handlers.py").write_text(
        "from constellation_node_sdk import create_node_app, register_handler\n"
        "from gate_sdk import TransportPacket\n\n"
        "app = create_node_app()\n\n\n"
        "@register_handler('echo')\n"
        "def echo(packet: TransportPacket) -> TransportPacket:\n"
        "    return packet.derive()\n",
        encoding="utf-8",
    )
    (pkg / "enginehandlers.py").write_text("ENGINE = True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "node-pkg"\ndependencies = ["constellation-node-sdk>=1"]\n',
        encoding="utf-8",
    )


def test_inventory_check_does_not_reject_product_shaped_surfaces(tmp_path: Path) -> None:
    """Node-, engine-, contract- and SDK-shaped surfaces are not inventory errors.

    The fixture is deliberately NOT a complete chassis, so the checker still
    fails on missing required files. What it must never do is name a product
    surface as the reason.
    """
    _product_shaped_tree(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(INVENTORY_CHECK)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "L9_INVENTORY_ROOT": str(tmp_path)},
    )
    assert proc.returncode == 1, "an incomplete chassis still fails"
    assert "missing required file" in proc.stderr
    for forbidden in (
        "deny directory present",
        "handlers.py",
        "constellation-node-sdk",
        "Constellation node API",
        "nodespec.yaml",
        "spec.yaml",
        "L9-Node-Template",
    ):
        assert forbidden not in proc.stderr, (
            f"inventory_check rejected a product-shaped surface by shape: {forbidden!r}"
        )


def test_inventory_check_still_denies_org_ci_distribution(tmp_path: Path) -> None:
    """Neutrality about product kind does not loosen the CI ownership boundary."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "governance.yml").write_text("name: governance\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(INVENTORY_CHECK)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "L9_INVENTORY_ROOT": str(tmp_path)},
    )
    assert proc.returncode == 1
    assert ".github/workflows/governance.yml" in proc.stderr
    assert "l9-ci-core" in proc.stderr


def test_hygiene_audit_does_not_reject_product_shaped_surfaces(tmp_path: Path) -> None:
    """The hygiene audit keeps eval/exec/print and the dual-runner ban, nothing else."""
    _product_shaped_tree(tmp_path)
    (tmp_path / "src" / "node_pkg" / "debug.py").write_text(
        "def dump(x):\n    print(x)\n", encoding="utf-8"
    )
    hygiene = _load("repo_hygiene_audit_under_test", HYGIENE_AUDIT)
    hygiene.ROOT = tmp_path
    hygiene.SRC = tmp_path / "src"

    assert hygiene.audit_scaffold() == []
    findings = hygiene.audit_src()
    assert findings == ["src/node_pkg/debug.py:2: forbidden call print()"]

    (tmp_path / "Justfile").write_text("default:\n\techo hi\n", encoding="utf-8")
    assert hygiene.audit_scaffold() == ["forbidden root file present: Justfile"]
