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
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
# scripts/birth-runner is not an importable package name, so load by path. The
# module must be in sys.modules *before* exec_module: @dataclass resolves
# annotations through sys.modules[cls.__module__].
_SPEC = importlib.util.spec_from_file_location("l9_birth_new_repo", BIRTH_RUNNER / "new_repo.py")
assert _SPEC is not None
assert _SPEC.loader is not None
new_repo = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = new_repo
_SPEC.loader.exec_module(new_repo)
# The engine locates its provenance module relative to its own file, so reading
# it back off the loaded engine is what guarantees the test and the birth are
# talking about the same module rather than two copies that agree for now.
prov = new_repo.prov

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
            template_version="2.1.0",
            org_profile_sha="b" * 40,
            born_at="2026-08-26T00:00:00+00:00",
        )
        assert new_repo.parse_marker_profile(text) == "non_constellation_python"
        assert "a" * 40 in text
        assert "b" * 40 in text

    def test_the_org_contract_keys_stay_flat(self) -> None:
        """Quantum-L9/.github parses this file with one regex on `profile:`.

        Birth provenance is an additive nested block; the three keys the
        organization's contract names must stay at the top level or an org-wide
        sweep silently resolves every born repository to the default class.
        """
        text = new_repo.render_marker(
            profile_name="non_constellation_python",
            repository="Quantum-L9/x",
            template_sha="a" * 40,
            template_version="2.1.0",
            org_profile_sha="b" * 40,
            born_at="2026-08-26T00:00:00+00:00",
        )
        doc = prov.parse_flat_yaml(text)
        assert doc["schema"] == prov.MARKER_SCHEMA
        assert doc["profile"] == "non_constellation_python"
        assert doc["authority"] == "Quantum-L9/.github"

    def test_provenance_lives_under_the_birth_block(self) -> None:
        text = new_repo.render_marker(
            profile_name="non_constellation_python",
            repository="Quantum-L9/x",
            template_sha="a" * 40,
            template_version="2.1.0",
            org_profile_sha="b" * 40,
            born_at="2026-08-26T00:00:00+00:00",
        )
        birth = prov.birth_block(text)
        assert birth["template_sha"] == "a" * 40
        assert birth["template_version"] == "2.1.0"
        assert birth["org_policy_sha"] == "b" * 40
        assert birth["born_at"] == "2026-08-26T00:00:00+00:00"

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


class TestBirthNormalisesBeforeItAttests:
    """Formatting is a birth invariant, and the receipt records what changed.

    An assembled tree is template plus payload, written by two parties that
    never agreed on import order. A mechanically fixable diff between them was
    destroying whole births over whitespace.
    """

    def test_the_detail_names_what_ruff_changed(self) -> None:
        detail = new_repo._autofix_detail(
            "Found 20 errors (20 fixed, 0 remaining).\nFixed 20 errors.",
            "12 files reformatted, 123 files left unchanged",
        )
        assert "20 lint fix(es)" in detail
        assert "12 file(s) reformatted" in detail

    def test_the_counters_are_anchored_and_bounded(self) -> None:
        """An unanchored leading `\\d+` is retried at every offset of the output.

        That is quadratic in the length of a run's stdout rather than linear
        (Sonar python:S8786), and ruff prints each counter on its own line, so
        anchoring costs nothing. Asserted because the cheap spelling is the one
        a later edit reaches for.
        """
        assert new_repo._REFORMATTED_RE.pattern.startswith("^")
        assert new_repo._FIXED_RE.pattern.startswith("^")
        assert "\\d+" not in new_repo._REFORMATTED_RE.pattern
        assert "\\d+" not in new_repo._FIXED_RE.pattern

    def test_a_counter_mid_line_is_not_mistaken_for_the_summary(self) -> None:
        # Anchoring is what stops "...left 12 files reformatted" in some other
        # sentence from being read as ruff's own count.
        assert new_repo._autofix_detail("", "note: it left 12 files reformatted") == "already clean"

    def test_a_clean_payload_says_so_rather_than_nothing(self) -> None:
        # A blank detail reads as "the step did not run". It ran; it found none.
        assert new_repo._autofix_detail("All checks passed!", "5 files left unchanged") == (
            "already clean"
        )

    def test_autofix_runs_before_the_manifest_and_the_stamp(self) -> None:
        """Order is the whole point, so it is asserted rather than assumed.

        The manifest digest, the version stamp and the receipt digest all
        describe the newborn's bytes. Fixing after any of them would leave the
        root commit's own attestation describing a tree that no longer exists.
        """
        source = Path(new_repo.__file__).read_text(encoding="utf-8")
        autofix = source.index('"finalize.autofix"')
        manifest = source.index('"finalize.manifest"')
        assert autofix < manifest

    def test_the_fix_stays_safe_and_the_gate_stays_closed(self) -> None:
        """`--unsafe-fixes` would let birth rewrite semantics, not whitespace.

        And stage 5 must still *check* after the fix: without that, a lint error
        ruff cannot fix would sail into a published repository.
        """
        source = Path(new_repo.__file__).read_text(encoding="utf-8")
        # The quoted form is the argument; the bare word appears in the comment
        # explaining why it is not passed, so matching that would be self-tripping.
        assert '"--unsafe-fixes"' not in source
        assert '("validate.lint", "lint", [str(python), "-m", "ruff", "check", "."])' in source
        assert (
            '("validate.format", "format", [str(python), "-m", "ruff", "format", "--check", "."])'
            in source
        )


