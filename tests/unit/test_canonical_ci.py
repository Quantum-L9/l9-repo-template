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


# ─────────────────────────────────────────────────────────────────────────────
# Enrolment — the claim birth can actually prove
# ─────────────────────────────────────────────────────────────────────────────

CORE_ID = cci.CI_AUTHORITY_REPOSITORY_ID
CANON_REF = cci.CI_AUTHORITY_REF


def _summary(**over: object) -> dict:
    """A ruleset exactly as `repos/{slug}/rulesets?includes_parents=true` returns it.

    Note what is absent: `rules`. The listing names each ruleset and says where
    it comes from and whether it is enforced, and stops there. A decision made
    from this object alone can only ever be "not enrolled".
    """
    base = {
        "id": 42,
        "name": "L9 canonical CI required",
        "target": "branch",
        "source_type": "Organization",
        "source": "Quantum-L9",
        "enforcement": "active",
        "node_id": "RRS_lACkT3Jn",
        "_links": {"self": {"href": "/orgs/Quantum-L9/rulesets/42"}},
    }
    base.update(over)
    return base


def _detail(**over: object) -> dict:
    """The same ruleset as `repos/{slug}/rulesets/{id}` returns it: `rules` present."""
    base = dict(_summary())
    base["rules"] = [
        {
            "type": "workflows",
            "parameters": {
                "do_not_enforce_on_create": True,
                "workflows": [
                    {"path": ORG_CI, "ref": CANON_REF, "repository_id": CORE_ID, "sha": PIN}
                ],
            },
        }
    ]
    base.update(over)
    return base


def _only(detail: dict) -> dict:
    """The single workflow entry of a detail's `workflows` rule."""
    return detail["rules"][0]["parameters"]["workflows"][0]


class _Fetcher:
    """A detail endpoint. Records what it was asked for; unknown ids are unreadable."""

    def __init__(self, *details: dict) -> None:
        self.by_id = {d["id"]: d for d in details}
        self.calls: list[int] = []

    def __call__(self, ruleset_id: int) -> object | None:
        self.calls.append(ruleset_id)
        return self.by_id.get(ruleset_id)


def _enrolment(summaries: object, *details: dict) -> object | None:
    return cci.enrollment_from_rulesets(summaries, fetch_detail=_Fetcher(*details))


class TestEnrollmentHydration:
    """The listing is a summary; the decision needs the full object."""

    def test_the_listing_carries_no_rules_to_decide_on(self) -> None:
        assert "rules" not in _summary()
        assert "rules" in _detail()

    def test_the_candidate_is_hydrated_by_id(self) -> None:
        fetch = _Fetcher(_detail())
        found = cci.enrollment_from_rulesets([_summary()], fetch_detail=fetch)
        assert found is not None
        assert fetch.calls == [42]

    def test_a_ruleset_that_could_never_qualify_is_not_hydrated(self) -> None:
        """No call is worth making for a ruleset whose summary already disqualifies it.

        It also means its detail being unreadable proves nothing, so it must not
        be allowed to fail the birth closed.
        """
        fetch = _Fetcher()
        cci.enrollment_from_rulesets(
            [
                _summary(id=1, source_type="Repository"),
                _summary(id=2, enforcement="evaluate"),
            ],
            fetch_detail=fetch,
        )
        assert fetch.calls == []


