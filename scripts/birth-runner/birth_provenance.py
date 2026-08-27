#!/usr/bin/env python3
"""Two records, never one: what a repository was BORN from, and what it CONFORMS to now.

A repository has two different relationships with the template that made it, and
collapsing them into one file is why "which template made this?" and "is this
repository up to date?" kept answering each other's question.

    BIRTH PROVENANCE      immutable, forever
                          `.l9-template-version`, `.l9/org-birth-profile.yaml`,
                          `.l9/birth-receipt.json`
                          Three years from now these still describe what created
                          the repository. Nothing reconciles them, ever.

    CONFORMANCE STATE     mutable, reconciled
                          `.l9/template-state.yaml`
                          What the repository is expected to match TODAY. A
                          reconciliation PR moves this; it never touches the
                          birth record.

Two records, two questions:

    BIRTH INTEGRITY       "Is this repository genuinely what it claims it was
                          born from?"      -> scripts/birth-runner/verify_birth_integrity.py
    CURRENT CONFORMANCE   "Has it drifted from today's required org/template
                          state?"          -> the central drift engine, which reads
                          `.l9/template-state.yaml` and never rewrites the birth record.

This module owns the shapes and the digests over them, so the engine that writes
them and the checker that verifies them cannot drift apart: one algorithm, one
file, two callers.

Dependency-free on purpose. The provenance files are read by Python here, by one
regex in Node on the organization side, and by a human three years from now. None
of those should need a YAML library to answer "where did this repository come
from".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

TEMPLATE_REPO = "Quantum-L9/l9-repo-template"
ORG_PROFILE_REPO = "Quantum-L9/.github"

# ─── The four provenance surfaces ────────────────────────────────────────────
TEMPLATE_VERSION_PATH = ".l9-template-version"
MARKER_PATH = ".l9/org-birth-profile.yaml"
BIRTH_RECEIPT_PATH = ".l9/birth-receipt.json"
TEMPLATE_STATE_PATH = ".l9/template-state.yaml"

# Written by the birth engine, after the product payload, and never again.
BIRTH_OWNED_PATHS = frozenset({TEMPLATE_VERSION_PATH, MARKER_PATH, BIRTH_RECEIPT_PATH})
# Written by the birth engine, then owned by reconciliation.
CONFORMANCE_OWNED_PATHS = frozenset({TEMPLATE_STATE_PATH})
# A product payload owns its product. It never owns the record of its own birth:
# a payload carrying any of these is rejected rather than silently overwritten.
ENGINE_OWNED_PATHS = BIRTH_OWNED_PATHS | CONFORMANCE_OWNED_PATHS

RECEIPT_SCHEMA = "l9.birth-receipt/v1"
TEMPLATE_STATE_SCHEMA = "l9.template-state/v1"
# The organization's contract for this file is three keys — schema, profile,
# authority (Quantum-L9/.github docs/REPO_BIRTH_PROFILES.md) — and it parses them
# with one regex. Birth provenance is an additive nested block under `birth:`, so
# the org's v1 reader is unaffected and the schema id stays honest.
MARKER_SCHEMA = "l9.org-birth-profile-marker/v1"

TRAILER_RECEIPT = "L9-Birth-Receipt"
TRAILER_TEMPLATE = "L9-Template"
TRAILER_TEMPLATE_VERSION = "L9-Template-Version"
TRAILER_POLICY = "L9-Policy"
TRAILER_CLASS = "L9-Class"
REQUIRED_TRAILERS = (TRAILER_RECEIPT, TRAILER_TEMPLATE, TRAILER_POLICY, TRAILER_CLASS)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")
_TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$")


class ProvenanceError(RuntimeError):
    """A provenance record could not be produced or could not be trusted."""


# ─────────────────────────────────────────────────────────────────────────────
# git, as the provenance substrate
# ─────────────────────────────────────────────────────────────────────────────


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise ProvenanceError(f"git {' '.join(args)} failed ({proc.returncode}): {detail[-500:]}")
    return proc.stdout


def is_git_repo(root: Path) -> bool:
    try:
        return git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except ProvenanceError:
        return False


def has_commits(root: Path) -> bool:
    try:
        git(root, "rev-parse", "--verify", "HEAD")
    except ProvenanceError:
        return False
    return True


def root_commit(root: Path) -> str:
    """The one commit a born repository starts from.

    More than one root means an unrelated history was grafted on, and "the birth
    commit" stops being a well-defined thing to attest against — so that is a
    failure, not a pick-the-first situation.
    """
    roots = [line.strip() for line in git(root, "rev-list", "--max-parents=0", "HEAD").split()]
    if len(roots) != 1:
        raise ProvenanceError(
            f"expected exactly one root commit, found {len(roots)} — "
            "an unrelated history was merged into this repository"
        )
    return roots[0]


def commit_message(root: Path, commit: str) -> str:
    return git(root, "log", "-1", "--format=%B", commit)


def template_version_at(template_src: Path, sha: str) -> str:
    """The `.l9-template-version` recorded AT a specific template commit.

    Not the one lying in the template working tree. The birth record pins a SHA,
    so the version it records has to be the version that SHA actually carries —
    otherwise a repository is stamped `2.1.0 @ <commit that says 2.0.0>` and the
    provenance is unfalsifiable prose from the moment it is written.
    """
    if not SHA_RE.match(sha):
        raise ProvenanceError(
            f"cannot pin a template version to {sha!r} — birth needs a real template commit"
        )
    try:
        version = git(template_src, "show", f"{sha}:{TEMPLATE_VERSION_PATH}").strip()
    except ProvenanceError as exc:
        raise ProvenanceError(
            f"commit {sha[:12]} of the template carries no {TEMPLATE_VERSION_PATH}: {exc}"
        ) from exc
    if not VERSION_RE.match(version):
        raise ProvenanceError(f"commit {sha[:12]} records an unusable template version {version!r}")
    return version


def assert_version_agrees(*, assembled: str, pinned: str, sha: str) -> None:
    """The version in the tree must be the version at the recorded SHA.

    This is the invariant that catches a stale `.l9-template-version` BEFORE a
    remote repository exists. Without it a birth happily records
    `template_sha: <a commit that says 2.0.0>` beside `template_version: 2.1.0`,
    and nothing in the system can ever say which half was wrong.
    """
    if assembled != pinned:
        raise ProvenanceError(
            f"template version disagreement: the assembled repository carries "
            f"{assembled!r} but template commit {sha[:12]} records {pinned!r} — "
            f"birth will not stamp provenance it cannot prove. Commit "
            f"{TEMPLATE_VERSION_PATH}, or birth from a clean template checkout."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Digests — one algorithm, two callers
# ─────────────────────────────────────────────────────────────────────────────


def canonical_json(doc: Mapping[str, object]) -> bytes:
    """Byte-stable JSON: sorted keys, no insignificant whitespace."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")


