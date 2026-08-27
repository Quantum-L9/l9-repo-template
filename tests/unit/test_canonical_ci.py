"""A repository that exists is not a repository that is born.

These tests hold the part of birth that cannot be faked by a green-looking
repository: that the accepted CI run is THIS root commit's, that a missing or
unfinished run is a failure rather than a shrug, and that a product payload
cannot quietly take the binding away.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "scripts" / "birth-runner" / "canonical_ci.py"
_SPEC = importlib.util.spec_from_file_location("l9_canonical_ci", MODULE)
assert _SPEC is not None
assert _SPEC.loader is not None
cci = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cci
_SPEC.loader.exec_module(cci)

ROOT_SHA = "a" * 40
OTHER_SHA = "b" * 40
CORE = cci.CI_AUTHORITY_REPO
ORG_CI = cci.CI_AUTHORITY_WORKFLOW
PIN = "c" * 40


def _run(**over: object) -> dict:
    base = {
        "id": 100,
        "head_sha": ROOT_SHA,
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-27T10:00:00Z",
        "html_url": "https://github.com/x/y/actions/runs/100",
    }
    base.update(over)
    return base


def _binding_yaml(uses: str) -> str:
    return f"name: L9 CI\non:\n  push:\n    branches: [main]\njobs:\n  l9-ci:\n    uses: {uses}\n"


# ─────────────────────────────────────────────────────────────────────────────
# BIRTH-CI-002 — the run must be THIS commit's
# ─────────────────────────────────────────────────────────────────────────────


class TestRunCorrelation:
    def test_the_root_commits_own_run_is_selected(self) -> None:
        assert cci.select_birth_run([_run()], root_sha=ROOT_SHA)["id"] == 100

    def test_a_run_for_another_commit_is_never_accepted(self) -> None:
        assert cci.select_birth_run([_run(head_sha=OTHER_SHA)], root_sha=ROOT_SHA) is None

    def test_a_run_on_another_branch_is_never_accepted(self) -> None:
        assert cci.select_birth_run([_run(head_branch="feature/x")], root_sha=ROOT_SHA) is None

    def test_a_stale_success_does_not_stand_in(self) -> None:
        """The failure mode this exists for: 'some run passed recently'."""
        stale = _run(id=1, head_sha=OTHER_SHA, created_at="2026-08-27T09:00:00Z")
        assert cci.select_birth_run([stale], root_sha=ROOT_SHA) is None

    def test_the_newest_matching_run_wins_a_re_run(self) -> None:
        old = _run(id=1, created_at="2026-08-27T09:00:00Z", conclusion="failure")
        new = _run(id=2, created_at="2026-08-27T11:00:00Z")
        assert cci.select_birth_run([old, new], root_sha=ROOT_SHA)["id"] == 2

    @pytest.mark.parametrize("bad", [None, "not-a-list", 42, {}])
    def test_an_unreadable_run_list_selects_nothing(self, bad: object) -> None:
        assert cci.select_birth_run(bad, root_sha=ROOT_SHA) is None

    @pytest.mark.parametrize("missing", [{}, {"head_sha": ""}, {"head_sha": "short"}])
    def test_a_run_that_names_no_commit_is_never_accepted(self, missing: dict) -> None:
        assert not cci.run_matches_root(missing, root_sha=ROOT_SHA)


# ─────────────────────────────────────────────────────────────────────────────
# BIRTH-CI-003 — only success is success
# ─────────────────────────────────────────────────────────────────────────────


class TestVerdict:
    def test_success_is_the_only_path_to_born(self) -> None:
        assert cci.verdict_for_run(_run(), root_sha=ROOT_SHA).state == cci.BORN

    @pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out", "", "skipped"])
    def test_any_other_conclusion_quarantines(self, conclusion: str) -> None:
        verdict = cci.verdict_for_run(_run(conclusion=conclusion), root_sha=ROOT_SHA)
        assert verdict.state == cci.QUARANTINED

    def test_an_unfinished_run_is_provisional_not_born(self) -> None:
        verdict = cci.verdict_for_run(
            _run(status="in_progress", conclusion=None), root_sha=ROOT_SHA
        )
        assert verdict.state == cci.PROVISIONAL

    def test_a_born_verdict_records_the_evidence(self) -> None:
        block = cci.ci_provenance(cci.verdict_for_run(_run(), root_sha=ROOT_SHA))
        assert block["authority_repo"] == CORE
        assert block["workflow"] == ORG_CI
        assert block["birth_run_id"] == 100
        assert block["birth_conclusion"] == "success"
        assert block["root_sha"] == ROOT_SHA
        assert block["state"] == cci.BORN

    def test_provenance_never_invents_a_value(self) -> None:
        """An unobserved run id is absent, not null and not a placeholder."""
        block = cci.ci_provenance(cci.timeout_verdict(ROOT_SHA, 60, saw_run=False))
        assert "birth_run_id" not in block
        assert "birth_conclusion" not in block
        assert block["state"] == cci.QUARANTINED


class TestTimeout:
    def test_never_started_and_started_but_stuck_are_different_diagnoses(self) -> None:
        never = cci.timeout_verdict(ROOT_SHA, 900, saw_run=False)
        stuck = cci.timeout_verdict(ROOT_SHA, 900, saw_run=True)
        assert "not enrolled" in never.detail
        assert "did not conclude" in stuck.detail
        assert never.detail != stuck.detail

    def test_a_timeout_is_a_failure_not_a_pass(self) -> None:
        for saw in (True, False):
            assert cci.timeout_verdict(ROOT_SHA, 900, saw_run=saw).state == cci.QUARANTINED

    def test_the_timeout_is_named_in_the_diagnosis(self) -> None:
        assert "900s" in cci.timeout_verdict(ROOT_SHA, 900, saw_run=False).detail


# ─────────────────────────────────────────────────────────────────────────────
# BIRTH-CI-001 / 004 — binding discovery, structural
# ─────────────────────────────────────────────────────────────────────────────


class TestBindingDiscovery:
    def test_a_canonical_binding_is_found(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "l9-ci.yml").write_text(_binding_yaml(f"{CORE}/{ORG_CI}@{PIN}"), encoding="utf-8")
        found = cci.canonical_bindings(tmp_path)
        assert len(found) == 1
        assert found[0].is_canonical
        assert found[0].ref_is_immutable

    def test_no_workflows_means_no_binding(self, tmp_path: Path) -> None:
        assert cci.canonical_bindings(tmp_path) == []

    def test_a_uses_inside_a_comment_is_not_a_binding(self, tmp_path: Path) -> None:
        """Structural parsing, not grep. This is why the module reads YAML."""
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "decoy.yml").write_text(
            f"# uses: {CORE}/{ORG_CI}@{PIN}\nname: x\non: push\njobs:\n"
            "  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        assert cci.canonical_bindings(tmp_path) == []

    def test_an_unparseable_workflow_binds_nothing(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "broken.yml").write_text("jobs: [unbalanced\n", encoding="utf-8")
        assert cci.canonical_bindings(tmp_path) == []

    def test_a_floating_ref_is_reported_as_not_immutable(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "l9-ci.yml").write_text(_binding_yaml(f"{CORE}/{ORG_CI}@main"), encoding="utf-8")
        binding = cci.canonical_bindings(tmp_path)[0]
        assert binding.is_canonical
        assert not binding.ref_is_immutable

    def test_a_non_l9_reusable_workflow_is_neither_canonical_nor_rogue(
        self, tmp_path: Path
    ) -> None:
        """A repository may call somebody else's workflow. That is its business."""
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "other.yml").write_text(
            _binding_yaml(f"acme/tools/.github/workflows/build.yml@{PIN}"), encoding="utf-8"
        )
        assert cci.canonical_bindings(tmp_path) == []
        assert cci.assert_binding_authorized(tmp_path) == []