class TestSessionScaffoldingIsNeverBorn:
    """Agent session bootstrap is this machine's, not the template's.

    `.claude/` carries symlinks into the governance clone at an absolute machine
    path plus a copy of the governance command/skill library, and `.mcp.json` is
    0600 environment configuration. Copied into a newborn they are staged by
    `git add -A` and land in the ROOT COMMIT — the one commit that is supposed
    to be attestable provenance and nothing else.
    """

    @pytest.mark.parametrize(
        "rel",
        [
            ".claude/settings.json",
            ".claude/rules",
            ".claude/skills/l9-plan/SKILL.md",
            ".mcp.json",
        ],
    )
    def test_the_template_copy_drops_it(self, rel: str) -> None:
        assert new_repo._is_session_scaffolding(Path(rel))

    @pytest.mark.parametrize("rel", ["src/pkg/app.py", ".github/CODEOWNERS", "docs/x.md"])
    def test_template_content_is_untouched(self, rel: str) -> None:
        assert not new_repo._is_session_scaffolding(Path(rel))

    def test_the_birth_dispatch_workflow_is_not_inherited(self) -> None:
        """A newborn is a product, not a second factory.

        `.github/**` is `chassis`, so CODEOWNERS, labels and dependabot ARE
        inherited. The birth dispatch workflow must not be: it mints an
        organisation-Administration token, and a newborn carrying it is inert
        only for as long as nobody creates a `repo-birth` environment there.
        """
        assert new_repo._is_session_scaffolding(Path(".github/workflows/repo-birth-dispatch.yml"))

    def test_copy_tree_keeps_github_but_drops_the_dispatch_workflow(self, tmp_path: Path) -> None:
        # The exclusion is one file, not the directory. Proving both halves in
        # one copy is what stops a future widening from passing silently.
        src = tmp_path / "template"
        (src / ".github" / "workflows").mkdir(parents=True)
        (src / ".github" / "CODEOWNERS").write_text("* @owner\n", encoding="utf-8")
        (src / ".github" / "workflows" / "repo-birth-dispatch.yml").write_text(
            "name: x\n", encoding="utf-8"
        )
        dest = tmp_path / "newborn"
        dest.mkdir()
        new_repo.copy_tree(src, dest)
        assert (dest / ".github" / "CODEOWNERS").is_file()
        assert not (dest / ".github" / "workflows" / "repo-birth-dispatch.yml").exists()

    def test_copy_tree_leaves_it_behind(self, tmp_path: Path) -> None:
        src = tmp_path / "template"
        (src / ".claude" / "hooks").mkdir(parents=True)
        (src / ".claude" / "hooks" / "wrap.py").write_text("", encoding="utf-8")
        (src / ".mcp.json").write_text("{}", encoding="utf-8")
        (src / "README.md").write_text("# t\n", encoding="utf-8")
        dest = tmp_path / "newborn"
        dest.mkdir()
        new_repo.copy_tree(src, dest)
        assert (dest / "README.md").is_file()
        assert not (dest / ".claude").exists()
        assert not (dest / ".mcp.json").exists()

    def test_a_payload_may_still_own_its_own_claude_config(self, tmp_path: Path) -> None:
        # The exclusion is about THIS machine's scaffolding, not about forbidding
        # a product from shipping Claude configuration it actually wrote.
        payload = tmp_path / "payload"
        (payload / ".claude").mkdir(parents=True)
        (payload / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        dest = tmp_path / "dest"
        dest.mkdir()
        assert new_repo.overlay_payload(payload, dest) == [".claude/settings.json"]

    def test_the_template_gitignores_it_for_the_newborn(self) -> None:
        # copy_tree keeps it out of the assembled tree; .gitignore keeps it out
        # of the commit when the bootstrap later runs INSIDE a born repository.
        ignored = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert "/.claude/" in ignored
        assert "/.mcp.json" in ignored


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


class TestAnAuthoritativePayloadMustBeCompiled:
    """The classification a birth acts on is verified, never inferred.

    Repository shape used to be read off a directory during assembly, so the
    decision that DELETES product surfaces was taken while files were already
    being copied. Now the compiler proposes it from an immutable snapshot and
    the engine verifies it — which means a repository-shaped directory with no
    compiled payload is a refusal.
    """

    @staticmethod
    def _config(tmp_path: Path, payload: Path, contract: Path | None = None) -> object:
        argv = [
            "--repo",
            "l9-newborn",
            "--pkg",
            "l9_newborn",
            "--desc",
            "A product",
            "--work-dir",
            str(tmp_path / "work"),
            "--payload",
            str(payload),
            "--no-remote",
        ]
        if contract is not None:
            argv += ["--payload-contract", str(contract)]
        return new_repo.build_config(new_repo.parse_args(argv))

    def test_a_repository_shaped_directory_without_a_contract_is_refused(
        self, tmp_path: Path
    ) -> None:
        payload = tmp_path / "payload"
        for rel in new_repo.load_ownership(REPO)["repository_shape"]:
            (payload / rel).mkdir(parents=True, exist_ok=True)
        cfg = self._config(tmp_path, payload)
        with pytest.raises(new_repo.BirthError) as exc:
            new_repo._preflight_payload_contract(cfg, new_repo.BirthReceipt())
        assert "repository-shaped" in str(exc.value)
        assert "make birth-payload" in str(exc.value)

    def test_a_fragment_still_needs_no_contract(self, tmp_path: Path) -> None:
        """The pre-existing additive contract, unchanged. Products depend on it."""
        payload = tmp_path / "payload" / "src" / "l9_newborn"
        payload.mkdir(parents=True)
        (payload / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
        cfg = self._config(tmp_path, tmp_path / "payload")
        receipt = new_repo.BirthReceipt()
        new_repo._preflight_payload_contract(cfg, receipt)
        assert cfg.verified_payload_mode == "additive"
        assert receipt.stages[-1].status == "SKIP"

    def test_no_payload_is_not_a_payload_decision(self, tmp_path: Path) -> None:
        cfg = new_repo.build_config(
            new_repo.parse_args(
                [
                    "--repo",
                    "l9-newborn",
                    "--pkg",
                    "l9_newborn",
                    "--desc",
                    "A product",
                    "--work-dir",
                    str(tmp_path / "work"),
                    "--no-remote",
                ]
            )
        )
        receipt = new_repo.BirthReceipt()
        new_repo._preflight_payload_contract(cfg, receipt)
        assert cfg.verified_payload_mode is None
        assert receipt.stages[-1].detail == "no PAYLOAD given"

    def test_a_contract_without_a_payload_is_a_mistake(self, tmp_path: Path) -> None:
        """A compiled payload authorizes bytes; it does not carry them."""
        argv = new_repo.parse_args(
            [
                "--repo",
                "l9-newborn",
                "--pkg",
                "l9_newborn",
                "--desc",
                "A product",
                "--work-dir",
                str(tmp_path / "work"),
                "--payload-contract",
                str(tmp_path / "payload.json"),
                "--no-remote",
            ]
        )
        with pytest.raises(new_repo.BirthError, match="without a PAYLOAD"):
            new_repo.build_config(argv)


class TestOneOwnershipContractReader:
    """The engine and the compiler must not hold two readings of one contract."""

    def test_the_engine_delegates_to_the_shared_reader(self) -> None:
        assert new_repo.is_repository_payload is new_repo.ownership_contract.is_repository_payload
        assert new_repo.payload_package_dirs is new_repo.ownership_contract.payload_package_dirs
        assert new_repo.OWNERSHIP_PATH == new_repo.ownership_contract.OWNERSHIP_PATH

    def test_an_unreadable_contract_still_stops_the_birth_here(self, tmp_path: Path) -> None:
        """Delegation must not turn a fail-closed read into an unhandled error."""
        with pytest.raises(new_repo.BirthError):
            new_repo.load_ownership(tmp_path)


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


# ─────────────────────────────────────────────────────────────────────────────
# Canonical CI enrolment — the ruleset listing is a summary
# ─────────────────────────────────────────────────────────────────────────────

CORE_ID = new_repo.canonical_ci.CI_AUTHORITY_REPOSITORY_ID
ORG_CI = new_repo.canonical_ci.CI_AUTHORITY_WORKFLOW
CANON_REF = new_repo.canonical_ci.CI_AUTHORITY_REF
SLUG = "Quantum-L9/l9-observability-core"

LIST_ENDPOINT = f"repos/{SLUG}/rulesets?includes_parents=true"
DETAIL_ENDPOINT = f"repos/{SLUG}/rulesets/42?includes_parents=true"


def _ruleset_summary() -> dict:
    """As the LIST endpoint returns it: named and sourced, but carrying no rules."""
    return {
        "id": 42,
        "name": "L9 canonical CI required",
        "source_type": "Organization",
        "enforcement": "active",
    }


def _ruleset_detail(**over: object) -> dict:
    """As the DETAIL endpoint returns it: the rules the listing omits."""
    base = dict(_ruleset_summary())
    base["rules"] = [
        {
            "type": "workflows",
            "parameters": {
                "do_not_enforce_on_create": True,
                "workflows": [
                    {"path": ORG_CI, "ref": CANON_REF, "repository_id": CORE_ID, "sha": "d" * 40}
                ],
            },
        }
    ]
    base.update(over)
    return base


class _Gh:
    """A `gh api` boundary. Anything not answered here exits non-zero."""

    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.endpoints: list[str] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        endpoint = cmd[-1]
        self.endpoints.append(endpoint)
        if endpoint not in self.responses:
            return subprocess.CompletedProcess(cmd, 1, "", "gh: Not Found (HTTP 404)")
        return subprocess.CompletedProcess(cmd, 0, json.dumps(self.responses[endpoint]), "")


def _ci_config() -> object:
    return new_repo.BirthConfig(
        org="Quantum-L9",
        repo="l9-observability-core",
        pkg="l9_observability_core",
        desc="observability",
        work_dir=Path("/nonexistent"),
        payload=None,
        payload_contract=None,
        template_src=Path("/nonexistent"),
        org_profile_src=None,
        repo_class="non_constellation_python",
        remote=True,
        private=False,
        keep=False,
        receipt_path=None,
        bootstrap_timeout=1,
    )


def _ci_receipt() -> object:
    return new_repo.BirthReceipt(
        org="Quantum-L9",
        repository="l9-observability-core",
        package="l9_observability_core",
        head_sha="e" * 40,
    )


def _verify(monkeypatch: pytest.MonkeyPatch, gh: _Gh) -> object:
    monkeypatch.setattr(new_repo, "run", gh)
    receipt = _ci_receipt()
    new_repo.stage_verify_ci_enrollment(_ci_config(), receipt)
    return receipt


def _stage(receipt: object, key: str) -> object:
    return next(s for s in receipt.stages if s.key == key)


class TestEnrollmentIsHydratedFromTheDetailEndpoint:
    """`repos/{slug}/rulesets` answers *which* rulesets, never *what they require*.

    Reading enrolment off the listing alone can only ever answer "not enrolled",
    which is how a correctly enrolled repository reads as unenrolled and every
    real birth QUARANTINEs.
    """

    def test_a_real_org_ruleset_is_recognised_as_enrolment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gh = _Gh({LIST_ENDPOINT: [_ruleset_summary()], DETAIL_ENDPOINT: _ruleset_detail()})
        receipt = _verify(monkeypatch, gh)
        assert _stage(receipt, "ci.enrollment").status == "PASS"
        assert DETAIL_ENDPOINT in gh.endpoints

    def test_enrolment_leaves_the_repository_provisional_never_born(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Enrolment is not evaluation. BORN is earned by a real pull request."""
        gh = _Gh({LIST_ENDPOINT: [_ruleset_summary()], DETAIL_ENDPOINT: _ruleset_detail()})
        receipt = _verify(monkeypatch, gh)
        assert receipt.ci["state"] == new_repo.canonical_ci.PROVISIONAL
        assert receipt.state != new_repo.canonical_ci.BORN

    def test_the_summary_alone_is_never_treated_as_enrolment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The listing is hydrated, not believed — even when it looks complete."""
        gh = _Gh({LIST_ENDPOINT: [_ruleset_detail()]})  # detail-shaped, but from the LIST
        monkeypatch.setattr(new_repo, "run", gh)
        monkeypatch.delenv(new_repo.CI_UNVERIFIED_ENV, raising=False)
        with pytest.raises(new_repo.BirthError, match="undeterminable"):
            new_repo.stage_verify_ci_enrollment(_ci_config(), _ci_receipt())


class TestUndeterminableEnrollmentFailsClosed:
    def test_an_unreadable_detail_stops_the_birth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gh = _Gh({LIST_ENDPOINT: [_ruleset_summary()]})  # detail 404s
        monkeypatch.setattr(new_repo, "run", gh)
        monkeypatch.delenv(new_repo.CI_UNVERIFIED_ENV, raising=False)
        with pytest.raises(new_repo.BirthError, match="undeterminable"):
            new_repo.stage_verify_ci_enrollment(_ci_config(), _ci_receipt())

    def test_the_breakglass_does_not_excuse_an_undeterminable_enrolment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The operator may accept a repository KNOWN to be unenrolled.

        That is a different claim from one whose enrolment nothing could read,
        so the reason is never consulted on this path.
        """
        gh = _Gh({LIST_ENDPOINT: [_ruleset_summary()]})
        monkeypatch.setattr(new_repo, "run", gh)
        monkeypatch.setenv(new_repo.CI_UNVERIFIED_ENV, "ruleset not applied yet")
        with pytest.raises(new_repo.BirthError, match="undeterminable"):
            new_repo.stage_verify_ci_enrollment(_ci_config(), _ci_receipt())

    def test_a_genuinely_absent_ruleset_is_still_breakglassable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unenrolled stays a WARN with a reason. Only undeterminable is absolute."""
        gh = _Gh({LIST_ENDPOINT: []})
        monkeypatch.setenv(new_repo.CI_UNVERIFIED_ENV, "ruleset not applied yet")
        receipt = _verify(monkeypatch, gh)
        assert _stage(receipt, "ci.enrollment").status == "WARN"

    def test_a_wrong_owner_ruleset_is_not_enrolment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The canonical path in the wrong repository is not canonical CI."""
        wrong = _ruleset_detail()
        wrong["rules"][0]["parameters"]["workflows"][0]["repository_id"] = CORE_ID + 1
        gh = _Gh({LIST_ENDPOINT: [_ruleset_summary()], DETAIL_ENDPOINT: wrong})
        monkeypatch.setattr(new_repo, "run", gh)
        monkeypatch.delenv(new_repo.CI_UNVERIFIED_ENV, raising=False)
        with pytest.raises(new_repo.BirthError, match="NOT enrolled"):
            new_repo.stage_verify_ci_enrollment(_ci_config(), _ci_receipt())