def receipt_digest(receipt: Mapping[str, object]) -> str:
    """sha256 over the receipt WITHOUT its own digest field."""
    body = {key: value for key, value in receipt.items() if key != "digest"}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def manifest_digest(files: Mapping[str, bytes]) -> str:
    """sha256 over `<sha256>  <path>` lines, one per file, path-sorted.

    The same shape as `MANIFEST.sha256`, and for the same reason: a digest a
    human can reproduce with `sha256sum` when they do not trust the tool.
    """
    lines = [f"{hashlib.sha256(body).hexdigest()}  {rel}" for rel, body in sorted(files.items())]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def git_tracked_paths(root: Path) -> list[str]:
    """Exactly the paths `git add -A` would stage — cached plus unignored untracked.

    Defining the manifest over git's own answer, rather than over a filesystem
    walk, is what keeps the birth-time digest equal to the digest of the commit
    that lands: a gitignored build artifact lying in the work directory cannot
    make the two disagree.
    """
    out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({rel for rel in out.split("\0") if rel})


def _blob_bytes(path: Path) -> bytes:
    """A file's content, or a symlink's target — matching what git stores."""
    if path.is_symlink():
        return os.readlink(path).encode("utf-8")
    return path.read_bytes()


def worktree_manifest(root: Path, *, exclude: Iterable[str] = ()) -> dict[str, bytes]:
    skip = set(exclude)
    files: dict[str, bytes] = {}
    for rel in git_tracked_paths(root):
        if rel in skip:
            continue
        path = root / rel
        if path.is_symlink() or path.is_file():
            files[rel] = _blob_bytes(path)
    return files


def commit_manifest(root: Path, commit: str, *, exclude: Iterable[str] = ()) -> dict[str, bytes]:
    """Every blob in a commit's tree, read in one `git cat-file --batch`."""
    skip = set(exclude)
    listing = git(root, "ls-tree", "-r", "-z", "--name-only", commit)
    paths = sorted(rel for rel in listing.split("\0") if rel and rel not in skip)
    return _cat_blobs(root, commit, paths)


