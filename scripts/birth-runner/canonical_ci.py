#!/usr/bin/env python3
"""Canonical CI binding, correlation, and birth state.

A repository that exists is not automatically born. Creation proves GitHub
accepted bytes; lifecycle closure requires current organization enrollment and
an observed canonical CI success.

    LOCAL        assembled and locally validated; nothing published
    PROVISIONAL  published and enrolled with the canonical authority
    BORN         canonical required-workflow CI evaluated the repository and succeeded
    QUARANTINED  published, and enrollment is missing or accepted CI evidence failed

The publish transaction itself ends at PROVISIONAL because the organization
ruleset deliberately uses `do_not_enforce_on_create: true`. That keeps repository
creation possible while proving the newborn is enrolled for subsequent governed
events.

`l9-ci-core` now declares a native default-branch `push` lane as well as
`pull_request`. The external GitHub required-workflow runtime decides whether a
genesis push is actually instantiated. The birth control plane must never assume
that external behavior: an exact required-workflow push may earn BORN only when
it is observed and correlated to the zero-parent root commit. Otherwise a later
required-workflow pull-request success can earn BORN.

Ownership:

    GitHub organization ruleset  owns CI targeting and the required-workflow binding
    l9-ci-core                   owns CI implementation and execution semantics
    consumer repository          owns no L9 CI caller or Core pin
    l9-repo-template             owns birth orchestration and lifecycle correlation

Nothing here copies, reimplements, or second-guesses CI. It answers questions
about somebody else's CI: is this repository reachable by the canonical
authority, did a run evaluate the exact revision being claimed, and did it
succeed.

Birth publication uses `enrollment_from_rulesets`. Run-correlation helpers remain
here for lifecycle reconciliation. A stale success, a run on another branch, or
a run for another commit must never be accepted as evidence for this one.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The canonical CI authority. `l9-ci-core/.l9/org-runtime-contract.yaml` names
# `org-ci.yml` as the organization entrypoint; a binding that points anywhere
# else is not canonical CI, whatever it is called.
CI_AUTHORITY_REPO = "Quantum-L9/l9-ci-core"
CI_AUTHORITY_WORKFLOW = ".github/workflows/org-ci.yml"

# A required-workflow rule names the workflow's home by numeric repository id,
# not by name. The id is what makes the rule point at `l9-ci-core` rather than at
# any other repository that happens to keep a file at the same path, so it is
# the field enrollment is decided on. `Quantum-L9/l9-ci-core`, id:
CI_AUTHORITY_REPOSITORY_ID = 1285564308

# The ref the organization ruleset must pin. A rule that resolves the canonical
# workflow from some other branch or tag is a different workflow.
CI_AUTHORITY_REF = "refs/heads/main"

WORKFLOW_DIR = ".github/workflows"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# `owner/repo/.github/workflows/name.yml@ref` is the only shape GitHub accepts for
# a cross-repository reusable-workflow reference.
USES_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)/"
    r"(?P<path>\.github/workflows/[A-Za-z0-9._-]+\.ya?ml)@(?P<ref>\S+)$"
)

LOCAL = "LOCAL"
PROVISIONAL = "PROVISIONAL"
BORN = "BORN"
QUARANTINED = "QUARANTINED"


class CanonicalCIError(RuntimeError):
    """Birth cannot prove canonical CI. Never downgraded to a warning."""


@dataclass(frozen=True)
class Binding:
    """One observed CI binding, from a consumer workflow or organization ruleset."""

    workflow_file: str
    job: str
    owner_repo: str
    path: str
    ref: str

    @property
    def is_canonical(self) -> bool:
        return self.owner_repo == CI_AUTHORITY_REPO and self.path == CI_AUTHORITY_WORKFLOW

    @property
    def ref_is_immutable(self) -> bool:
        return bool(SHA_RE.match(self.ref))

    def describe(self) -> str:
        return f"{self.workflow_file}:{self.job} -> {self.owner_repo}/{self.path}@{self.ref}"


@dataclass
class CIVerdict:
    """What was observed about canonical CI for one exact revision."""

    state: str
    detail: str = ""
    run_id: int | None = None
    run_url: str = ""
    conclusion: str = ""
    authority_repo: str = CI_AUTHORITY_REPO
    workflow: str = CI_AUTHORITY_WORKFLOW
    revision: str = ""
    checked: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# Binding discovery: structural, never grep
# -----------------------------------------------------------------------------


def _load_yaml(text: str) -> Any:
    import yaml

    return yaml.safe_load(text)


def bindings_in_workflow(name: str, text: str) -> list[Binding]:
    """Every cross-repository `uses:` a workflow's jobs declare.

    Parsed as YAML rather than matched as text: a `uses:` inside a comment, a
    string literal, or a job this workflow never runs is not a binding, and a
    line-oriented check cannot tell the difference.
    """
    try:
        doc = _load_yaml(text)
    except Exception:  # noqa: BLE001 - an unparseable workflow binds nothing
        return []
    if not isinstance(doc, dict):
        return []
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return []
    found: list[Binding] = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if not isinstance(uses, str):
            continue
        match = USES_RE.match(uses.strip())
        if match is None:
            continue
        found.append(
            Binding(
                workflow_file=name,
                job=str(job_name),
                owner_repo=f"{match.group('owner')}/{match.group('repo')}",
                path=match.group("path"),
                ref=match.group("ref"),
            )
        )
    return found


def discover_bindings(root: Path) -> list[Binding]:
    """Every reusable-workflow binding declared by the repository at `root`."""
    workflows = root / WORKFLOW_DIR
    if not workflows.is_dir():
        return []
    found: list[Binding] = []
    for path in sorted(workflows.iterdir()):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        found.extend(
            bindings_in_workflow(path.name, path.read_text(encoding="utf-8", errors="replace"))
        )
    return found


def canonical_bindings(root: Path) -> list[Binding]:
    return [b for b in discover_bindings(root) if b.is_canonical]


#: Reads one ruleset's full representation by id, or returns None when it
#: cannot be read. Injected so this module stays pure and the GitHub call
#: stays in the orchestrator.
DetailFetcher = Callable[[int], Any]


def workflow_is_canonical(workflow: Any) -> bool:
    """Does one entry of a `workflows` rule name the canonical CI entrypoint?

    All three fields are load-bearing, and `repository_id` most of all. The path
    `.github/workflows/org-ci.yml` is not owned by anything. Any repository in
    the organization may hold a file there, and a rule pointing at that file in
    the wrong repository would enforce somebody else's CI under the canonical
    name. Ownership is therefore read from the numeric id GitHub records.
    """
    if not isinstance(workflow, dict):
        return False
    repository_id = workflow.get("repository_id")
    if isinstance(repository_id, bool) or not isinstance(repository_id, int):
        return False
    if repository_id != CI_AUTHORITY_REPOSITORY_ID:
        return False
    if str(workflow.get("path") or "") != CI_AUTHORITY_WORKFLOW:
        return False
    return str(workflow.get("ref") or "") == CI_AUTHORITY_REF


def enrollment_in_ruleset(detail: Any) -> Binding | None:
    """Enrollment as read from one hydrated ruleset, or None.

    `detail` is a full ruleset representation, the shape returned by
    `repos/{slug}/rulesets/{id}`, which is the only shape that carries `rules`.
    Every condition is re-read here rather than trusted from the listing that
    selected this ruleset, because the listing is a summary and the full
    representation is the authority.

    Enrollment requires all of:

      * `source_type` Organization;
      * `enforcement` active;
      * a `workflows` rule whose `do_not_enforce_on_create` is true;
      * an entry naming the canonical authority by repository id, path and ref.
    """
    if not isinstance(detail, dict):
        return None
    if str(detail.get("source_type") or "") != "Organization":
        return None
    if str(detail.get("enforcement") or "") != "active":
        return None
    for rule in detail.get("rules") or []:
        if not isinstance(rule, dict) or rule.get("type") != "workflows":
            continue
        params = rule.get("parameters")
        if not isinstance(params, dict):
            continue
        if params.get("do_not_enforce_on_create") is not True:
            continue
        for workflow in params.get("workflows") or []:
            if not workflow_is_canonical(workflow):
                continue
            return Binding(
                workflow_file=f"org-ruleset:{detail.get('name') or detail.get('id')}",
                job="required-workflow",
                owner_repo=CI_AUTHORITY_REPO,
                path=CI_AUTHORITY_WORKFLOW,
                ref=CI_AUTHORITY_REF,
            )
    return None


def enrollment_from_rulesets(rulesets: Any, *, fetch_detail: DetailFetcher) -> Binding | None:
    """The organization ruleset that requires canonical CI for a repository.

    `rulesets` is `repos/{slug}/rulesets?includes_parents=true`. That response is
    a list of summaries: it carries `id`, `name`, `source_type` and `enforcement`
    but not `rules`. Each candidate therefore has to be hydrated by id before the
    enrollment decision is made.

    Only Organization-sourced, actively enforced summaries are hydrated. A
    repository-sourced or `evaluate` ruleset could not be canonical enrollment.

    Raises `CanonicalCIError` when a candidate's detail cannot be read or has
    disappeared between listing and fetch. A ruleset whose rules are unknown
    leaves enrollment undeterminable and must not be quietly reported as absent.
    """
    if not isinstance(rulesets, list):
        return None
    for entry in rulesets:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("source_type") or "") != "Organization":
            continue
        if str(entry.get("enforcement") or "") != "active":
            continue
        ruleset_id = entry.get("id")
        name = str(entry.get("name") or "unnamed")
        if isinstance(ruleset_id, bool) or not isinstance(ruleset_id, int):
            raise CanonicalCIError(
                f"organisation ruleset {name!r} applies to this repository but carries no "
                f"usable id ({ruleset_id!r}), so its rules cannot be read. "
                "Enrolment is undeterminable."
            )
        detail = fetch_detail(ruleset_id)
        if detail is None:
            raise CanonicalCIError(
                f"organisation ruleset {ruleset_id} ({name!r}) is listed for this repository "
                "but its detail could not be read, so its rules are unknown. "
                "Enrolment is undeterminable."
            )
        found = enrollment_in_ruleset(detail)
        if found is not None:
            return found
    return None


def assert_binding_authorized(root: Path) -> list[Binding]:
    """BIRTH-CI-001 / BIRTH-CI-004, evaluated on the assembled tree.

    Absence of a consumer L9 workflow is allowed and expected under organization
    enforcement. A consumer workflow that points at a non-canonical Quantum-L9
    CI authority fails closed because it looks governed while evaluating
    something else.
    """
    all_bindings = discover_bindings(root)
    canonical = [b for b in all_bindings if b.is_canonical]
    rogue = [
        b
        for b in all_bindings
        if not b.is_canonical and b.owner_repo.split("/")[0] == CI_AUTHORITY_REPO.split("/")[0]
    ]
    if rogue:
        raise CanonicalCIError(
            "workflow binds a Quantum-L9 CI workflow that is not the canonical authority: "
            + "; ".join(b.describe() for b in rogue)
            + f" — canonical CI is {CI_AUTHORITY_REPO}/{CI_AUTHORITY_WORKFLOW}"
        )
    return canonical


# -----------------------------------------------------------------------------
# Run correlation: the run must be this exact revision's
# -----------------------------------------------------------------------------


def run_matches_root(entry: Any, *, root_sha: str, default_branch: str = "main") -> bool:
    """Is this Actions run an evaluation of exactly `root_sha`?

    "Some run passed recently" is not evidence. A run counts only when its head
    SHA is the root commit. Branch is checked too because a run for the same SHA
    on another ref is a different event, and a run that reports no SHA at all is
    never accepted.
    """
    if not isinstance(entry, dict):
        return False
    head = str(entry.get("head_sha") or "")
    if not SHA_RE.match(head) or head != root_sha:
        return False
    branch = str(entry.get("head_branch") or "")
    return branch in ("", default_branch)


def select_birth_run(
    runs: Any, *, root_sha: str, default_branch: str = "main"
) -> dict[str, Any] | None:
    """The newest run that evaluates this exact root commit, or None.

    Never falls back to the newest successful run. A stale success, a run on
    another branch and a run for another commit all return None.
    """
    if not isinstance(runs, list):
        return None
    candidates = [
        r for r in runs if run_matches_root(r, root_sha=root_sha, default_branch=default_branch)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))


def verdict_for_run(entry: dict[str, Any], *, root_sha: str) -> CIVerdict:
    """Turn one correlated run into a birth verdict."""
    run_id = entry.get("id")
    url = str(entry.get("html_url") or "")
    status = str(entry.get("status") or "")
    conclusion = str(entry.get("conclusion") or "")
    if status != "completed":
        return CIVerdict(
            state=PROVISIONAL,
            detail=f"run {run_id} is {status or 'unknown'} — not yet concluded",
            run_id=run_id if isinstance(run_id, int) else None,
            run_url=url,
        )
    if conclusion == "success":
        return CIVerdict(
            state=BORN,
            detail=f"run {run_id}: success",
            run_id=run_id if isinstance(run_id, int) else None,
            run_url=url,
            conclusion=conclusion,
            revision=root_sha,
        )
    return CIVerdict(
        state=QUARANTINED,
        detail=f"run {run_id}: {conclusion or 'no conclusion'}",
        run_id=run_id if isinstance(run_id, int) else None,
        run_url=url,
        conclusion=conclusion or "unknown",
    )


def timeout_verdict(root_sha: str, timeout_s: int, *, saw_run: bool) -> CIVerdict:
    """Distinguish never-started from started-but-not-finished."""
    if saw_run:
        detail = (
            f"canonical CI started for {root_sha[:12]} but did not conclude in {timeout_s}s "
            "— binding is live, the run is slow or stuck"
        )
    else:
        detail = (
            f"no canonical CI run ever appeared for {root_sha[:12]} within {timeout_s}s "
            "— the repository is not enrolled, or the authority never triggered"
        )
    return CIVerdict(state=QUARANTINED, detail=detail, revision=root_sha)


def ci_provenance(verdict: CIVerdict) -> dict[str, Any]:
    """The birth record's CI block. Only observed values, never placeholders."""
    block: dict[str, Any] = {
        "authority_repo": verdict.authority_repo,
        "workflow": verdict.workflow,
    }
    if verdict.revision:
        block["root_sha"] = verdict.revision
    if verdict.run_id is not None:
        block["birth_run_id"] = verdict.run_id
    if verdict.run_url:
        block["birth_run_url"] = verdict.run_url
    if verdict.conclusion:
        block["birth_conclusion"] = verdict.conclusion
    block["state"] = verdict.state
    return block