class TestUnauthorizedAuthority:
    def test_a_quantum_l9_workflow_that_is_not_org_ci_fails_closed(self, tmp_path: Path) -> None:
        """Worse than no binding: it looks like enrollment and evaluates something else."""
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "l9-ci.yml").write_text(
            _binding_yaml(f"{CORE}/.github/workflows/self-ci.yml@{PIN}"), encoding="utf-8"
        )
        with pytest.raises(cci.CanonicalCIError, match="not the canonical authority"):
            cci.assert_binding_authorized(tmp_path)

    def test_a_lookalike_repository_fails_closed(self, tmp_path: Path) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "l9-ci.yml").write_text(
            _binding_yaml(f"Quantum-L9/l9-ci-core-fork/{ORG_CI}@{PIN}"), encoding="utf-8"
        )
        with pytest.raises(cci.CanonicalCIError):
            cci.assert_binding_authorized(tmp_path)


class TestPayloadCannotRemoveTheBinding:
    """BIRTH-CI-004, at the layer that decides it.

    The binding is measured on the ASSEMBLED tree, after the payload overlay and
    after ownership reconciliation — so 'the payload omitted it' and 'the
    payload replaced it' are the same observable fact, and both are caught.
    """

    def test_an_assembled_tree_without_the_binding_is_detectable(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        assert cci.canonical_bindings(tmp_path) == []

    def test_a_payload_that_overwrites_the_binding_with_its_own_ci_is_caught(
        self, tmp_path: Path
    ) -> None:
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "l9-ci.yml").write_text(
            "name: L9 CI\non: push\njobs:\n  l9-ci:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo 'my own CI'\n",
            encoding="utf-8",
        )
        assert cci.canonical_bindings(tmp_path) == [], (
            "a job that runs steps instead of calling the authority is not enrollment"
        )


class TestAuthorityIsNotGuessed:
    def test_the_authority_matches_l9_ci_core_declared_entrypoint(self) -> None:
        """Read from the contract, not invented here."""
        assert cci.CI_AUTHORITY_REPO == "Quantum-L9/l9-ci-core"
        assert cci.CI_AUTHORITY_WORKFLOW == ".github/workflows/org-ci.yml"

    def test_the_states_are_the_four_the_lifecycle_declares(self) -> None:
        assert {cci.LOCAL, cci.PROVISIONAL, cci.BORN, cci.QUARANTINED} == {
            "LOCAL",
            "PROVISIONAL",
            "BORN",
            "QUARANTINED",
        }
