from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "scripts" / "birth-runner" / "birth_status.py"
_SPEC = importlib.util.spec_from_file_location("l9_birth_status", MODULE)
assert _SPEC is not None
assert _SPEC.loader is not None
status = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = status
_SPEC.loader.exec_module(status)

SLUG = "Quantum-L9/IdeaOS"
BORN_AT = "2026-09-08T00:53:27+00:00"
PR_SHA = "b" * 40
OTHER_SHA = "c" * 40
RULESET_ID = 21895545


def _receipt() -> str:
    return json.dumps(
        {
            "schema": "l9.birth-receipt/v1",
            "repository": SLUG,
            "born_at": BORN_AT,
            "digest": "d" * 64,
        }
    )


def _summary() -> dict:
    return {
        "id": RULESET_ID,
        "name": "L9 canonical CI required",
        "source_type": "Organization",
        "source": "Quantum-L9",
        "enforcement": "active",
    }


def _detail() -> dict:
    return {
        **_summary(),
        "rules": [
            {
                "type": "workflows",
                "parameters": {
                    "do_not_enforce_on_create": True,
                    "workflows": [
                        {
                            "repository_id": status.canonical_ci.CI_AUTHORITY_REPOSITORY_ID,
                            "path": status.canonical_ci.CI_AUTHORITY_WORKFLOW,
                            "ref": status.canonical_ci.CI_AUTHORITY_REF,
                        }
                    ],
                },
            }
        ],
    }


def _run(
    *,
    run_id: int = 1,
    event: str = "pull_request",
    head_sha: str = PR_SHA,
    head_branch: str = "feature/first",
    run_status: str = "completed",
    conclusion: str = "success",
    path: str = ".github/workflows/org-ci.yml",
    workflow_url: str = "https://api.github.com/repos/Quantum-L9/IdeaOS/actions/required_workflows/352698067",
    created_at: str = "2026-09-08T00:55:42Z",
) -> dict:
    return {
        "id": run_id,
        "name": "Organization CI (Core)",
        "event": event,
        "head_sha": head_sha,
        "head_branch": head_branch,
        "status": run_status,
        "conclusion": conclusion,
        "path": path,
        "workflow_url": workflow_url,
        "created_at": created_at,
        "html_url": f"https://github.com/Quantum-L9/IdeaOS/actions/runs/{run_id}",
    }


class FakeApi:
    def __init__(self, runs: list[dict], *, enrolled: bool = True):
        self.runs = runs
        self.enrolled = enrolled
        self.calls: list[str] = []

    def json(self, path: str):
        self.calls.append(path)
        if path == f"repos/{SLUG}":
            return {"full_name": SLUG, "default_branch": "main"}
        if path == f"repos/{SLUG}/rulesets?includes_parents=true":
            return [_summary()] if self.enrolled else []
        if path == f"repos/{SLUG}/rulesets/{RULESET_ID}":
            return _detail()
        if path == f"repos/{SLUG}/actions/runs?per_page=100&page=1":
            return {"workflow_runs": self.runs}
        raise AssertionError(f"unexpected API path: {path}")

    def text(self, path: str) -> str:
        self.calls.append(path)
        assert path == f"repos/{SLUG}/contents/.l9/birth-receipt.json"
        return _receipt()


def test_ideaos_shape_becomes_born_from_required_workflow_pr_success() -> None:
    api = FakeApi([_run()])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "BORN"
    assert result["canonical_ci"]["enrolled"] is True
    assert result["canonical_ci"]["accepted_events"] == ["merge_group", "pull_request"]
    assert result["evidence"]["event"] == "pull_request"
    assert result["evidence"]["head_sha"] == PR_SHA
    assert result["evidence"]["run_id"] == 1
    assert result["birth_receipt"]["immutable"] is True


def test_required_workflow_merge_group_success_can_earn_born() -> None:
    api = FakeApi([_run(event="merge_group", head_branch="gh-readonly-queue/main/pr-1")])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "BORN"
    assert result["evidence"]["event"] == "merge_group"
    assert "merge group" in result["detail"]


def test_push_is_not_required_workflow_lifecycle_evidence() -> None:
    api = FakeApi([_run(event="push", head_sha=OTHER_SHA, head_branch="main")])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "PROVISIONAL"
    assert result["evidence"] is None


def test_consumer_workflow_with_same_path_is_not_required_workflow_evidence() -> None:
    local = _run(
        workflow_url="https://api.github.com/repos/Quantum-L9/IdeaOS/actions/workflows/352698067"
    )
    api = FakeApi([local])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "PROVISIONAL"
    assert result["evidence"] is None


def test_missing_org_enrollment_is_quarantined_even_with_a_green_run() -> None:
    api = FakeApi([_run()], enrolled=False)
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "QUARANTINED"
    assert result["canonical_ci"]["enrolled"] is False
    assert result["evidence"] is None


def test_enrolled_repo_with_no_lifecycle_run_is_provisional() -> None:
    api = FakeApi([])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "PROVISIONAL"
    assert "no post-birth" in result["detail"]


def test_failed_required_workflow_run_quarantines_until_success_exists() -> None:
    failed = _run(conclusion="failure")
    api = FakeApi([failed])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "QUARANTINED"
    assert result["evidence"]["conclusion"] == "failure"


def test_later_failure_does_not_unbirth_repository_after_success() -> None:
    passed = _run(run_id=1, conclusion="success")
    failed = _run(
        run_id=2,
        head_sha=OTHER_SHA,
        conclusion="failure",
        created_at="2026-09-08T02:00:00Z",
    )
    api = FakeApi([failed, passed])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "BORN"
    assert result["evidence"]["run_id"] == 1


def test_pre_birth_run_is_ignored() -> None:
    stale = _run(created_at="2026-09-08T00:40:00Z")
    api = FakeApi([stale])
    result = status.derive_status(SLUG, api_json=api.json, api_text=api.text)
    assert result["state"] == "PROVISIONAL"