def _cat_blobs(root: Path, commit: str, paths: list[str]) -> dict[str, bytes]:
    if not paths:
        return {}
    stdin = "".join(f"{commit}:{rel}\n" for rel in paths).encode("utf-8")
    proc = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ProvenanceError(
            f"git cat-file --batch failed: {proc.stderr.decode(errors='replace')}"
        )
    out = proc.stdout
    found: dict[str, bytes] = {}
    pos = 0
    for rel in paths:
        end = out.find(b"\n", pos)
        if end < 0:
            raise ProvenanceError(f"truncated cat-file output at {rel}")
        header = out[pos:end].decode("utf-8", errors="replace").split()
        if len(header) != 3 or header[1] != "blob":
            raise ProvenanceError(f"{rel} is not a blob in {commit[:12]}: {' '.join(header)}")
        size = int(header[2])
        start = end + 1
        found[rel] = out[start : start + size]
        pos = start + size + 1
    return found


def read_blob(root: Path, commit: str, rel: str) -> bytes | None:
    """One file's bytes at a commit, or None when the commit does not carry it."""
    try:
        return _cat_blobs(root, commit, [rel])[rel]
    except ProvenanceError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# The records themselves
# ─────────────────────────────────────────────────────────────────────────────


def build_receipt(
    *,
    repository: str,
    repo_class: str,
    template_sha: str,
    template_version: str,
    org_policy_sha: str,
    payload_mode: str,
    manifest_sha256: str,
    born_at: str,
) -> dict[str, object]:
    """The birth receipt, digest included.

    Three independently comparable things come out of one birth: this receipt,
    the root commit that carries its digest in a trailer, and the repository
    contents the digest covers. A mismatch anywhere means the birth is not what
    it says it is.
    """
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "repository": repository,
        "repo_class": repo_class,
        "template": {
            "repository": TEMPLATE_REPO,
            "sha": template_sha,
            "version": template_version,
        },
        "org_policy": {"repository": ORG_PROFILE_REPO, "sha": org_policy_sha},
        "payload_mode": payload_mode,
        "manifest_sha256": manifest_sha256,
        "born_at": born_at,
    }
    receipt["digest"] = receipt_digest(receipt)
    return receipt


def render_receipt_json(receipt: Mapping[str, object]) -> str:
    """Pretty on disk, canonical for the digest. The digest never reads this."""
    return json.dumps(receipt, indent=2, sort_keys=True) + "\n"


def render_marker(
    *,
    profile_name: str,
    repository: str,
    template_sha: str,
    template_version: str,
    org_profile_sha: str,
    born_at: str,
) -> str:
    """The class declaration the organization reads, plus the birth record.

    The top four keys are the organization's contract and are parsed over there
    with a single regex on `profile:`. Everything under `birth:` is this
    template's provenance record: immutable, and never rewritten by
    reconciliation.
    """
    return (
        "# Organization birth profile marker + immutable birth record.\n"
        "#\n"
        "# This repository declares its own class; Quantum-L9/.github decides what that\n"
        "# class receives (INHERIT / MATERIALIZE / REMOTE APPLY / FORBID), per\n"
        "# policies/repo-classes.yml over there.\n"
        "#\n"
        "# The `birth:` block below is IMMUTABLE. It records the exact pair of commits\n"
        "# this repository was born from and must still describe them years from now.\n"
        "# What the repository is expected to conform to TODAY is a different question,\n"
        "# answered by .l9/template-state.yaml — reconciliation moves that file and never\n"
        "# this one.\n"
        f"schema: {MARKER_SCHEMA}\n"
        f"profile: {profile_name}\n"
        f"authority: {ORG_PROFILE_REPO}\n"
        f"repository: {repository}\n"
        "birth:\n"
        f"  template_repository: {TEMPLATE_REPO}\n"
        f"  template_sha: {template_sha}\n"
        f"  template_version: {template_version}\n"
        f"  org_policy_sha: {org_profile_sha}\n"
        f"  born_at: {born_at}\n"
    )


