from __future__ import annotations

import base64
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
ROOT_SHA = "a" * 40
WORKFLOW_SHA = "1" * 40
NODE = "WFR_test"
RULESET_ID = 21895545


def _receipt(**overrides: object) -> str:
    doc: dict[str, object] = {
        "schema": "l9.birth-receipt/v1",
        "repository": SLUG,
        "born_at": BORN_AT,
        "repo_class": "service",
        "template": {
            "repository": "Quantum-L9/l9-repo-template",
            "sha": "a" * 40,
            "version": "1.0.0",
        },
        "org_policy": {"repository": "Quantum-L9/.github", "sha": "e" * 40},
        "payload_mode": "none",
        "manifest_sha256": "f" * 64,
    }
    doc.update(overrides)
    if "digest" not in overrides:
        doc["digest"] = status.provenance.receipt_digest(doc)
    return json.dumps(doc)


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
        "node_id": NODE,
    }


class FakeApi:
    def __init__(self, runs: list[dict], *, enrolled: bool = True):
        self.runs = runs
        self.enrolled = enrolled
        self.calls: list[str] = []
        self.current_body = _receipt()
        self.root_body = self.current_body
        self.authority_repo = status.canonical_ci.CI_AUTHORITY_REPO

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
        compare = f"repos/{status.canonical_ci.CI_AUTHORITY_REPO}/compare/"
        if path.startswith(compare):
            return {"status": "ahead", "ahead_by": 3, "behind_by": 0}
        raise AssertionError(f"unexpected API path: {path}")

    def text(self, path: str) -> str:
        self.calls.append(path)
        if path.startswith(f"repos/{SLUG}/contents/.l9/birth-receipt.json?ref="):
            return self.root_body
        assert path == f"repos/{SLUG}/contents/.l9/birth-receipt.json"
        return self.current_body

    def exchange(self, path: str) -> tuple[dict[str, str], str]:
        self.calls.append(path)
        if "page=9" in path:
            digest = json.loads(self.current_body)["digest"]
            body = json.dumps(
                [
                    {
                        "sha": ROOT_SHA,
                        "parents": [],
                        "commit": {
                            "message": f"birth the repository\n\nL9-Birth-Receipt: sha256:{digest}\n"
                        },
                    }
                ]
            )
            return {}, body
        if "commits?" in path:
            link = (
                f"<https://api.github.com/repos/{SLUG}/commits?sha=main&per_page=100&page=9>; "
                'rel="last"'
            )
            return {"link": link}, "[]"
        raise AssertionError(f"unexpected exchange path: {path}")

    def workflow_file(self, node_id: str) -> dict[str, str]:
        assert node_id == NODE
        workflow = status.canonical_ci.CI_AUTHORITY_WORKFLOW
        return {
            "path": workflow,
            "repositoryName": self.authority_repo,
            "repositoryFileUrl": (
                f"https://github.com/{status.canonical_ci.CI_AUTHORITY_REPO}/blob/"
                f"{WORKFLOW_SHA}/{workflow}"
            ),
        }


def _derive(api: FakeApi) -> dict:
    return status.derive_status(
        SLUG,
        api_json=api.json,
        api_text=api.text,
        api_exchange=api.exchange,
        workflow_file=api.workflow_file,
    )


def test_ideaos_shape_becomes_born_from_required_workflow_pr_success() -> None:
    api = FakeApi([_run()])
    result = _derive(api)
    assert result["state"] == "BORN"
    assert result["canonical_ci"]["enrolled"] is True
    assert result["canonical_ci"]["accepted_events"] == ["merge_group", "pull_request"]
    assert result["evidence"]["event"] == "pull_request"
    assert result["evidence"]["head_sha"] == PR_SHA
    assert result["evidence"]["run_id"] == 1
    assert result["birth_receipt"]["immutable"] is True


def test_required_workflow_merge_group_success_can_earn_born() -> None:
    api = FakeApi([_run(event="merge_group", head_branch="gh-readonly-queue/main/pr-1")])
    result = _derive(api)
    assert result["state"] == "BORN"
    assert result["evidence"]["event"] == "merge_group"
    assert "merge group" in result["detail"]


def test_push_is_not_required_workflow_lifecycle_evidence() -> None:
    api = FakeApi([_run(event="push", head_sha=OTHER_SHA, head_branch="main")])
    result = _derive(api)
    assert result["state"] == "PROVISIONAL"
    assert result["evidence"] is None


def test_consumer_workflow_with_same_path_is_not_required_workflow_evidence() -> None:
    local = _run(
        workflow_url="https://api.github.com/repos/Quantum-L9/IdeaOS/actions/workflows/352698067"
    )
    api = FakeApi([local])
    result = _derive(api)
    assert result["state"] == "PROVISIONAL"
    assert result["evidence"] is None


def test_missing_org_enrollment_is_quarantined_even_with_a_green_run() -> None:
    api = FakeApi([_run()], enrolled=False)
    result = _derive(api)
    assert result["state"] == "QUARANTINED"
    assert result["canonical_ci"]["enrolled"] is False
    assert result["evidence"] is None


def test_enrolled_repo_with_no_lifecycle_run_is_provisional() -> None:
    api = FakeApi([])
    result = _derive(api)
    assert result["state"] == "PROVISIONAL"
    assert "no post-birth" in result["detail"]


def test_failed_required_workflow_run_quarantines_until_success_exists() -> None:
    failed = _run(conclusion="failure")
    api = FakeApi([failed])
    result = _derive(api)
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
    result = _derive(api)
    assert result["state"] == "BORN"
    assert result["evidence"]["run_id"] == 1


def test_pre_birth_run_is_ignored() -> None:
    stale = _run(created_at="2026-09-08T00:40:00Z")
    api = FakeApi([stale])
    result = _derive(api)
    assert result["state"] == "PROVISIONAL"


def test_foreign_required_workflow_is_not_canonical_authority() -> None:
    api = FakeApi([_run()])
    api.authority_repo = "Quantum-L9/not-core"
    result = _derive(api)
    assert result["state"] == "PROVISIONAL"
    assert result["evidence"] is None


def test_skipped_and_neutral_completed_runs_are_quarantined(conclusion: str = "skipped") -> None:
    api = FakeApi([_run(conclusion=conclusion)])
    result = _derive(api)
    assert result["state"] == "QUARANTINED"
    assert result["evidence"]["conclusion"] == conclusion
    assert "pending" not in result["detail"]


def test_neutral_completed_run_is_quarantined() -> None:
    test_skipped_and_neutral_completed_runs_are_quarantined("neutral")


def test_contents_envelope_decodes_before_receipt_parse() -> None:
    raw = _receipt()
    envelope = json.dumps(
        {"encoding": "base64", "content": base64.b64encode(raw.encode()).decode()}
    )
    assert json.loads(status.decode_contents_body(envelope))["schema"] == "l9.birth-receipt/v1"


def test_mutated_receipt_digest_is_unknown() -> None:
    api = FakeApi([_run()])
    body = json.loads(api.current_body)
    body["digest"] = "0" * 64
    api.current_body = json.dumps(body)
    result = _derive(api)
    assert result["state"] == "UNKNOWN"
    assert result["birth_receipt"]["immutable"] is False
    assert "digest" in result["detail"]


def test_rewritten_receipt_blob_is_unknown_even_when_digest_matches() -> None:
    api = FakeApi([_run()])
    api.root_body = _receipt(born_at="2026-09-01T00:00:00+00:00")
    result = _derive(api)
    assert result["state"] == "UNKNOWN"
    assert result["birth_receipt"]["immutable"] is False
    assert "root commit" in result["detail"]
