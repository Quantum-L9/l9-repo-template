#!/usr/bin/env python3
"""Canonical CI binding, correlation, and birth state.

A repository that exists is not a repository that is born. Creating the remote,
pushing the root commit, and applying organization settings prove that GitHub
accepted some bytes — none of it proves the code was ever evaluated. This module
holds the part that does.

    LOCAL        assembled and locally validated; nothing published
    PROVISIONAL  root commit published; canonical CI not yet proven
    BORN         canonical CI evaluated THIS root commit and succeeded
    QUARANTINED  published, and canonical CI is missing, failed, or timed out

The transition PROVISIONAL -> BORN is the only one that may print BORN, and it
requires a remotely observed run correlated to the exact root SHA. Publication
and successful birth are separate events, which is also what keeps the model
acyclic: CI cannot run before a commit exists, so birth waits after publishing
rather than gating the commit itself.

Ownership, unchanged by this module:

    l9-ci-core           owns CI implementation and execution semantics
    the newborn          owns only the minimal binding that invokes it
    l9-repo-template     owns birth orchestration and this verification

Nothing here copies, reimplements, or second-guesses CI. It answers three
questions about someone else's CI: is this repository bound to it, did it run
for this exact commit, and did it succeed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The canonical CI authority. `l9-ci-core/.l9/org-runtime-contract.yaml` names
# `org-ci.yml` as the organization entrypoint; a binding that points anywhere
# else is not canonical CI, whatever it is called.
CI_AUTHORITY_REPO = "Quantum-L9/l9-ci-core"
CI_AUTHORITY_WORKFLOW = ".github/workflows/org-ci.yml"

WORKFLOW_DIR = ".github/workflows"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# `owner/repo/.github/workflows/name.yml@ref` — the only shape GitHub accepts for
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
    """One reusable-workflow reference found in a newborn's own workflows."""

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
    """What was observed about canonical CI for one root commit."""

    state: str
    detail: str = ""
    run_id: int | None = None
    run_url: str = ""
    conclusion: str = ""
    authority_repo: str = CI_AUTHORITY_REPO
    workflow: str = CI_AUTHORITY_WORKFLOW
    revision: str = ""
    checked: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Binding discovery — structural, never grep
# ─────────────────────────────────────────────────────────────────────────────


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


def assert_binding_authorized(root: Path) -> list[Binding]:
    """BIRTH-CI-001 / BIRTH-CI-004, evaluated on the assembled tree.

    Raises when a repository declares CI that is not the canonical authority.
    An unauthorized binding is worse than none: it looks like enrollment and
    evaluates something else.
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


# ─────────────────────────────────────────────────────────────────────────────
# Run correlation — the run must be THIS commit's
# ─────────────────────────────────────────────────────────────────────────────


def run_matches_root(entry: Any, *, root_sha: str, default_branch: str = "main") -> bool:
    """Is this Actions run an evaluation of exactly `root_sha`?

    "Some run passed recently" is not evidence. A run counts only when its head
    SHA is the root commit. Branch is checked too, because a run for the same
    SHA on another ref is a different event, and a run that reports no SHA at
    all is never accepted.
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
    """The newest run that evaluates this root commit, or None.

    Never falls back to "the newest successful run". A stale success, a run on
    another branch, and a run for another commit all return None, which is what
    keeps a green-looking repository from being declared born on someone else's
    evidence.
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
    """Distinguish "never started" from "started and did not finish".

    The two failures have different causes and different fixes, and a single
    "CI did not pass" message hides which one happened.
    """
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
    """The birth record's CI block. Only observed values; never a placeholder."""
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
