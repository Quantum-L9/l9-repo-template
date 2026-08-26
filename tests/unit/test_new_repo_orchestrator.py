"""Unit tests for the birth orchestrator's decision logic.

Everything here runs without git, gh, uv, or a network: these are the pure
functions that decide whether a birth may proceed, and they are exactly the
ones whose failure would be discovered only after a repository already exists.
"""

from __future__ import annotations

import importlib.util
import json
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
