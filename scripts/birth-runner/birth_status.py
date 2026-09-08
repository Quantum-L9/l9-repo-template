#!/usr/bin/env python3
"""Derive repository-birth lifecycle state from live GitHub evidence.

The immutable birth receipt records creation provenance. Lifecycle state is
separate live truth derived from current organization enrollment plus canonical
required-workflow executions. Consumer repositories never ship a Core workflow.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

SCHEMA = "l9.repo-birth-status/v1"
DEFAULT_ORG = "Quantum-L9"
REQUIRED_WORKFLOW_URL_TOKEN = "/actions/required_workflows/"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_WORKFLOW_EVENTS = frozenset({"pull_request", "merge_group"})
TERMINAL_FAILURES = frozenset(
    {"action_required", "cancelled", "failure", "stale", "startup_failure", "timed_out"}
)


def _load_canonical_ci():
    path = Path(__file__).resolve().parent / "canonical_ci.py"
    spec = importlib.util.spec_from_file_location("l9_birth_status_canonical_ci", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical CI contract at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canonical_ci = _load_canonical_ci()


class BirthStatusError(RuntimeError):
    """Authoritative lifecycle state could not be derived."""


JsonApi = Callable[[str], Any]
TextApi = Callable[[str], str]


@dataclass(frozen=True)
class RunEvidence:
    run_id: int
    url: str
    event: str
    head_sha: str
    head_branch: str
    status: str
    conclusion: str
    created_at: str
    workflow_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "url": self.url,
            "event": self.event,
            "head_sha": self.head_sha,
            "head_branch": self.head_branch,
            "status": self.status,
            "conclusion": self.conclusion,
            "created_at": self.created_at,
            "workflow_name": self.workflow_name,
        }


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], check=False, capture_output=True, text=True)


def gh_api_json(path: str) -> Any:
    proc = _run_gh(["api", path])
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthStatusError(f"GitHub API read failed for {path}: {detail[-1200:]}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise BirthStatusError(f"GitHub API returned invalid JSON for {path}") from exc


def gh_api_text(path: str) -> str:
    proc = _run_gh(["api", path, "-H", "Accept: application/vnd.github.raw+json"])
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthStatusError(f"GitHub API read failed for {path}: {detail[-1200:]}")
    return proc.stdout


def parse_time(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise BirthStatusError("missing timestamp")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise BirthStatusError(f"invalid timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_slug(repo: str, org: str = DEFAULT_ORG) -> str:
    value = (repo or "").strip()
    if not value:
        raise BirthStatusError("REPO is required")
    if "/" in value:
        owner, name = value.split("/", 1)
        if not owner or not name or "/" in name:
            raise BirthStatusError("REPO must be name or owner/name")
        return value
    return f"{org}/{value}"


def read_birth_receipt(slug: str, api_text: TextApi) -> dict[str, Any]:
    text = api_text(f"repos/{slug}/contents/.l9/birth-receipt.json")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BirthStatusError(".l9/birth-receipt.json is not valid JSON") from exc
    if not isinstance(doc, dict) or doc.get("schema") != "l9.birth-receipt/v1":
        raise BirthStatusError("repository has no canonical l9.birth-receipt/v1")
    if doc.get("repository") != slug:
        raise BirthStatusError(
            f"birth receipt repository mismatch: expected {slug}, got {doc.get('repository')!r}"
        )
    return doc


def current_enrollment(slug: str, api_json: JsonApi):
    summaries = api_json(f"repos/{slug}/rulesets?includes_parents=true")

    def fetch_detail(ruleset_id: int) -> Any:
        return api_json(f"repos/{slug}/rulesets/{ruleset_id}")

    try:
        return canonical_ci.enrollment_from_rulesets(summaries, fetch_detail=fetch_detail)
    except canonical_ci.CanonicalCIError as exc:
        raise BirthStatusError(str(exc)) from exc


def is_required_core_run(run: Any, *, born_at: datetime) -> bool:
    if not isinstance(run, dict):
        return False
    if str(run.get("event") or "") not in REQUIRED_WORKFLOW_EVENTS:
        return False
    if str(run.get("path") or "") != canonical_ci.CI_AUTHORITY_WORKFLOW:
        return False
    if REQUIRED_WORKFLOW_URL_TOKEN not in str(run.get("workflow_url") or ""):
        return False
    head_sha = str(run.get("head_sha") or "")
    if not SHA_RE.fullmatch(head_sha):
        return False
    try:
        created_at = parse_time(str(run.get("created_at") or ""))
    except BirthStatusError:
        return False
    return created_at >= born_at


def evidence_from_run(run: dict[str, Any]) -> RunEvidence:
    run_id = run.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        raise BirthStatusError("canonical workflow run has no usable id")
    return RunEvidence(
        run_id=run_id,
        url=str(run.get("html_url") or ""),
        event=str(run.get("event") or ""),
        head_sha=str(run.get("head_sha") or ""),
        head_branch=str(run.get("head_branch") or ""),
        status=str(run.get("status") or ""),
        conclusion=str(run.get("conclusion") or ""),
        created_at=str(run.get("created_at") or ""),
        workflow_name=str(run.get("name") or ""),
    )


def list_post_birth_runs(slug: str, born_at: datetime, api_json: JsonApi) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    page = 1
    while True:
        doc = api_json(f"repos/{slug}/actions/runs?per_page=100&page={page}")
        runs = doc.get("workflow_runs") if isinstance(doc, dict) else None
        if not isinstance(runs, list) or not runs:
            break
        for run in runs:
            if isinstance(run, dict) and is_required_core_run(run, born_at=born_at):
                found.append(run)
        observed_times: list[datetime] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            try:
                observed_times.append(parse_time(str(run.get("created_at") or "")))
            except BirthStatusError:
                continue
        if observed_times and min(observed_times) < born_at:
            break
        if len(runs) < 100:
            break
        page += 1
    return found


def classify_runs(runs: list[dict[str, Any]]) -> tuple[str, RunEvidence | None, str]:
    ordered = sorted(
        runs,
        key=lambda run: (str(run.get("created_at") or ""), int(run.get("id") or 0)),
    )
    successful = [
        run
        for run in ordered
        if str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") == "success"
    ]
    if successful:
        evidence = evidence_from_run(successful[0])
        source = "merge group" if evidence.event == "merge_group" else "pull request"
        return "BORN", evidence, f"canonical Core CI passed the post-birth {source}"

    terminal_failures = [
        run
        for run in ordered
        if str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") in TERMINAL_FAILURES
    ]
    if terminal_failures:
        evidence = evidence_from_run(terminal_failures[-1])
        return "QUARANTINED", evidence, "canonical Core CI completed without success"

    if ordered:
        evidence = evidence_from_run(ordered[-1])
        return "PROVISIONAL", evidence, "canonical Core CI is pending; no success exists yet"
    return "PROVISIONAL", None, "enrolled; no post-birth canonical lifecycle run observed"


def derive_status(
    slug: str,
    *,
    api_json: JsonApi = gh_api_json,
    api_text: TextApi = gh_api_text,
) -> dict[str, Any]:
    repo = api_json(f"repos/{slug}")
    if not isinstance(repo, dict) or str(repo.get("full_name") or "") != slug:
        raise BirthStatusError(f"repository {slug} could not be proven")
    default_branch = str(repo.get("default_branch") or "")
    if not default_branch:
        raise BirthStatusError("repository has no observable default branch")

    receipt = read_birth_receipt(slug, api_text)
    born_at = parse_time(str(receipt.get("born_at") or ""))
    enrollment = current_enrollment(slug, api_json)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "repository": slug,
        "default_branch": default_branch,
        "birth_receipt": {
            "schema": receipt.get("schema"),
            "digest": receipt.get("digest"),
            "born_at": receipt.get("born_at"),
            "immutable": True,
        },
        "canonical_ci": {
            "authority_repo": canonical_ci.CI_AUTHORITY_REPO,
            "workflow": canonical_ci.CI_AUTHORITY_WORKFLOW,
            "authority_ref": canonical_ci.CI_AUTHORITY_REF,
            "enrolled": enrollment is not None,
            "enrollment": enrollment.workflow_file if enrollment is not None else None,
            "accepted_events": sorted(REQUIRED_WORKFLOW_EVENTS),
        },
        "evidence": None,
    }

    if enrollment is None:
        result.update(
            state="QUARANTINED",
            detail="canonical organization required-workflow enrollment is missing",
        )
        return result

    candidates = list_post_birth_runs(slug, born_at, api_json)
    state, evidence, detail = classify_runs(candidates)
    result["state"] = state
    result["detail"] = detail
    if evidence is not None:
        result["evidence"] = evidence.to_dict()
    return result


def render_human(status: dict[str, Any]) -> str:
    ci = status["canonical_ci"]
    receipt = status["birth_receipt"]
    lines = [
        "L9 BIRTH STATUS",
        f"REPOSITORY: {status['repository']}",
        f"STATE: {status['state']}",
        f"DETAIL: {status['detail']}",
        f"RECEIPT: immutable sha256:{receipt.get('digest') or 'unknown'}",
        "ENROLLMENT: " + (str(ci.get("enrollment")) if ci.get("enrolled") else "FAIL"),
        f"CORE: {ci['authority_repo']}/{ci['workflow']}@{ci['authority_ref']}",
    ]
    evidence = status.get("evidence")
    if isinstance(evidence, dict):
        lines.extend(
            [
                f"EVENT: {evidence.get('event') or 'unknown'}",
                f"HEAD: {evidence.get('head_sha') or 'unknown'}",
                f"RUN: {evidence.get('run_id')}",
                f"CONCLUSION: {evidence.get('conclusion') or evidence.get('status') or 'pending'}",
                f"URL: {evidence.get('url') or 'unknown'}",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive current L9 repository birth status")
    parser.add_argument("--repo", required=True, help="repository name or owner/name")
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if shutil.which("gh") is None:
        print("L9 BIRTH STATUS\nSTATE: UNKNOWN\nDETAIL: gh is required", file=sys.stderr)
        return 2
    args = parse_args(argv)
    try:
        slug = normalize_slug(args.repo, args.org)
        status = derive_status(slug)
    except BirthStatusError as exc:
        slug = f"{args.org}/{args.repo}" if "/" not in args.repo else args.repo
        if args.as_json:
            print(
                json.dumps(
                    {"schema": SCHEMA, "repository": slug, "state": "UNKNOWN", "detail": str(exc)},
                    sort_keys=True,
                )
            )
        else:
            print(f"L9 BIRTH STATUS\nREPOSITORY: {slug}\nSTATE: UNKNOWN\nDETAIL: {exc}")
        return 2
    if args.as_json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(render_human(status))
    return 1 if status["state"] == "QUARANTINED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