class TestEnrollment:
    def test_an_organisation_ruleset_requiring_org_ci_is_enrolment(self) -> None:
        found = _enrolment([_summary()], _detail())
        assert found is not None
        assert found.is_canonical
        assert "org-ruleset:" in found.workflow_file
        assert found.ref == CANON_REF

    def test_a_repository_sourced_ruleset_is_not_enrolment(self) -> None:
        """Only the organisation can enrol a repository.

        A repo-sourced ruleset is the repository enrolling itself — the
        consumer-owned enforcement `org-runtime-contract.yaml` prohibits.
        """
        assert _enrolment([_summary(source_type="Repository")]) is None

    def test_a_repository_sourced_detail_is_not_enrolment(self) -> None:
        """The full object is the authority, not the summary that selected it."""
        assert _enrolment([_summary()], _detail(source_type="Repository")) is None

    def test_an_evaluate_ruleset_is_not_enrolment(self) -> None:
        """`evaluate` reports and permits. It makes nothing required."""
        assert _enrolment([_summary(enforcement="evaluate")]) is None

    def test_an_evaluate_detail_is_not_enrolment(self) -> None:
        assert _enrolment([_summary()], _detail(enforcement="evaluate")) is None

    def test_the_canonical_path_in_another_repository_is_not_enrolment(self) -> None:
        """Ownership is the repository id, never the path.

        Any repository in the organisation may keep a file at
        `.github/workflows/org-ci.yml`. A rule pointing at the wrong one would
        enforce someone else's CI under the canonical name.
        """
        wrong = _detail()
        _only(wrong)["repository_id"] = CORE_ID + 1
        assert _enrolment([_summary()], wrong) is None

    @pytest.mark.parametrize("bad", [None, "1285564308", True])
    def test_a_missing_or_untyped_repository_id_is_not_enrolment(self, bad: object) -> None:
        wrong = _detail()
        _only(wrong)["repository_id"] = bad
        assert _enrolment([_summary()], wrong) is None

    def test_a_ruleset_requiring_a_different_workflow_is_not_enrolment(self) -> None:
        wrong = _detail()
        _only(wrong)["path"] = ".github/workflows/self-ci.yml"
        assert _enrolment([_summary()], wrong) is None

    def test_a_ruleset_pinning_a_different_ref_is_not_enrolment(self) -> None:
        """A different ref resolves a different workflow, whatever its path."""
        wrong = _detail()
        _only(wrong)["ref"] = "refs/heads/staging"
        assert _enrolment([_summary()], wrong) is None

    def test_enforcing_on_create_is_not_enrolment(self) -> None:
        """A required workflow that fires on create blocks the newborn's own birth."""
        wrong = _detail()
        wrong["rules"][0]["parameters"]["do_not_enforce_on_create"] = False
        assert _enrolment([_summary()], wrong) is None

    def test_an_absent_do_not_enforce_on_create_is_not_enrolment(self) -> None:
        wrong = _detail()
        del wrong["rules"][0]["parameters"]["do_not_enforce_on_create"]
        assert _enrolment([_summary()], wrong) is None

    def test_a_non_workflows_rule_is_not_enrolment(self) -> None:
        """A required STATUS CHECK is not a required WORKFLOW.

        A status check blocks a merge; it does not make anything run. A repo
        with no workflow would block forever on a check that never appears.
        """
        checks = _detail()
        checks["rules"] = [
            {"type": "required_status_checks", "parameters": {"required_status_checks": []}}
        ]
        assert _enrolment([_summary()], checks) is None

    @pytest.mark.parametrize("bad", [None, "not-a-list", 42, {}, []])
    def test_unreadable_input_is_never_enrolment(self, bad: object) -> None:
        assert _enrolment(bad) is None

    def test_enrolment_is_found_among_unrelated_rulesets(self) -> None:
        noise = [
            {"source_type": "Repository", "name": "Code Quality Copilot review", "rules": []},
            _summary(id=7, name="Org tag protection"),
            _summary(),
        ]
        assert _enrolment(noise, _detail(id=7, rules=[]), _detail()) is not None


class TestUndeterminableFailsClosed:
    """A ruleset that applies here and cannot be read is not an absence."""

    def test_an_unreadable_detail_raises_rather_than_reading_as_unenrolled(self) -> None:
        with pytest.raises(cci.CanonicalCIError, match="undeterminable"):
            _enrolment([_summary()])

    def test_a_ruleset_that_disappears_between_list_and_fetch_raises(self) -> None:
        """Listed a moment ago, 404 now. That is a disappearance, not an absence."""
        with pytest.raises(cci.CanonicalCIError, match="42"):
            _enrolment([_summary(), _summary(id=99)], _detail(id=99))

    def test_an_unreadable_detail_is_not_masked_by_a_later_enrolment(self) -> None:
        """Fail closed even when a readable ruleset further down would have passed.

        The unreadable one might have been a stricter rule; nothing here knows.
        """
        with pytest.raises(cci.CanonicalCIError):
            _enrolment([_summary(id=7, name="unreadable"), _summary()], _detail())

    def test_a_summary_without_a_usable_id_raises(self) -> None:
        with pytest.raises(cci.CanonicalCIError, match="undeterminable"):
            _enrolment([_summary(id=None)])
