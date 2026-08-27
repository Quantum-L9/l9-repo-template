"""The config a repository ships must describe that repository.

`plugin-config.yaml` is chassis and every generated Cursor rule is rendered from
it, so a stale value in it is not cosmetic: it becomes an active instruction to
an agent working in a repository the claim is false about. These tests hold the
three ways a value can be false — inherited identity, an entrypoint that names
no module, and a capability whose surface was never born — plus the one thing
the reconciler must never do, which is invent a claim.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reconcile_plugin_config.py"
_SPEC = importlib.util.spec_from_file_location("l9_reconcile_plugin_config", SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
reconcile = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = reconcile
_SPEC.loader.exec_module(reconcile)


CONFIG = """plugin_version: "1.2.0"
repo_name: "l9-repo-template"
domain: "quantum-l9-python-museum"

protected_paths:
  - "uv.lock"

high_risk_commands:
  - "rm -rf .venv"

ci_gates:
  - "make verify"

package_name: "l9_product"
app_entrypoint: "l9_product.app:app"
src_layout: true
python_version: "3.12"

graph_record:
  node_type: "plugin_install"
  capabilities:
    - "verify"
    - "obs-optional"
  capability_evidence:
    verify: "Repo.mk"
    obs-optional: "observability"
  data_governance_class: "internal"
"""

ARCHITECTURE = """schema: l9.architecture-spec/v1
metadata:
  repository: Quantum-L9/l9-product-repo
  status: authoritative
identity:
  role: backend-neutral-contract-library
"""


def _tree(root: Path, *, app: bool = True, obs: bool = True, identity: str = ARCHITECTURE) -> Path:
    """A repository the config can be reconciled against."""
    (root / "src" / "l9_product").mkdir(parents=True)
    (root / "src" / "l9_product" / "__init__.py").write_text("", encoding="utf-8")
    if app:
        (root / "src" / "l9_product" / "app.py").write_text("app = 1\n", encoding="utf-8")
    if obs:
        (root / "observability").mkdir()
        (root / "observability" / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "Repo.mk").write_text("# product targets\n", encoding="utf-8")
    (root / ".l9").mkdir()
    (root / ".l9" / "architecture.yaml").write_text(identity, encoding="utf-8")
    (root / "plugin-config.yaml").write_text(CONFIG, encoding="utf-8")
    return root


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


class TestIdentityIsDerivedNotInherited:
    def test_repo_name_comes_from_the_architecture_file(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        assert _run(root).returncode == 0
        text = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'repo_name: "l9-product-repo"' in text
        assert "l9-repo-template" not in text

    def test_domain_comes_from_the_declared_role(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        _run(root)
        text = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'domain: "backend-neutral-contract-library"' in text
        assert "quantum-l9-python-museum" not in text

    def test_domain_falls_back_to_the_repository_name(self, tmp_path: Path) -> None:
        """Honest, not invented: a name is a true statement about a repository."""
        identity = "schema: l9.architecture-spec/v1\nmetadata:\n  repository: Quantum-L9/l9-plain\n"
        root = _tree(tmp_path, identity=identity)
        _run(root)
        assert 'domain: "l9-plain"' in (root / "plugin-config.yaml").read_text(encoding="utf-8")


class TestClaimsAreProvedAgainstTheTree:
    def test_an_entrypoint_with_no_module_is_dropped(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, app=False)
        proc = _run(root)
        assert proc.returncode == 0, proc.stderr
        assert "app_entrypoint" not in (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert "app_entrypoint dropped" in proc.stdout

    def test_an_entrypoint_with_a_module_survives(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        _run(root)
        text = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'app_entrypoint: "l9_product.app:app"' in text

    def test_a_package_entrypoint_counts_as_materialized(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, app=False)
        (root / "src" / "l9_product" / "app").mkdir()
        (root / "src" / "l9_product" / "app" / "__init__.py").write_text("", encoding="utf-8")
        _run(root)
        assert 'app_entrypoint: "l9_product.app:app"' in (root / "plugin-config.yaml").read_text(
            encoding="utf-8"
        )

    def test_a_capability_without_its_evidence_is_dropped(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, obs=False)
        proc = _run(root)
        assert proc.returncode == 0, proc.stderr
        text = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert "obs-optional" not in text
        assert '- "verify"' in text, "an evidenced capability was collateral damage"
        assert 'verify: "Repo.mk"' in text

    def test_a_capability_with_its_evidence_survives(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        _run(root)
        assert '- "obs-optional"' in (root / "plugin-config.yaml").read_text(encoding="utf-8")

    def test_a_package_name_that_names_nothing_fails_closed(self, tmp_path: Path) -> None:
        """Not derivable, so not guessable. Stop rather than invent."""
        root = _tree(tmp_path)
        config = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        (root / "plugin-config.yaml").write_text(
            config.replace('package_name: "l9_product"', 'package_name: "l9_absent"'),
            encoding="utf-8",
        )
        proc = _run(root)
        assert proc.returncode == 1
        assert "names no package" in proc.stderr


class TestTheGate:
    def test_check_fails_on_a_stale_config(self, tmp_path: Path) -> None:
        proc = _run(_tree(tmp_path), "--check")
        assert proc.returncode == 1
        assert "DRIFT" in proc.stderr

    def test_check_passes_once_reconciled(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        assert _run(root).returncode == 0
        assert _run(root, "--check").returncode == 0

    def test_reconciliation_is_idempotent(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        _run(root)
        first = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        _run(root)
        assert (root / "plugin-config.yaml").read_text(encoding="utf-8") == first

    def test_comments_and_untouched_keys_survive(self, tmp_path: Path) -> None:
        """A YAML round-trip would reformat every line nothing asked to change."""
        root = _tree(tmp_path, obs=False)
        _run(root)
        text = (root / "plugin-config.yaml").read_text(encoding="utf-8")
        assert 'plugin_version: "1.2.0"' in text
        assert 'node_type: "plugin_install"' in text
        assert 'data_governance_class: "internal"' in text
        assert '  - "rm -rf .venv"' in text

    def test_this_template_already_describes_itself(self) -> None:
        """The gate is real here too, not only in what this template gives away."""
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout


class TestPureHelpers:
    @pytest.mark.parametrize(
        ("entrypoint", "expected"),
        [
            ("pkg.app:app", ("src/pkg/app.py", "src/pkg/app/__init__.py")),
            ("pkg.web.api:app", ("src/pkg/web/api.py", "src/pkg/web/api/__init__.py")),
        ],
    )
    def test_module_paths(self, entrypoint: str, expected: tuple[str, str]) -> None:
        module = entrypoint.split(":", 1)[0]
        assert reconcile.module_relpaths(module, src_layout=True) == expected

    def test_a_flat_layout_is_not_assumed_to_be_src(self) -> None:
        assert reconcile.module_relpaths("pkg.app", src_layout=False) == (
            "pkg/app.py",
            "pkg/app/__init__.py",
        )

    @pytest.mark.parametrize("bad", ["", "not-an-entrypoint", "pkg.app", ":app"])
    def test_an_unparseable_entrypoint_is_never_treated_as_proved(
        self, tmp_path: Path, bad: str
    ) -> None:
        assert not reconcile.entrypoint_is_materialized(tmp_path, bad, src_layout=True)

    def test_a_capability_with_no_declared_evidence_is_unconditional(self, tmp_path: Path) -> None:
        assert reconcile.unsupported_capabilities(tmp_path, ["verify"], {}) == []
