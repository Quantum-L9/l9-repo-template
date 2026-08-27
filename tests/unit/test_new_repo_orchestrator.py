"""Unit tests for the birth orchestrator's decision logic.

Everything here runs without git, gh, uv, or a network: these are the pure
functions that decide whether a birth may proceed, and they are exactly the
ones whose failure would be discovered only after a repository already exists.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
# scripts/birth-runner is not an importable package name, so load by path. The
# module must be in sys.modules *before* exec_module: @dataclass resolves
# annotations through sys.modules[cls.__module__].
_SPEC = importlib.util.spec_from_file_location(
    "l9_birth_new_repo", REPO / "scripts" / "birth-runner" / "new_repo.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
new_repo = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = new_repo
_SPEC.loader.exec_module(new_repo)

# The template's own DENY_CI_DISTRIBUTION, transcribed. A class that stops
# forbidding one of these while inventory_check still denies it recreates the
# exact contradiction the birth profile exists to remove.
DENIED_BY_INVENTORY = (
    ".github/workflows/l9-analysis.yml",
    ".github/workflows/l9-lint-test.yml",
    ".github/workflows/on-org-update.yml",
    ".github/workflows/governance.yml",
    ".github/governance",
)

MINIMAL_POLICY = json.dumps(
    {
        "schema": "l9.org-birth-profile/v1",
        "default_class": "default",
        "marker_path": ".l9/org-birth-profile.yaml",
        "classes": {
            "default": {"seed_categories": ["codeowners"]},
            "non_constellation_python": {
                "seed_categories": ["codeowners"],
                "inherit": ["CODE_OF_CONDUCT.md"],
                "forbid": [".github/workflows/governance.yml", ".github/governance/**"],
            },
        },
    }
)


class TestIdentityValidation:
    @pytest.mark.parametrize(
        "name", ["l9-observability-core", "Repo.Name", "a", "l9_repo_template"]
    )
    def test_accepts_valid_repo_names(self, name: str) -> None:
        assert new_repo.validate_repo_name(name) == name

    @pytest.mark.parametrize("name", ["", "  ", "-leading", "has space", "repo.git", "a" * 101])
    def test_rejects_invalid_repo_names(self, name: str) -> None:
        with pytest.raises(new_repo.BirthError):
            new_repo.validate_repo_name(name)

    @pytest.mark.parametrize("pkg", ["l9_observability_core", "obs", "a1_b2"])
    def test_accepts_valid_package_names(self, pkg: str) -> None:
        assert new_repo.validate_package_name(pkg) == pkg

    @pytest.mark.parametrize(
        "pkg", ["", "L9Obs", "9lives", "has-dash", "has space", "l9_example_pkg"]
    )
    def test_rejects_invalid_package_names(self, pkg: str) -> None:
        with pytest.raises(new_repo.BirthError):
            new_repo.validate_package_name(pkg)

    def test_rejects_placeholder_description(self) -> None:
        with pytest.raises(new_repo.BirthError):
            new_repo.validate_description("CHANGE_ME — one-line description")

    def test_requires_description(self) -> None:
        with pytest.raises(new_repo.BirthError):
            new_repo.validate_description("   ")


class TestOrgPolicyParsing:
    def test_strips_full_line_comments(self) -> None:
        doc = new_repo.parse_json_in_yaml("# a comment\n" + MINIMAL_POLICY)
        assert set(doc["classes"]) == {"default", "non_constellation_python"}

    def test_preserves_hash_inside_strings(self) -> None:
        doc = new_repo.parse_json_in_yaml('{"classes": {"x": {}}, "note": "a#b"}')
        assert doc["note"] == "a#b"

    @pytest.mark.parametrize("text", ["", "   ", "not json", '{"no": "classes"}'])
    def test_rejects_unusable_policy(self, text: str) -> None:
        with pytest.raises(new_repo.BirthError):
            new_repo.parse_json_in_yaml(text)

    def test_unknown_class_stops_the_birth(self) -> None:
        # A sweep falls back to default; a birth must not. A typo that silently
        # widens what a repository receives is discovered after it exists.
        doc = new_repo.parse_json_in_yaml(MINIMAL_POLICY)
        with pytest.raises(new_repo.BirthError, match="unknown repo class"):
            new_repo.resolve_profile(doc, "typo_class")

    def test_resolves_declared_class(self) -> None:
        doc = new_repo.parse_json_in_yaml(MINIMAL_POLICY)
        profile = new_repo.resolve_profile(doc, "non_constellation_python")
        assert profile["name"] == "non_constellation_python"
        assert ".github/workflows/governance.yml" in profile["forbid"]


class TestPatternMatching:
    def test_exact_path(self) -> None:
        assert new_repo.match_pattern(["a/b"], "a/b") == "a/b"
        assert new_repo.match_pattern(["a/b"], "a/bc") is None

    def test_directory_prefix(self) -> None:
        assert new_repo.match_pattern(["a/**"], "a/b/c") == "a/**"
        assert new_repo.match_pattern(["a/**"], "ab/c") is None

    def test_empty_inputs(self) -> None:
        assert new_repo.match_pattern([], "a") is None
        assert new_repo.match_pattern(["", "a"], "a") == "a"


class TestForbidEnforcement:
    def test_detects_a_forbidden_file(self, tmp_path: Path) -> None:
        profile = {"forbid": [".github/workflows/governance.yml"]}
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / ".github" / "workflows" / "governance.yml").write_text("x", encoding="utf-8")
        assert new_repo.forbidden_present(tmp_path, profile) == [".github/workflows/governance.yml"]

    def test_detects_a_forbidden_directory(self, tmp_path: Path) -> None:
        profile = {"forbid": [".github/governance/**"]}
        (tmp_path / ".github" / "governance").mkdir(parents=True)
        assert new_repo.forbidden_present(tmp_path, profile) == [".github/governance/**"]

    def test_clean_tree_reports_nothing(self, tmp_path: Path) -> None:
        profile = {"forbid": [".github/workflows/governance.yml", ".github/governance/**"]}
        assert new_repo.forbidden_present(tmp_path, profile) == []

    def test_template_tree_is_clean_under_its_own_class(self) -> None:
        # The template must satisfy the class it declares. If it did not, every
        # repository born from it would inherit the violation.
        profile = {"forbid": list(DENIED_BY_INVENTORY)}
        assert new_repo.forbidden_present(REPO, profile) == []


class TestMarker:
    def test_rendered_marker_round_trips(self) -> None:
        text = new_repo.render_marker(
            profile_name="non_constellation_python",
            repository="Quantum-L9/l9-observability-core",
            template_sha="a" * 40,
            org_profile_sha="b" * 40,
            born_at="2026-08-26T00:00:00+00:00",
        )
        assert new_repo.parse_marker_profile(text) == "non_constellation_python"
        assert "a" * 40 in text
        assert "b" * 40 in text

    def test_committed_marker_declares_the_expected_class(self) -> None:
        text = (REPO / ".l9" / "org-birth-profile.yaml").read_text(encoding="utf-8")
        assert new_repo.parse_marker_profile(text) == new_repo.BIRTH_PROFILE_CLASS

    @pytest.mark.parametrize("text", [None, "", "no profile key", "  profile: indented"])
    def test_unparseable_marker_is_none(self, text: str | None) -> None:
        assert new_repo.parse_marker_profile(text) is None


class TestReceipt:
    def _receipt(self) -> object:
        receipt = new_repo.BirthReceipt(
            org="Quantum-L9",
            repository="l9-observability-core",
            package="l9_observability_core",
            birth_profile="non_constellation_python",
            template_sha="a" * 40,
            org_profile_sha="b" * 40,
        )
        receipt.record("preflight.tools", "tools", "PASS")
        receipt.record("validate.lock", "lock", "PASS")
        return receipt

    def test_renders_grouped_stages(self) -> None:
        out = new_repo.render_receipt(self._receipt())
        assert "L9 REPOSITORY BIRTH" in out
        assert "Preflight" in out
        assert "Validation" in out
        assert "BIRTH: PASS" in out

    def test_a_failed_stage_fails_the_birth(self) -> None:
        receipt = self._receipt()
        receipt.record("validate.tests", "tests", "FAIL", "1 failed")
        assert receipt.failed
        assert "BIRTH: FAIL" in new_repo.render_receipt(receipt)
        assert receipt.to_dict()["result"] == "FAIL"

    def test_receipt_json_carries_both_provenance_shas(self) -> None:
        payload = self._receipt().to_dict()
        assert payload["template"]["sha"] == "a" * 40
        assert payload["organization"]["sha"] == "b" * 40
        assert payload["organization"]["birth_profile"] == "non_constellation_python"


class TestCopyExclusions:
    @pytest.mark.parametrize(
        "rel",
        [
            ".git/config",
            ".venv/bin/python",
            "src/l9_example_pkg.egg-info/PKG-INFO",
            "src/__pycache__/x.pyc",
        ],
    )
    def test_machine_state_is_never_born(self, rel: str) -> None:
        assert new_repo._is_machine_state(Path(rel))

    @pytest.mark.parametrize("rel", ["src/pkg/app.py", "README.md", ".github/CODEOWNERS"])
    def test_real_content_is_carried(self, rel: str) -> None:
        assert not new_repo._is_machine_state(Path(rel))


class TestMaterializeOrgPayload:
    """MATERIALIZE writes the applicable org files BEFORE the initial commit.

    A repository that is "born, then offered an org patch" is born incomplete.
    These assert the write/keep semantics directly, because a real birth
    against the current template writes nothing — the template already ships
    all three dests, so the happy path exercises only the keep branch.
    """

    def test_writes_missing_files(self, tmp_path: Path) -> None:
        written, kept = new_repo.materialize_org_payload(
            tmp_path,
            {".github/CODEOWNERS": "* @team\n", ".github/labels.yml": "labels: []\n"},
        )
        assert written == [".github/CODEOWNERS", ".github/labels.yml"]
        assert kept == []
        assert (tmp_path / ".github" / "CODEOWNERS").read_text(encoding="utf-8") == "* @team\n"

    def test_never_overwrites_what_the_repo_already_has(self, tmp_path: Path) -> None:
        # Missing-only, matching the seeder: the template and the product
        # payload are closer to the repository than the org default is.
        (tmp_path / ".github").mkdir()
        (tmp_path / ".github" / "CODEOWNERS").write_text("mine\n", encoding="utf-8")
        written, kept = new_repo.materialize_org_payload(tmp_path, {".github/CODEOWNERS": "org\n"})
        assert written == []
        assert kept == [".github/CODEOWNERS"]
        assert (tmp_path / ".github" / "CODEOWNERS").read_text(encoding="utf-8") == "mine\n"

    def test_empty_payload_is_a_no_op(self, tmp_path: Path) -> None:
        assert new_repo.materialize_org_payload(tmp_path, {}) == ([], [])


class TestInheritedPresent:
    def test_reports_a_repo_local_copy_of_an_inherited_file(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_OF_CONDUCT.md").write_text("x", encoding="utf-8")
        profile = {"inherit": ["CODE_OF_CONDUCT.md", ".github/ISSUE_TEMPLATE/**"]}
        assert new_repo.inherited_present(tmp_path, profile) == ["CODE_OF_CONDUCT.md"]

    def test_reports_a_directory_pattern(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
        profile = {"inherit": [".github/ISSUE_TEMPLATE/**"]}
        assert new_repo.inherited_present(tmp_path, profile) == [".github/ISSUE_TEMPLATE/**"]

    def test_clean_tree_reports_nothing(self, tmp_path: Path) -> None:
        assert new_repo.inherited_present(tmp_path, {"inherit": ["CODE_OF_CONDUCT.md"]}) == []


class TestLicenceIsNotRepositoryPoisoned:
    """A licence naming one repository is wrong in every other repository.

    The birth engine copies the template LICENSE into every newborn as
    canonical, so this is the one defect a factory would reproduce perfectly,
    forever, without anyone noticing.
    """

    def test_template_licence_is_generic(self) -> None:
        text = (REPO / "LICENSE").read_text(encoding="utf-8")
        assert new_repo.POISONED_LICENSE_NOTICE not in text
        assert "QUANTUM AI PARTNERS" in text

    def test_the_poisoned_notice_is_what_birth_refuses(self) -> None:
        assert new_repo.POISONED_LICENSE_NOTICE == (
            "applies only to the Quantum-L9/.github repository"
        )


class TestDefaultWorkDir:
    def test_is_not_a_predictable_world_writable_tmp_path(self) -> None:
        # A fixed /tmp path lets any local user pre-create <workdir>/<repo> —
        # as a symlink, or with their own contents — before the birth runs.
        root = new_repo.default_work_dir()
        assert not str(root).startswith("/tmp/")
        assert root.is_dir()

    def test_is_private_to_the_owner(self) -> None:
        import stat

        mode = new_repo.default_work_dir().stat().st_mode
        assert not mode & stat.S_IRWXG
        assert not mode & stat.S_IRWXO


class TestAuthPreflightUsesRest:
    """`gh auth status` is not authoritative on a GraphQL-restricted surface.

    The session gateway serves REST and refuses GraphQL; `gh auth status`
    verifies over GraphQL, so it reports "The token in GH_TOKEN is invalid"
    while every REST call the birth makes succeeds. Gating on it failed a birth
    that would have worked.
    """

    def test_preflight_does_not_shell_to_gh_auth_status(self) -> None:
        # Assert on the argv literal, not on prose: the comment above the fix
        # names `gh auth status` deliberately, to say why it is not used.
        source = (REPO / "scripts" / "birth-runner" / "new_repo.py").read_text(encoding="utf-8")
        assert '"auth", "status"' not in source

    def test_preflight_probes_rest_instead(self) -> None:
        source = (REPO / "scripts" / "birth-runner" / "new_repo.py").read_text(encoding="utf-8")
        assert '["gh", "api", "user", "--jq", ".login"]' in source


class TestPayloadOwnershipContract:
    """The template's declaration of what a product inherits from it."""

    def test_template_ships_a_loadable_contract(self) -> None:
        doc = new_repo.load_ownership(REPO)
        assert doc["schema"] == "l9.birth-payload-ownership/v1"
        assert doc["repository_shape"]
        assert doc["product"]
        assert doc["chassis"]

    def test_a_missing_contract_stops_the_birth(self, tmp_path: Path) -> None:
        # Fail closed. Falling back to "the template owns everything" is the
        # defect this contract removes.
        with pytest.raises(new_repo.BirthError):
            new_repo.load_ownership(tmp_path)

    @pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '{"product": []}'])
    def test_an_unusable_contract_stops_the_birth(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / new_repo.OWNERSHIP_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        with pytest.raises(new_repo.BirthError):
            new_repo.load_ownership(tmp_path)

    def test_every_template_path_is_classified(self) -> None:
        """No surface may be silently template-owned.

        Adding a file to this template forces an answer to "does a product
        inherit this?" — the question the additive-only overlay never asked.
        """
        doc = new_repo.load_ownership(REPO)
        declared = list(doc["product"]) + list(doc["chassis"])
        tracked = subprocess.run(
            ["git", "-C", str(REPO), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        unclassified = [rel for rel in tracked if new_repo.match_pattern(declared, rel) is None]
        assert unclassified == [], f"unclassified template surfaces: {unclassified}"

    @pytest.mark.parametrize(
        "rel",
        [
            "Dockerfile",
            "docker-compose.yml",
            "observability/docker-compose.observability.yml",
            "src/l9_example_pkg/app.py",
            "src/l9_example_pkg/health.py",
            "src/l9_example_pkg/protocols.py",
            "src/l9_example_pkg/retry.py",
            "src/l9_example_pkg/settings.py",
            "tests/integration/test_app_http.py",
            "docs/examples/observability/prometheus_slo_alerts.example.yml",
        ],
    )
    def test_example_product_surfaces_are_product_owned(self, rel: str) -> None:
        doc = new_repo.load_ownership(REPO)
        assert new_repo.match_pattern(doc["product"], rel) is not None

    @pytest.mark.parametrize(
        "rel",
        [
            "Makefile",
            "Repo.mk",
            "LICENSE",
            "tools/l9_repo/__main__.py",
            "scripts/birth-runner/new_repo.py",
            "scripts/inventory_check.py",
            "scripts/render_cursor_rules.py",
            ".l9/org-birth-profile.yaml",
            ".cursor/rules/templates/l9-python-repo.mdc.template",
        ],
    )
    def test_chassis_surfaces_are_never_product_owned(self, rel: str) -> None:
        doc = new_repo.load_ownership(REPO)
        assert new_repo.match_pattern(doc["product"], rel) is None


def _repository_payload(root: Path, pkg: str = "l9_product") -> Path:
    """A minimal standalone repository payload — the shape, not a real product."""
    for rel, body in {
        "pyproject.toml": '[project]\nname = "l9-product"\n',
        ".l9/architecture.yaml": "schema: l9.architecture-spec/v1\n",
        f"src/{pkg}/__init__.py": '"""product"""\n',
        f"src/{pkg}/canonical.py": "VALUE = 1\n",
        "tests/test_canonical.py": "def test_ok() -> None:\n    assert True\n",
        "scripts/inventory_check.py": "raise SystemExit(0)\n",
    }.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return root


class TestRepositoryPayloadDetection:
    def test_a_standalone_repository_is_identified(self, tmp_path: Path) -> None:
        payload = _repository_payload(tmp_path / "payload")
        assert new_repo.is_repository_payload(payload, new_repo.load_ownership(REPO))

    @pytest.mark.parametrize("drop", ["pyproject.toml", ".l9/architecture.yaml", "src", "tests"])
    def test_a_fragment_is_not(self, tmp_path: Path, drop: str) -> None:
        payload = _repository_payload(tmp_path / "payload")
        target = payload / drop
        shutil.rmtree(target) if target.is_dir() else target.unlink()
        assert not new_repo.is_repository_payload(payload, new_repo.load_ownership(REPO))

    def test_a_payload_carrying_only_src_is_still_additive(self, tmp_path: Path) -> None:
        # The pre-existing partial-overlay contract. Products depend on it.
        payload = tmp_path / "payload"
        (payload / "src" / "l9_product").mkdir(parents=True)
        (payload / "src" / "l9_product" / "__init__.py").write_text("", encoding="utf-8")
        assert not new_repo.is_repository_payload(payload, new_repo.load_ownership(REPO))


class TestReconcileProductOwnership:
    """Absence in an authoritative payload is meaningful."""

    @staticmethod
    def _assembled(root: Path, pkg: str = "l9_product") -> Path:
        for rel in (
            "Dockerfile",
            "docker-compose.yml",
            ".dockerignore",
            ".env.example",
            "observability/docker-compose.observability.yml",
            "observability/grafana/provisioning/dashboards/dashboards.yaml",
            "docs/examples/coderabbit.yaml",
            f"src/{pkg}/__init__.py",
            f"src/{pkg}/app.py",
            f"src/{pkg}/health.py",
            f"src/{pkg}/protocols.py",
            f"src/{pkg}/retry.py",
            f"src/{pkg}/settings.py",
            "tests/integration/test_app_http.py",
            "Makefile",
            "Repo.mk",
            "LICENSE",
            "docs/LIFECYCLE.md",
            "scripts/render_cursor_rules.py",
            "tools/l9_repo/__main__.py",
            ".l9/org-birth-profile.yaml",
        ):
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("template\n", encoding="utf-8")
        return root

    def test_unsupplied_product_surfaces_are_removed(self, tmp_path: Path) -> None:
        dest = self._assembled(tmp_path / "dest")
        payload = _repository_payload(tmp_path / "payload")
        removed = new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        for rel in ("Dockerfile", "docker-compose.yml", "src/l9_product/app.py"):
            assert rel in removed
            assert not (dest / rel).exists()
        assert not (dest / "observability").exists()

    def test_the_payload_package_replaces_the_template_package(self, tmp_path: Path) -> None:
        dest = self._assembled(tmp_path / "dest")
        payload = _repository_payload(tmp_path / "payload")
        new_repo.overlay_payload(payload, dest)
        new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        assert sorted(p.name for p in (dest / "src" / "l9_product").iterdir()) == [
            "__init__.py",
            "canonical.py",
        ]

    def test_chassis_and_org_surfaces_survive(self, tmp_path: Path) -> None:
        dest = self._assembled(tmp_path / "dest")
        payload = _repository_payload(tmp_path / "payload")
        new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        for rel in (
            "Makefile",
            "Repo.mk",
            "LICENSE",
            "docs/LIFECYCLE.md",
            "scripts/render_cursor_rules.py",
            "tools/l9_repo/__main__.py",
            ".l9/org-birth-profile.yaml",
        ):
            assert (dest / rel).is_file(), f"reconciliation removed chassis surface {rel}"

    def test_a_supplied_product_surface_is_kept(self, tmp_path: Path) -> None:
        dest = self._assembled(tmp_path / "dest")
        payload = _repository_payload(tmp_path / "payload")
        (payload / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        new_repo.overlay_payload(payload, dest)
        removed = new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        assert "Dockerfile" not in removed
        assert (dest / "Dockerfile").read_text(encoding="utf-8") == "FROM scratch\n"

    def test_a_directory_empty_before_the_birth_is_left_alone(self, tmp_path: Path) -> None:
        """Only directories reconciliation itself emptied are pruned."""
        dest = self._assembled(tmp_path / "dest")
        (dest / "docs" / "adr").mkdir(parents=True)
        payload = _repository_payload(tmp_path / "payload")
        new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        assert (dest / "docs" / "adr").is_dir()

    def test_git_state_is_never_touched(self, tmp_path: Path) -> None:
        dest = self._assembled(tmp_path / "dest")
        (dest / ".git" / "objects").mkdir(parents=True)
        (dest / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        payload = _repository_payload(tmp_path / "payload")
        new_repo.reconcile_product_ownership(dest, payload, new_repo.load_ownership(REPO))
        assert (dest / ".git" / "HEAD").is_file()
        assert (dest / ".git" / "objects").is_dir()


class TestPayloadPackageDirs:
    def test_lists_the_packages_a_payload_ships(self, tmp_path: Path) -> None:
        payload = _repository_payload(tmp_path / "payload", pkg="l9_observability_core")
        assert new_repo.payload_package_dirs(payload) == ["l9_observability_core"]

    def test_a_payload_without_src_lists_nothing(self, tmp_path: Path) -> None:
        assert new_repo.payload_package_dirs(tmp_path) == []