def render_template_state(
    *,
    template_sha: str,
    template_version: str,
    org_policy_sha: str,
    reconciled_at: str,
    reconciled_by: str = "birth",
) -> str:
    """What this repository is expected to conform to NOW.

    Born equal to the birth record and mutable from then on. A reconciliation PR
    that moves a repository onto a newer template baseline updates THIS file;
    `.l9/org-birth-profile.yaml` keeps saying where the repository came from, so
    the history reads born from X -> reconciled to Y -> reconciled to Z.
    """
    return (
        "# Current template / organization conformance state. MUTABLE.\n"
        "#\n"
        "# This is not provenance. It is the baseline this repository is expected to\n"
        "# match today, and a reconciliation PR is what moves it. For where this\n"
        "# repository came from, read the immutable `birth:` block in\n"
        "# .l9/org-birth-profile.yaml — that one never changes.\n"
        f"schema: {TEMPLATE_STATE_SCHEMA}\n"
        "template:\n"
        f"  repository: {TEMPLATE_REPO}\n"
        f"  current_sha: {template_sha}\n"
        f"  current_version: {template_version}\n"
        "policy:\n"
        f"  repository: {ORG_PROFILE_REPO}\n"
        f"  current_sha: {org_policy_sha}\n"
        f"last_reconciled_at: {reconciled_at}\n"
        f"reconciled_by: {reconciled_by}\n"
    )


def parse_flat_yaml(text: str | None) -> dict[str, object]:
    """A two-level reader for the provenance files this template writes.

    Deliberately not a YAML parser. These files are written by one function in
    this module, in one shape — `key: value` at the top level and one level of
    indented children under a bare `key:`. Reading them with exactly that much
    grammar keeps the birth record free of a runtime dependency on both sides,
    and means anything more exotic in the file is not something birth wrote.
    """
    doc: dict[str, object] = {}
    parent: str | None = None
    for raw in (text or "").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.strip().partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if raw[:1].isspace():
            block = doc.get(parent) if parent else None
            if isinstance(block, dict):
                block[key] = value
            continue
        if value:
            doc[key] = value
            parent = None
        else:
            doc[key] = {}
            parent = key
    return doc


def birth_block(marker_text: str | None) -> dict[str, object]:
    block = parse_flat_yaml(marker_text).get("birth")
    return block if isinstance(block, dict) else {}


# ─────────────────────────────────────────────────────────────────────────────
# Commit trailers — the root commit's copy of the record
# ─────────────────────────────────────────────────────────────────────────────


def commit_trailers(receipt: Mapping[str, object]) -> list[str]:
    template = receipt.get("template")
    template = template if isinstance(template, dict) else {}
    policy = receipt.get("org_policy")
    policy = policy if isinstance(policy, dict) else {}
    return [
        f"{TRAILER_RECEIPT}: sha256:{receipt.get('digest', '')}",
        f"{TRAILER_TEMPLATE}: {template.get('sha', '')}",
        f"{TRAILER_TEMPLATE_VERSION}: {template.get('version', '')}",
        f"{TRAILER_POLICY}: {policy.get('sha', '')}",
        f"{TRAILER_CLASS}: {receipt.get('repo_class', '')}",
    ]


def parse_trailers(message: str | None) -> dict[str, str]:
    """The `Key: value` lines in the commit message's trailing block.

    Git's own rule, and for git's own reason: the trailer block is the LAST
    paragraph, and a message that is only one paragraph has none — its first
    line is a subject. Without that, `chore: birth` parses as a trailer named
    `chore`, and a commit carrying no birth record at all looks like it carries
    one.
    """
    lines = (message or "").strip().splitlines()
    paragraph: list[str] = []
    for line in reversed(lines):
        if not line.strip():
            break
        paragraph.insert(0, line.strip())
    if not paragraph or len(paragraph) == len(lines):
        return {}
    matches = [_TRAILER_RE.match(line) for line in paragraph]
    if not all(matches):
        return {}
    return {m.group(1): m.group(2).strip() for m in matches if m}


def expected_trailers(receipt: Mapping[str, object]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in commit_trailers(receipt):
        key, _, value = line.partition(":")
        parsed[key.strip()] = value.strip()
    return parsed


# ─────────────────────────────────────────────────────────────────────────────
# Protected paths
# ─────────────────────────────────────────────────────────────────────────────


def birth_path_collisions(payload: Path) -> list[str]:
    """Engine-owned provenance paths a product payload is trying to supply."""
    return sorted(rel for rel in ENGINE_OWNED_PATHS if (payload / rel).exists())


def assert_payload_owns_no_birth_paths(payload: Path) -> None:
    """Fail closed. A payload never gets to write the record of its own birth.

    Silently overwriting is the failure this exists to remove: a payload copied
    out of an older repository carries that repository's `.l9-template-version`
    and its birth marker, the overlay wins on collision, and the newborn is born
    claiming a provenance that belongs to a different repository.
    """
    collision = birth_path_collisions(payload)
    if collision:
        raise ProvenanceError(
            f"payload attempted to own protected birth paths: {collision} — "
            "birth provenance is written by the birth engine, after the payload, "
            "and is never inherited from a product tree"
        )
