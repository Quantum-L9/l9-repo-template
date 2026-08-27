#!/usr/bin/env python3
"""One-command repository birth for non-Constellation Quantum-L9 Python repos.

`make new-repo` runs this. When it returns PASS the repository is *born* — not
"created, now go do seven other things". The eight stages below are a state
machine, and every one of them either passes or stops the birth.

    [1] PREFLIGHT              tools, auth, identity validation, name is free
    [2] ASSEMBLE LOCALLY       template + identity stamp + optional payload
    [3] FINALIZE               LICENSE, uv lock, rules, manifest, metadata
    [4] APPLY ORG BIRTH PROFILE current Quantum-L9/.github, class capabilities
    [5] STAMP BIRTH PROVENANCE the immutable record, written AFTER the payload
    [6] VALIDATE BEFORE CREATION  the full product gate, on the newborn
    [7] CREATE GITHUB REPOSITORY  commit with provenance trailers, create, push
    [8] REMOTE ORG BOOTSTRAP      labels, settings, applicable seeding
    [9] REMOTE ATTESTATION        read the remote back and prove it

`uv lock` is stage 3, not something a product author is asked to remember. A
birth invariant belongs to the birth engine.

Stage 5 exists because ORDER IS THE CONTRACT. Provenance is generated output, so
it is stamped after the product payload has been overlaid and after the
organization has had its say — never copied in with the template and hoped over.
A payload may not carry any of it: `scripts/birth-runner/birth_provenance.py`
names the protected paths and the birth refuses a payload that supplies one,
rather than letting an overlay silently overwrite the record of the newborn's own
birth with some older repository's.

Stage 5 also splits two questions that were previously one file's job:

    .l9-template-version         IMMUTABLE  what this repository was born from
    .l9/org-birth-profile.yaml   IMMUTABLE  class + the exact pair of commits
    .l9/birth-receipt.json       IMMUTABLE  the whole record, plus a digest
    .l9/template-state.yaml      MUTABLE    what it must conform to TODAY

Reconciliation moves the last one. Nothing moves the first three, so
"is this repository genuinely what it claims it was born from?" keeps its answer
years after "is it up to date?" has changed its own.

Ownership, unchanged by this script:

    l9-repo-template     owns HOW A REPO IS BORN
    Quantum-L9/.github   owns WHAT THE ORGANIZATION REQUIRES
    l9-ci-core           owns HOW CI EXECUTES
    l9-ci-control-plane  owns WHICH CI APPLIES WHERE
    the product repo     owns ITS PRODUCT

This script never decides what the organization requires. It reads
`policies/repo-classes.yml` from Quantum-L9/.github at a recorded SHA and
applies it.

Nor does it decide what a product owns. A PAYLOAD that is a standalone
repository is AUTHORITATIVE over its product tree: the template's example
product — the FastAPI service, the Docker runtime, the local observability
stack — is not inherited by a repository that never asked for it. What is
chassis and what is example is declared in
`scripts/birth-runner/payload-ownership.yaml`, not inferred here. A partial
payload keeps the original additive-overlay semantics.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def _load_sibling(name: str):
    """Load a module that lives next to this file, wherever this file lives.

    Not a bare `import`: that resolves for free when the script is executed
    directly (sys.path[0] is the script's directory) and fails when a fixture,
    a renamed tree, or a test harness loads this file by path instead. The
    provenance module is not optional, so it is located relative to THIS file
    rather than to whatever the interpreter's search path happens to be.
    """
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the birth provenance module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The engine that WRITES provenance and the checker that VERIFIES it share one
# module deliberately: two copies of a digest algorithm are two digests.
prov = _load_sibling("birth_provenance")

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ORG = "Quantum-L9"
ORG_PROFILE_REPO = "Quantum-L9/.github"
ORG_PROFILE_PATH = "policies/repo-classes.yml"
PYPROJECT = "pyproject.toml"
MARKER_PATH = prov.MARKER_PATH
VERIFY_BIRTH = "scripts/birth-runner/verify_birth_integrity.py"
# The template's own answer to "what does a product inherit from me?". Read from
# the template source, never from the payload: a payload does not get to widen
# the set of template surfaces it silently keeps.
OWNERSHIP_PATH = "scripts/birth-runner/payload-ownership.yaml"
SEED_BRANCH = "chore/auto-seed-governance"
# A licence that names one repository is wrong in every other repository. The
# org consumer template carried this notice; birth copies that file in as
# canonical, so the assertion belongs in the birth engine too, not only upstream.
POISONED_LICENSE_NOTICE = "applies only to the Quantum-L9/.github repository"
# The org taxonomy is 33 labels; require most rather than an exact count, so
# adding one label upstream does not fail every birth.
MIN_ORG_LABELS = 20


def default_work_dir() -> Path:
    """A private, user-owned birth workspace.

    Never a fixed path under /tmp. A world-writable directory with a
    predictable name lets any local user pre-create `<workdir>/<repo>` — as a
    symlink, or with their own contents — before the birth runs, and the
    engine would then assemble a repository inside it and push the result.
    `$XDG_STATE_HOME` (or `~/.local/state`) is user-owned, and the directory is
    created 0700 so a pre-existing world-readable one is not silently reused.
    """
    base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    root = Path(base) / "l9" / "births"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


BIRTH_PROFILE_CLASS = "non_constellation_python"
CANONICAL_LICENSE = "LICENSE"

# Directories never carried from the template into a newborn. `.git` would make
# the newborn a fork of the template's history; the rest is machine state.
COPY_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".eggs",
        "node_modules",
    }
)

# Build metadata carries the *template's* package name. Copying it would hand a
# newborn a stale `l9_example_pkg.egg-info` describing a package it does not
# have.
COPY_EXCLUDE_SUFFIXES = (".egg-info",)

# Agent session scaffolding, projected into whatever checkout the bootstrap ran
# in. It is not template content and a newborn must not inherit it: `.claude/`
# carries symlinks into the governance clone at an absolute machine path and a
# copy of the governance command/skill library, and `.mcp.json` is 0600
# environment configuration. Before this exclusion a birth run from a governed
# workspace copied all of it in, `git add -A` staged it, and it landed in the
# newborn's ROOT COMMIT — the one commit that is supposed to be attestable
# provenance and nothing else.
#
# Excluded from the TEMPLATE copy only. A product payload that genuinely owns a
# `.claude/` directory still overlays it; that is the product's file, not this
# machine's.
TEMPLATE_EXCLUDE_TOP_LEVEL = frozenset({".claude", ".mcp.json"})

REPO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
PKG_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MARKER_PROFILE_RE = re.compile(r"^profile:[ \t]*[\"']?([A-Za-z0-9_-]+)[\"']?[ \t]*$", re.M)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class BirthError(RuntimeError):
    """A stage refused to continue. The message is the operator-facing reason."""


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers — no I/O, unit-tested without git, gh, or a network.
# ─────────────────────────────────────────────────────────────────────────────


def validate_repo_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise BirthError("REPO is required (e.g. REPO=l9-observability-core)")
    if not REPO_NAME_RE.match(name):
        raise BirthError(f"invalid REPO {name!r}: expect GitHub repository name characters")
    if name.endswith(".git"):
        raise BirthError(f"invalid REPO {name!r}: drop the .git suffix")
    return name


def validate_package_name(pkg: str) -> str:
    pkg = (pkg or "").strip()
    if not pkg:
        raise BirthError("PKG is required (e.g. PKG=l9_observability_core)")
    if not PKG_NAME_RE.match(pkg):
        raise BirthError(f"invalid PKG {pkg!r}: expect snake_case Python identifier")
    if not pkg.isidentifier() or pkg == "l9_example_pkg":
        raise BirthError(f"invalid PKG {pkg!r}: must be a fresh Python identifier")
    return pkg


def validate_description(desc: str) -> str:
    desc = (desc or "").strip()
    if not desc:
        raise BirthError("DESC is required (one-line description)")
    if "CHANGE_ME" in desc or "CHANGE ME" in desc:
        raise BirthError("DESC still carries a placeholder")
    return desc


def parse_json_in_yaml(text: str) -> dict:
    """Parse the JSON-in-YAML org policy.

    Full-line ``#`` comments are stripped so the policy can document itself.
    Identical contract to ``ops/repo-class-profile.js`` on the organization
    side: one file, two languages, zero YAML dependency in either.
    """
    if not text or not text.strip():
        raise BirthError("org repo-classes policy is empty")
    stripped = re.sub(r"^[ \t]*#.*$", "", text, flags=re.M)
    try:
        doc = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise BirthError(f"org repo-classes policy is not JSON-in-YAML: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("classes"), dict):
        raise BirthError("org repo-classes policy has no classes map")
    return doc


def match_pattern(patterns: list[str], dest: str) -> str | None:
    """Exact path, or one trailing ``/**`` directory prefix. No glob syntax.

    A birth contract that needs a regex to explain what a repository receives
    is not a contract.
    """
    for pattern in patterns or ():
        if not pattern:
            continue
        if pattern == dest:
            return pattern
        if pattern.endswith("/**") and dest.startswith(pattern[:-2]):
            return pattern
    return None


def resolve_profile(doc: dict, class_name: str | None) -> dict:
    """Resolve one class, strictly.

    Birth is strict where a sweep is lenient: a typo at birth must stop the
    birth, not silently fall back to a wider default payload.
    """
    known = sorted(doc["classes"])
    name = class_name or doc.get("default_class")
    if name not in doc["classes"]:
        raise BirthError(f"unknown repo class {name!r} (known: {', '.join(known)})")
    cls = doc["classes"][name]
    return {
        "name": name,
        "description": cls.get("description", ""),
        "seed_categories": list(cls.get("seed_categories") or []),
        "inherit": list(cls.get("inherit") or []),
        "forbid": list(cls.get("forbid") or []),
        "remote_apply": dict(cls.get("remote_apply") or {}),
        "mandatory_files_waive": list(cls.get("mandatory_files_waive") or []),
        "marker_path": doc.get("marker_path", MARKER_PATH),
    }


def parse_marker_profile(text: str | None) -> str | None:
    if not text:
        return None
    found = MARKER_PROFILE_RE.search(text)
    return found.group(1) if found else None


def forbidden_present(root: Path, profile: dict) -> list[str]:
    """Every FORBID pattern that actually exists in an assembled tree.

    FORBID is an assertion about the repository, not only a filter on a seed
    payload: a forbidden path can arrive from a product payload overlay just as
    easily as from a seeder.
    """
    hits: list[str] = []
    for pattern in profile["forbid"]:
        probe = pattern[:-3] if pattern.endswith("/**") else pattern
        if (root / probe).exists():
            hits.append(pattern)
    return hits


# The marker is rendered by the shared provenance module: the checker has to
# read exactly what the engine wrote, so one function writes it.
render_marker = prov.render_marker


@dataclass
class StageResult:
    key: str
    label: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


@dataclass
class BirthReceipt:
    org: str = ""
    repository: str = ""
    package: str = ""
    description: str = ""
    template_repo: str = "Quantum-L9/l9-repo-template"
    template_sha: str = "unknown"
    template_version: str = "unknown"
    org_profile_repo: str = ORG_PROFILE_REPO
    org_profile_sha: str = "unknown"
    birth_profile: str = ""
    payload: str = ""
    payload_mode: str = "none"
    workdir: str = ""
    head_sha: str = "unknown"
    born_at: str = ""
    manifest_sha256: str = ""
    # The birth receipt COMMITTED INTO the newborn (`.l9/birth-receipt.json`).
    # This run receipt is an operator report and lives in the work directory;
    # that one is the repository's own permanent record and carries the digest
    # the root commit's trailer names.
    birth_receipt: dict = field(default_factory=dict)
    materialized: list[str] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)

    def record(self, key: str, label: str, status: str, detail: str = "") -> StageResult:
        result = StageResult(key, label, status, detail)
        self.stages.append(result)
        return result

    @property
    def failed(self) -> list[StageResult]:
        return [s for s in self.stages if s.status == "FAIL"]

    def to_dict(self) -> dict:
        return {
            "schema": "l9.repo-birth-receipt/v1",
            "born_at": self.born_at,
            "template": {
                "repository": self.template_repo,
                "sha": self.template_sha,
                "template_version": self.template_version,
            },
            "organization": {
                "repository": self.org_profile_repo,
                "sha": self.org_profile_sha,
                "birth_profile": self.birth_profile,
            },
            "product": {
                "repository": f"{self.org}/{self.repository}" if self.org else self.repository,
                "package": self.package,
                "description": self.description,
                "payload": self.payload,
                "payload_mode": self.payload_mode,
            },
            "birth_receipt": dict(self.birth_receipt),
            "manifest_sha256": self.manifest_sha256,
            "workdir": self.workdir,
            "head_sha": self.head_sha,
            "materialized": list(self.materialized),
            "result": "PASS" if not self.failed else "FAIL",
            "stages": [
                {"key": s.key, "label": s.label, "status": s.status, "detail": s.detail}
                for s in self.stages
            ],
        }


_GROUPS = (
    ("preflight", "Preflight"),
    ("assemble", "Assemble"),
    ("finalize", "Finalization"),
    ("org", "Organization"),
    ("stamp", "Provenance"),
    ("validate", "Validation"),
    ("github", "GitHub"),
)


def render_receipt(receipt: BirthReceipt) -> str:
    lines: list[str] = ["", "L9 REPOSITORY BIRTH"]
    lines.append("Template")
    lines.append(f"  {receipt.template_repo:<22} {receipt.template_sha}")
    lines.append(f"  {'template_version':<22} {receipt.template_version}")
    lines.append("Organization")
    lines.append(f"  {receipt.org_profile_repo:<22} {receipt.org_profile_sha}")
    lines.append(f"  {'birth_profile':<22} {receipt.birth_profile}")
    lines.append("Product")
    lines.append(f"  {'repository':<22} {receipt.org}/{receipt.repository}")
    lines.append(f"  {'package':<22} {receipt.package}")
    if receipt.payload:
        lines.append(f"  {'payload':<22} {receipt.payload} ({receipt.payload_mode})")
    if receipt.birth_receipt:
        lines.append("Birth record")
        lines.append(f"  {'receipt digest':<22} sha256:{receipt.birth_receipt.get('digest', '')}")
        lines.append(f"  {'contents digest':<22} sha256:{receipt.manifest_sha256}")

    for prefix, heading in _GROUPS:
        group = [s for s in receipt.stages if s.key.startswith(f"{prefix}.")]
        if not group:
            continue
        lines.append(heading)
        for stage in group:
            lines.append(f"  {stage.label:<22} {stage.status}")
    lines.append(f"BIRTH: {'PASS' if not receipt.failed else 'FAIL'}")
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────────────


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=capture,
        text=True,
        env=merged,
    )
    if check and proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthError(f"{' '.join(cmd)} failed ({proc.returncode})\n{detail[-2000:]}")
    return proc


def _is_machine_state(rel: Path) -> bool:
    return any(part in COPY_EXCLUDE_DIRS for part in rel.parts) or any(
        part.endswith(COPY_EXCLUDE_SUFFIXES) for part in rel.parts
    )


def _is_session_scaffolding(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0] in TEMPLATE_EXCLUDE_TOP_LEVEL


def copy_tree(src: Path, dest: Path) -> int:
    """Copy the template working tree, skipping git, machine state, and session
    scaffolding."""
    copied = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if _is_machine_state(rel) or _is_session_scaffolding(rel):
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file() or path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target, follow_symlinks=False)
            copied += 1
    return copied


def overlay_payload(payload: Path, dest: Path) -> list[str]:
    """Overlay product files onto the assembled scaffold.

    The payload wins on collision — the template is the chassis, the payload is
    the product. Git and machine state are never carried across.
    """
    written: list[str] = []
    for path in sorted(payload.rglob("*")):
        rel = path.relative_to(payload)
        if _is_machine_state(rel):
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            written.append(rel.as_posix())
    return written


def load_ownership(template_src: Path) -> dict:
    """Read the template's payload-ownership contract.

    JSON-in-YAML, exactly like the organization policy, and for the same reason:
    the file has to explain itself in comments and this script has no YAML
    dependency. Fails closed — a missing or unreadable contract must stop a
    birth, not silently fall back to "the template owns everything", which is
    the defect this contract exists to remove.
    """
    path = template_src / OWNERSHIP_PATH
    if not path.is_file():
        raise BirthError(
            f"template has no payload ownership contract at {OWNERSHIP_PATH} — "
            "an authoritative payload cannot be reconciled without it"
        )
    stripped = re.sub(r"^[ \t]*#.*$", "", path.read_text(encoding="utf-8"), flags=re.M)
    try:
        doc = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise BirthError(f"{OWNERSHIP_PATH} is not JSON-in-YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise BirthError(f"{OWNERSHIP_PATH} is not a mapping")
    for key in ("repository_shape", "product", "chassis"):
        value = doc.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
            raise BirthError(f"{OWNERSHIP_PATH} has no usable {key!r} list")
    return doc


def is_repository_payload(payload: Path, ownership: dict) -> bool:
    """Is this payload a standalone repository, or a fragment?

    Positive identification only, against the declared `repository_shape`. Every
    listed path must be present. A payload that is merely large, or that happens
    to carry a `src/` directory, stays an additive overlay — the pre-existing
    behavior, which products already depend on.
    """
    return all((payload / rel).exists() for rel in ownership["repository_shape"])


def _relative_files(root: Path) -> list[str]:
    """Every real file under `root`, repository-relative, machine state skipped."""
    found: list[str] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if _is_machine_state(rel):
            continue
        if path.is_file() or path.is_symlink():
            found.append(rel.as_posix())
    return sorted(found)


def payload_package_dirs(payload: Path) -> list[str]:
    """The Python packages a repository-shaped payload declares under `src/`."""
    src = payload / "src"
    if not src.is_dir():
        return []
    return sorted(
        child.name
        for child in src.iterdir()
        if child.is_dir()
        and child.name not in COPY_EXCLUDE_DIRS
        and not child.name.endswith(COPY_EXCLUDE_SUFFIXES)
    )


def reconcile_product_ownership(dest: Path, payload: Path, ownership: dict) -> list[str]:
    """Make the payload authoritative over the product surfaces it owns.

    The overlay can only ever *overwrite*. It cannot express "this product does
    not have a Dockerfile", because there is no file in the payload with which
    to say so. Under an authoritative payload, absence says it: a `product`
    surface the payload does not supply is removed rather than inherited from
    the example product this template ships.

    Chassis and organization surfaces are untouched. The birth engine, the
    repository-execution facade, the canonical LICENSE, the class marker and the
    MATERIALIZE payload all survive — a product owns its product, not the
    factory that made it.

    Returns the removed paths, repository-relative and sorted.
    """
    supplied = set(_relative_files(payload))
    patterns = list(ownership["product"])
    removed: list[str] = []
    for rel in _relative_files(dest):
        if rel in supplied:
            continue
        if match_pattern(patterns, rel) is None:
            continue
        (dest / rel).unlink()
        removed.append(rel)
    _prune_emptied_dirs(dest, removed)
    return removed


def _prune_emptied_dirs(root: Path, removed: list[str]) -> None:
    """Drop the directories reconciliation itself emptied, and only those.

    Walking every directory in the tree would also collect one that was empty
    before the birth started; this walks up from each removed file instead, so a
    directory disappears only as a consequence of its own contents going.
    """
    for rel in removed:
        parent = (root / rel).parent
        while parent != root:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
            else:
                break


def git_head(root: Path) -> str:
    proc = run(["git", "-C", str(root), "rev-parse", "HEAD"], check=False)
    sha = (proc.stdout or "").strip()
    return sha if SHA_RE.match(sha) else "unknown"


def gh_json(args: list[str]) -> object:
    proc = run(["gh", *args])
    return json.loads(proc.stdout or "null")


def gh_json_safe(args: list[str]) -> object:
    """gh api returning parsed JSON, or None on any failure. Never raises."""
    proc = run(["gh", *args], check=False)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError:
        return None


def _remote_text(slug: str, path: str) -> str | None:
    """Decode a remote file's contents, or None when it cannot be read."""
    proc = run(["gh", "api", f"repos/{slug}/contents/{path}", "--jq", ".content"], check=False)
    if proc.returncode != 0:
        return None
    try:
        return base64.b64decode("".join((proc.stdout or "").split())).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


@dataclass
class BirthConfig:
    org: str
    repo: str
    pkg: str
    desc: str
    work_dir: Path
    payload: Path | None
    template_src: Path
    org_profile_src: Path | None
    repo_class: str
    remote: bool
    private: bool
    keep: bool
    receipt_path: Path | None
    bootstrap_timeout: int

    @property
    def slug(self) -> str:
        return f"{self.org}/{self.repo}"

    @property
    def dest(self) -> Path:
        return self.work_dir / self.repo


def _preflight_tools(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Every executable the chosen mode needs, and a usable gh session."""
    for tool in ("git", "python3", "uv"):
        if shutil.which(tool) is None:
            raise BirthError(f"{tool} not found on PATH")
    receipt.record("preflight.tools", "tools", "PASS", "git, python3, uv")

    # node runs the ORGANIZATION's seed payload builder in stage 4; a birth
    # cannot materialize org state without it.
    if shutil.which("node") is None:
        raise BirthError(
            "node not found on PATH — required to run the organization's seed payload builder"
        )

    if not (cfg.remote or cfg.org_profile_src is None):
        receipt.record("preflight.auth", "auth", "SKIP", "local birth, no gh needed")
        return
    if shutil.which("gh") is None:
        raise BirthError(
            "gh not found on PATH — required to read the org birth profile and to create "
            "the repository. Use --org-profile-src and --no-remote for a fully local birth."
        )
    # Probe with REST, not `gh auth status`. On a proxied surface the session
    # gateway serves REST but refuses GraphQL, and `gh auth status` verifies
    # over GraphQL — so it reports "The token in GH_TOKEN is invalid" while
    # every REST call this birth makes succeeds. GH_TOKEN there is a 14-char
    # placeholder; the proxy injects the real credential. Gating on auth status
    # fails a birth that would have worked.
    probe = run(["gh", "api", "user", "--jq", ".login"], check=False)
    login = (probe.stdout or "").strip()
    if probe.returncode != 0 or not login:
        raise BirthError(
            "GitHub REST is not reachable via gh — check credentials/proxy. "
            "(`gh auth status` is NOT authoritative on a GraphQL-restricted surface.)"
        )
    receipt.record("preflight.auth", "auth", "PASS", f"REST reachable as {login}")


def _preflight_sources(cfg: BirthConfig) -> None:
    """The template must be a pristine checkout, and the workspace must be free."""
    if not (cfg.template_src / PYPROJECT).is_file():
        raise BirthError(f"template source is not a repository checkout: {cfg.template_src}")
    if not (cfg.template_src / "src" / "l9_example_pkg").is_dir():
        raise BirthError(
            f"template source has already been renamed: {cfg.template_src} — "
            "birth needs a pristine l9-repo-template checkout"
        )
    if cfg.payload is not None:
        if not cfg.payload.is_dir():
            raise BirthError(f"PAYLOAD is not a directory: {cfg.payload}")
        # Fail here, not after a full tree copy: without the ownership contract
        # a repository-shaped payload cannot be told from a fragment.
        load_ownership(cfg.template_src)
        # And fail here rather than at stamping time: a payload carrying
        # `.l9-template-version` or a birth marker is almost always a tree copied
        # out of an older repository, and the overlay wins on collision. Reject
        # it while nothing has been assembled.
        prov.assert_payload_owns_no_birth_paths(cfg.payload)
    if cfg.dest.exists() and any(cfg.dest.iterdir()):
        raise BirthError(
            f"work directory already populated: {cfg.dest} — remove it or pass a different WORK_DIR"
        )


def _preflight_name_free(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Birth creates a repository; it does not adopt one that already exists."""
    if not cfg.remote:
        receipt.record("preflight.name", "name available", "SKIP", "local birth")
        return
    if run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False).returncode == 0:
        raise BirthError(
            f"{cfg.slug} already exists — birth creates a repository, it does not adopt one"
        )
    receipt.record("preflight.name", "name available", "PASS", f"{cfg.slug} is free")


def stage_preflight(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Tools, auth, identity, and a target name that is actually free."""
    _preflight_tools(cfg, receipt)
    # Identity was validated when the config was built; record it as evidence.
    receipt.record("preflight.identity", "identity", "PASS", f"{cfg.slug} / {cfg.pkg}")
    _preflight_sources(cfg)
    receipt.record(
        "preflight.provenance",
        "birth paths free",
        "PASS",
        f"{len(prov.ENGINE_OWNED_PATHS)} engine-owned path(s) unclaimed by the payload",
    )
    _preflight_name_free(cfg, receipt)


def stage_assemble(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Template + identity stamp + optional product payload."""
    cfg.dest.mkdir(parents=True, exist_ok=True)
    copied = copy_tree(cfg.template_src, cfg.dest)
    receipt.record("assemble.template", "template copied", "PASS", f"{copied} files")

    # No `git remote add origin` here. Stage 6 runs `gh repo create --source
    # --remote origin --push`, and gh's --remote flag CREATES that remote for
    # the source repository; pre-creating it makes two owners for one remote.
    # One operation owns remote-repo creation, origin creation, and the initial
    # push.
    run(["git", "init", "-q", "-b", "main"], cwd=cfg.dest)

    run(
        [
            sys.executable,
            "scripts/bootstrap_rename.py",
            "--pkg",
            cfg.pkg,
            "--org",
            cfg.org,
            "--repo",
            cfg.repo,
        ],
        cwd=cfg.dest,
    )
    receipt.record("assemble.identity", "identity stamped", "PASS", cfg.pkg)

    _stamp_description(cfg)
    receipt.record("assemble.description", "description", "PASS", cfg.desc[:48])

    status, detail = _assemble_payload(cfg, receipt)
    receipt.record("assemble.ownership", "payload ownership", status, detail)


def _assemble_payload(cfg: BirthConfig, receipt: BirthReceipt) -> tuple[str, str]:
    """Overlay the payload; return the ownership verdict for the caller to record.

    The overlay stage is recorded here and the ownership stage by the caller, so
    each stage key is written in exactly one place.
    """
    if cfg.payload is None:
        receipt.record("assemble.payload", "payload overlay", "SKIP", "no PAYLOAD given")
        receipt.payload_mode = "none"
        return "SKIP", "no PAYLOAD given"

    ownership = load_ownership(cfg.template_src)
    authoritative = is_repository_payload(cfg.payload, ownership)
    receipt.payload_mode = "authoritative" if authoritative else "additive"
    if authoritative:
        _assert_payload_package_matches(cfg)

    written = overlay_payload(cfg.payload, cfg.dest)
    receipt.record("assemble.payload", "payload overlay", "PASS", f"{len(written)} files")

    if not authoritative:
        # A fragment adds and overrides; it never speaks for what it omits.
        return "PASS", "additive overlay — payload is not repository-shaped"

    removed = reconcile_product_ownership(cfg.dest, cfg.payload, ownership)
    return "PASS", (
        f"authoritative — {len(removed)} template product surface(s) not owned by the payload"
        + (f": {', '.join(removed[:8])}" if removed else "")
    )


def _assert_payload_package_matches(cfg: BirthConfig) -> None:
    """PKG must name the package the authoritative payload actually ships.

    Under an authoritative payload the renamed template package is replaced by
    the payload's. If PKG names a different package, the replacement removes the
    renamed template package and installs one nothing points at — a birth that
    fails deep inside stage 5 with an import error, for a mistake visible here.
    """
    packages = payload_package_dirs(cfg.payload) if cfg.payload else []
    if packages and cfg.pkg not in packages:
        raise BirthError(
            f"PKG={cfg.pkg} is not the package this repository payload ships "
            f"({', '.join(packages)}) — an authoritative payload owns src/, so the "
            "names have to agree"
        )


def _stamp_description(cfg: BirthConfig) -> None:
    """Replace the template's own description with the product's.

    Only the `description = "..."` line in `[project]` is rewritten; prose that
    happens to quote the template description is left alone.
    """
    pyproject = cfg.dest / PYPROJECT
    text = pyproject.read_text(encoding="utf-8")
    escaped = cfg.desc.replace("\\", "\\\\").replace('"', '\\"')
    updated, count = re.subn(
        r'^description = ".*"$',
        f'description = "{escaped}"',
        text,
        count=1,
        flags=re.M,
    )
    if count:
        pyproject.write_text(updated, encoding="utf-8")


def _fetch_org_profile(cfg: BirthConfig) -> tuple[str, str]:
    """Return (policy text, org SHA) for the current Quantum-L9/.github.

    A local `--org-profile-src` records the SHA of that checkout when it is a
    git repository, so an offline birth still carries honest provenance rather
    than a fabricated one.
    """
    if cfg.org_profile_src is not None:
        policy = cfg.org_profile_src / ORG_PROFILE_PATH
        if not policy.is_file():
            raise BirthError(f"org profile source has no {ORG_PROFILE_PATH}: {cfg.org_profile_src}")
        return policy.read_text(encoding="utf-8"), git_head(cfg.org_profile_src)

    text = run(
        ["gh", "api", f"repos/{ORG_PROFILE_REPO}/contents/{ORG_PROFILE_PATH}", "--jq", ".content"]
    ).stdout

    decoded = base64.b64decode("".join(text.split())).decode("utf-8")
    head = gh_json(["api", f"repos/{ORG_PROFILE_REPO}/commits/HEAD", "--jq", "{sha:.sha}"])
    sha = head.get("sha", "unknown") if isinstance(head, dict) else "unknown"
    return decoded, sha


def _org_checkout(cfg: BirthConfig, org_sha: str) -> Path | None:
    """A Quantum-L9/.github working tree at the exact recorded SHA.

    Returned so the birth can run the ORGANIZATION's own payload builder
    (`ops/build-seed-payload.js`) rather than reimplementing the
    category -> destination mapping here. Two implementations of "what does
    this class receive" is two answers, and the seeder's is authoritative.
    """
    if cfg.org_profile_src is not None:
        return cfg.org_profile_src
    if shutil.which("gh") is None:
        return None
    dest = cfg.work_dir / f".org-github-{org_sha[:12]}"
    if (dest / "ops" / "build-seed-payload.js").is_file():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], cwd=dest)
    run(["git", "remote", "add", "origin", f"https://github.com/{ORG_PROFILE_REPO}.git"], cwd=dest)
    ref = org_sha if SHA_RE.match(org_sha) else "HEAD"
    run(["git", "fetch", "-q", "--depth=1", "origin", ref], cwd=dest)
    run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=dest)
    return dest


# With `node -e`, process.argv is [execPath, ...args] — there is no script path
# at argv[1] the way there is for a file, so the arguments start at index 1.
_PAYLOAD_JS = """
const fs = require('fs');
const path = require('path');
const root = process.argv[1];
const opts = JSON.parse(process.argv[2]);
process.chdir(root);
const { buildSeedPayload } = require(path.join(root, 'ops', 'build-seed-payload.js'));
process.stdout.write(JSON.stringify(buildSeedPayload({ fs, ...opts })));
"""


def build_org_payload(checkout: Path, profile: dict, cfg: BirthConfig) -> dict[str, str]:
    """Ask the organization what this class materializes. Do not guess.

    Runs `ops/build-seed-payload.js` from the pinned checkout, so INHERIT drops
    and FORBID throws inside the org's own code path — the same one the seeder
    uses. A FORBID hit surfaces here as a birth failure rather than as a red
    pull request opened against the newborn a week later.
    """
    if shutil.which("node") is None:
        raise BirthError(
            "node not found on PATH — required to run the organization's seed payload builder"
        )
    opts = {
        "profile": profile,
        "hasRootCodeowners": (cfg.dest / "CODEOWNERS").is_file(),
        "hasPython": (cfg.dest / PYPROJECT).is_file(),
        "hasPackageJson": (cfg.dest / "package.json").is_file(),
        "repository": cfg.slug,
    }
    proc = run(["node", "-e", _PAYLOAD_JS, str(checkout), json.dumps(opts)], check=False)
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthError(f"organization seed payload builder failed:\n{detail[-1500:]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise BirthError(f"seed payload builder returned non-JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BirthError("seed payload builder returned a non-object payload")
    return payload


def materialize_org_payload(root: Path, payload: dict[str, str]) -> tuple[list[str], list[str]]:
    """Write MATERIALIZE files into the newborn at `root`, missing-only.

    Missing-only matches the seeder's own semantics: the template and the
    product payload are closer to the repository than the org default is, so
    anything already present wins. Returns (written, kept).
    """
    written: list[str] = []
    kept: list[str] = []
    for dest, body in sorted(payload.items()):
        target = root / dest
        if target.exists():
            kept.append(dest)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(dest)
    return written, kept


def inherited_present(root: Path, profile: dict) -> list[str]:
    """INHERIT paths the repository is carrying its own copy of.

    Not fatal: GitHub prefers a repository-local file over the organization
    default, so a deliberate override is legal and supported. It is reported
    because an *accidental* copy is duplication the organization would then
    need a second synchronizer to clean up — which is the failure mode the
    whole INHERIT/MATERIALIZE split exists to avoid.
    """
    hits: list[str] = []
    for pattern in profile["inherit"]:
        probe = pattern[:-3] if pattern.endswith("/**") else pattern
        if (root / probe).exists():
            hits.append(pattern)
    return hits


def stage_finalize(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """The invariants a product author should never be asked to remember."""
    canonical = cfg.template_src / CANONICAL_LICENSE
    target = cfg.dest / CANONICAL_LICENSE
    if not canonical.is_file():
        raise BirthError("template has no canonical LICENSE")
    # The org LICENSE is repository-generic (Quantum AI Partners, no repo name),
    # so a payload that ships its own is overriding org policy, not customizing
    # a per-repo header. Restore the canonical text.
    replaced = target.is_file() and target.read_bytes() != canonical.read_bytes()
    shutil.copy2(canonical, target)
    # MUST FIX BEFORE BIRTH. The canonical text is copied into every newborn,
    # so a repository-specific notice in it is a licence that disclaims the
    # repository it governs — reproduced automatically, in every repository the
    # factory ever makes. This is the one thing a factory must never automate.
    if POISONED_LICENSE_NOTICE in target.read_text(encoding="utf-8"):
        raise BirthError(
            f"canonical LICENSE carries a repository-specific notice "
            f"({POISONED_LICENSE_NOTICE!r}) — it cannot govern {cfg.slug}. "
            "Fix templates/community-health/LICENSE upstream and the template LICENSE here."
        )
    receipt.record(
        "finalize.license",
        "license",
        "PASS",
        "restored canonical" if replaced else "canonical",
    )

    # Birth invariant, not a step someone remembers: the newborn must carry a
    # lock resolved for its own identity, or `uv lock --check` fails in CI on
    # day one.
    run(["uv", "lock"], cwd=cfg.dest)
    run(["uv", "sync", "--extra", "dev"], cwd=cfg.dest)
    receipt.record("finalize.lock", "uv.lock generated", "PASS", "uv lock + sync")

    run([str(_venv_python(cfg.dest)), "scripts/render_cursor_rules.py", "--force"], cwd=cfg.dest)
    receipt.record("finalize.rules", "generated rules", "PASS", "cursor rules rendered")

    run([str(_venv_python(cfg.dest)), "scripts/regenerate_runtime_manifest.py"], cwd=cfg.dest)
    receipt.record("finalize.manifest", "manifest", "PASS", "MANIFEST.sha256 regenerated")


def _venv_python(root: Path) -> Path:
    candidate = root / ".venv" / "bin" / "python"
    return candidate if candidate.is_file() else Path(sys.executable)


def stage_apply_org_profile(cfg: BirthConfig, receipt: BirthReceipt) -> dict:
    """Read the current organization contract and apply the applicable parts."""
    policy_text, org_sha = _fetch_org_profile(cfg)
    doc = parse_json_in_yaml(policy_text)
    profile = resolve_profile(doc, cfg.repo_class)

    receipt.org_profile_sha = org_sha
    receipt.birth_profile = profile["name"]

    # The class marker is NOT written here. It is birth provenance, and
    # provenance is stamped in stage 5 — after the product payload, after
    # MATERIALIZE, after everything that could still overwrite a file.
    receipt.record("org.profile", "org defaults", "PASS", f"{profile['name']} @ {org_sha[:12]}")

    # MATERIALIZE happens HERE, before validation and before the initial commit.
    # A repository that is "born, then offered an org patch" is not born with
    # the organization's current state; it is born incomplete and then sent a
    # pull request. The applicable org files belong in the first commit.
    checkout = _org_checkout(cfg, org_sha)
    if checkout is None:
        raise BirthError(
            "cannot reach a Quantum-L9/.github checkout to materialize org files — "
            "pass --org-profile-src for an offline birth"
        )
    payload = build_org_payload(checkout, profile, cfg)
    written, kept = materialize_org_payload(cfg.dest, payload)
    receipt.materialized = written
    receipt.record(
        "org.materialize",
        "org files materialized",
        "PASS",
        f"{len(written)} written, {len(kept)} already present"
        + (f": {', '.join(written)}" if written else ""),
    )

    # INHERIT is a claim that GitHub supplies the file org-wide. A repo-local
    # copy overrides that, which is legal but worth naming.
    overrides = inherited_present(cfg.dest, profile)
    receipt.record(
        "org.inherit",
        "inherit clean",
        "PASS",
        "no local copies of inherited files"
        if not overrides
        else f"repo-local override of {len(overrides)}: {', '.join(overrides)}",
    )

    # FORBID is an assertion about the assembled repository, not only a filter
    # on a seed payload — a product payload can introduce one just as easily.
    hits = forbidden_present(cfg.dest, profile)
    if hits:
        raise BirthError(
            f"assembled tree violates repo class {profile['name']}: {', '.join(hits)} — "
            "organization CI targeting belongs to l9-ci-core / l9-ci-control-plane"
        )
    receipt.record(
        "org.forbid",
        "forbid clean",
        "PASS",
        f"{len(profile['forbid'])} pattern(s) probed",
    )
    return profile


def stage_stamp_provenance(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Write the birth record — after the payload, after the organization, last.

    Everything before this stage can still overwrite a file: the template copy,
    the identity rename, the product overlay, MATERIALIZE. So the record of what
    made this repository is generated HERE, from values the engine resolved, and
    not copied in with the template and hoped over.

    Four files, two lifetimes:

        .l9-template-version        immutable   born-from version
        .l9/org-birth-profile.yaml  immutable   class + the exact commit pair
        .l9/birth-receipt.json      immutable   the whole record + its digest
        .l9/template-state.yaml     mutable     what it must conform to today

    The version is read from the template commit the record PINS, not from the
    template working tree, and the two must agree. That single invariant is what
    stops a repository being stamped `template_version: 2.1.0` beside a
    `template_sha` whose tree says `2.0.0` — a claim nothing downstream could
    ever check, discovered only when someone finally reads both.
    """
    marker_rel = str(profile.get("marker_path") or MARKER_PATH)
    if marker_rel not in prov.BIRTH_OWNED_PATHS:
        raise BirthError(
            f"the organization policy puts the class marker at {marker_rel!r}, which this "
            f"template does not protect as birth-owned ({sorted(prov.BIRTH_OWNED_PATHS)}) — "
            "a payload could overwrite it. Update the template's protected paths first."
        )

    version_file = cfg.dest / prov.TEMPLATE_VERSION_PATH
    pinned = prov.template_version_at(cfg.template_src, receipt.template_sha)
    prov.assert_version_agrees(
        assembled=version_file.read_text(encoding="utf-8").strip()
        if version_file.is_file()
        else "",
        pinned=pinned,
        sha=receipt.template_sha,
    )
    version_file.write_text(pinned + "\n", encoding="utf-8")
    receipt.template_version = pinned
    receipt.record(
        "stamp.version",
        "template version",
        "PASS",
        f"{pinned} @ {receipt.template_sha[:12]}",
    )

    marker = cfg.dest / marker_rel
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        prov.render_marker(
            profile_name=profile["name"],
            repository=cfg.slug,
            template_sha=receipt.template_sha,
            template_version=pinned,
            org_profile_sha=receipt.org_profile_sha,
            born_at=receipt.born_at,
        ),
        encoding="utf-8",
    )
    receipt.record(
        "stamp.marker",
        "birth marker",
        "PASS",
        f"{profile['name']} @ {receipt.org_profile_sha[:12]}",
    )

    (cfg.dest / prov.TEMPLATE_STATE_PATH).write_text(
        prov.render_template_state(
            template_sha=receipt.template_sha,
            template_version=pinned,
            org_policy_sha=receipt.org_profile_sha,
            reconciled_at=receipt.born_at,
        ),
        encoding="utf-8",
    )
    receipt.record("stamp.conformance", "conformance state", "PASS", f"conforms to {pinned}")

    # The contents digest is taken over exactly the files git is about to
    # commit — `ls-files --cached --others --exclude-standard` — so the number
    # recorded here is the number the root commit's tree hashes to. A gitignored
    # build artifact lying in the work directory cannot make the two disagree.
    manifest = prov.worktree_manifest(cfg.dest, exclude={prov.BIRTH_RECEIPT_PATH})
    receipt.manifest_sha256 = prov.manifest_digest(manifest)
    receipt.birth_receipt = prov.build_receipt(
        repository=cfg.slug,
        repo_class=profile["name"],
        template_sha=receipt.template_sha,
        template_version=pinned,
        org_policy_sha=receipt.org_profile_sha,
        payload_mode=receipt.payload_mode,
        manifest_sha256=receipt.manifest_sha256,
        born_at=receipt.born_at,
    )
    (cfg.dest / prov.BIRTH_RECEIPT_PATH).write_text(
        prov.render_receipt_json(receipt.birth_receipt),
        encoding="utf-8",
    )
    receipt.record(
        "stamp.receipt",
        "birth receipt",
        "PASS",
        f"{len(manifest)} files, sha256:{str(receipt.birth_receipt['digest'])[:12]}",
    )


def _verify_provenance(cfg: BirthConfig, receipt: BirthReceipt, key: str, label: str) -> None:
    """Run the newborn's own birth-integrity checker against the newborn.

    The same script the repository will carry forever, so what birth proves and
    what CI proves later are the same proof rather than two implementations that
    agree until they do not.
    """
    proc = run(
        [str(_venv_python(cfg.dest)), VERIFY_BIRTH, "--require-receipt"],
        cwd=cfg.dest,
        check=False,
    )
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        receipt.record(key, label, "FAIL", output.splitlines()[-1] if output else "")
        raise BirthError(f"birth integrity verification failed:\n{output[-1500:]}")
    receipt.record(
        key, label, "PASS", f"sha256:{str(receipt.birth_receipt.get('digest', ''))[:12]}"
    )


def stage_validate(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """The full product gate, run on the newborn, before anything is created."""
    python = _venv_python(cfg.dest)
    checks = (
        ("validate.inventory", "inventory", [str(python), "scripts/inventory_check.py"]),
        ("validate.hygiene", "hygiene", [str(python), "scripts/repo_hygiene_audit.py"]),
        (
            "validate.rules",
            "rules",
            [str(python), "scripts/render_cursor_rules.py", "--check"],
        ),
        ("validate.lint", "lint", [str(python), "-m", "ruff", "check", "."]),
        ("validate.format", "format", [str(python), "-m", "ruff", "format", "--check", "."]),
        ("validate.typecheck", "typecheck", [str(python), "-m", "mypy", "src"]),
        ("validate.tests", "tests", [str(python), "-m", "pytest", "-q"]),
        ("validate.lock", "lock", ["uv", "lock", "--check"]),
        (
            "validate.provenance",
            "birth provenance",
            [str(python), VERIFY_BIRTH, "--require-receipt"],
        ),
    )
    # The newborn carries the template's own test suite, including the birth
    # acceptance test. Running a birth inside a birth is pure recursion.
    nested = {"L9_SKIP_BIRTH_ACCEPTANCE": "1"}
    failures: list[str] = []
    for key, label, cmd in checks:
        proc = run(cmd, cwd=cfg.dest, check=False, env=nested)
        if proc.returncode == 0:
            receipt.record(key, label, "PASS")
        else:
            tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-1200:]
            receipt.record(key, label, "FAIL", tail.splitlines()[-1] if tail else "")
            failures.append(f"{label}:\n{tail}")
    if failures:
        raise BirthError(
            "validation failed before creation — nothing was created:\n\n" + "\n\n".join(failures)
        )


def stage_create(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Create the remote and push the finalized initial repository."""
    run(["git", "add", "-A"], cwd=cfg.dest)
    # The root commit carries the record too. Three independently comparable
    # things come out of one birth — the commit, the receipt, and the contents
    # the receipt's manifest digest covers — and a mismatch between any two of
    # them means the birth is not what it says it is.
    message = "\n".join(
        [
            f"chore: birth {cfg.slug} from l9-repo-template@{receipt.template_sha[:12]}",
            "",
            *prov.commit_trailers(receipt.birth_receipt),
        ]
    )
    run(
        [
            "git",
            "-c",
            "user.name=L9 Birth Runner",
            "-c",
            "user.email=noreply@quantum-l9.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=cfg.dest,
    )
    receipt.head_sha = git_head(cfg.dest)
    # The root commit only becomes checkable once it exists, so the full
    # three-way proof runs here — before anything is pushed, not after.
    _verify_provenance(cfg, receipt, "github.provenance", "birth record proved")

    visibility = "--private" if cfg.private else "--public"
    # One command owns all three: create the remote repository, create the
    # `origin` remote for this working tree, and push the initial commit.
    run(
        [
            "gh",
            "repo",
            "create",
            cfg.slug,
            visibility,
            "--description",
            cfg.desc,
            "--source",
            str(cfg.dest),
            "--remote",
            "origin",
            "--push",
        ]
    )
    receipt.record("github.create", "repository created", "PASS", cfg.slug)
    receipt.record("github.push", "initial push", "PASS", receipt.head_sha[:12])


def _newest_dispatch_run(workflow: str, since: str) -> dict | None:
    """The most recent workflow_dispatch run of `workflow` created at/after `since`.

    `gh workflow run` prints nothing useful and returns before a run exists, so
    the run has to be found by polling the runs list. Filtering on `since`
    keeps an older run of the same workflow from being mistaken for this one.
    """
    proc = run(
        [
            "gh",
            "api",
            f"repos/{ORG_PROFILE_REPO}/actions/workflows/{workflow}/runs"
            "?event=workflow_dispatch&per_page=20",
            "--jq",
            ".workflow_runs",
        ],
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        runs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    fresh = [r for r in runs if isinstance(r, dict) and str(r.get("created_at", "")) >= since]
    return max(fresh, key=lambda r: str(r.get("created_at", "")), default=None)


def _await_workflow(workflow: str, since: str, timeout_s: int) -> tuple[str, str]:
    """Block until one dispatched run reaches a conclusion.

    Returns (state, detail) where state is PASS / FAIL / TIMEOUT. A dispatch
    that GitHub merely ACCEPTED proves nothing: not that the run started, not
    that it succeeded, not that a single label was applied. Only `success`
    earns a PASS.
    """
    deadline = time.monotonic() + timeout_s
    run_id = None
    while time.monotonic() < deadline:
        found = _newest_dispatch_run(workflow, since)
        if found:
            run_id = found.get("id")
            status = str(found.get("status") or "")
            conclusion = str(found.get("conclusion") or "")
            if status == "completed":
                detail = f"run {run_id}: {conclusion or 'no conclusion'}"
                return ("PASS" if conclusion == "success" else "FAIL", detail)
        time.sleep(5)
    return ("TIMEOUT", f"run {run_id or '(never appeared)'} did not complete in {timeout_s}s")


def stage_remote_bootstrap(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Invoke the org capabilities now — and WAIT for them to finish.

    The organization contract says `make new-repo` dispatches the bootstrap
    workflow and waits for it. A dispatch returning 0 proves only that GitHub
    accepted the request; treating that as done let a birth report PASS while
    labels, settings and attestation had not run at all.
    """
    since = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    dispatches = [
        ("github.bootstrap", "org bootstrap", "repo-birth-bootstrap.yml"),
        ("github.seed", "org files seeded", "auto-seed-new-repo.yml"),
    ]
    for key, label, workflow in dispatches:
        cmd = [
            "gh",
            "workflow",
            "run",
            workflow,
            "--repo",
            ORG_PROFILE_REPO,
            "-f",
            f"target_repo={cfg.repo}",
            "-f",
            f"repo_class={profile['name']}",
            "-f",
            "dry_run=false",
        ]
        proc = run(cmd, check=False)
        if proc.returncode != 0:
            detail = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
            receipt.record(key, label, "FAIL", detail[-1] if detail else "dispatch failed")
            continue
        state, detail = _await_workflow(workflow, since, cfg.bootstrap_timeout)
        receipt.record(key, label, "PASS" if state == "PASS" else "FAIL", detail)


def _remote_has(slug: str, path: str) -> bool:
    """True when `path` exists on the remote default branch (file or directory)."""
    proc = run(["gh", "api", f"repos/{slug}/contents/{path}"], check=False)
    return proc.returncode == 0


def _attest_head(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """The remote default branch points at the commit birth actually made."""
    deadline = time.monotonic() + cfg.bootstrap_timeout
    remote_head = ""
    while time.monotonic() < deadline:
        proc = run(["gh", "api", f"repos/{cfg.slug}/commits/main", "--jq", ".sha"], check=False)
        remote_head = (proc.stdout or "").strip()
        if SHA_RE.match(remote_head):
            break
        time.sleep(3)
    receipt.record(
        "github.head",
        "remote HEAD",
        "PASS" if remote_head == receipt.head_sha else "FAIL",
        remote_head[:12] or "unreachable",
    )


def _attest_content(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Required files, a licence that governs THIS repo, and the class marker."""
    for rel in (
        "README.md",
        CANONICAL_LICENSE,
        MARKER_PATH,
        prov.TEMPLATE_VERSION_PATH,
        prov.BIRTH_RECEIPT_PATH,
        prov.TEMPLATE_STATE_PATH,
        PYPROJECT,
        "uv.lock",
    ):
        receipt.record(
            f"github.present.{rel}",
            f"remote {rel}",
            "PASS" if _remote_has(cfg.slug, rel) else "FAIL",
            rel,
        )

    # The licence that actually landed must not disclaim the repository it
    # governs. The org template carried a `.github`-only notice for a while,
    # and birth copies that file in as canonical — so a poisoned licence is
    # exactly what this factory would otherwise reproduce perfectly, forever.
    remote_license = _remote_text(cfg.slug, CANONICAL_LICENSE)
    receipt.record(
        "github.license",
        "license generic",
        "PASS" if remote_license and POISONED_LICENSE_NOTICE not in remote_license else "FAIL",
        "generic consumer licence" if remote_license else "unreadable or repo-specific",
    )

    remote_class = parse_marker_profile(_remote_text(cfg.slug, MARKER_PATH))
    receipt.record(
        "github.class",
        "org policy attested",
        "PASS" if remote_class == profile["name"] else "FAIL",
        remote_class or "marker unreadable",
    )

    # The birth receipt that landed must be the birth receipt that was written,
    # and must still hash to its own digest. Reading the local work directory
    # back would prove only that this process can read its own output.
    local_digest = str(receipt.birth_receipt.get("digest") or "")
    remote_digest, recomputed = _remote_receipt_digests(cfg.slug)
    receipt.record(
        "github.receipt",
        "birth receipt attested",
        "PASS"
        if local_digest and remote_digest == local_digest and recomputed == local_digest
        else "FAIL",
        f"sha256:{local_digest[:12]}"
        if remote_digest == local_digest == recomputed
        else f"remote says {remote_digest[:12] or '(unreadable)'}, hashes to {recomputed[:12]}",
    )


def _remote_receipt_digests(slug: str) -> tuple[str, str]:
    """(digest the remote receipt claims, digest it actually hashes to)."""
    text = _remote_text(slug, prov.BIRTH_RECEIPT_PATH)
    if not text:
        return "", ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return "", ""
    if not isinstance(parsed, dict):
        return "", ""
    return str(parsed.get("digest") or ""), prov.receipt_digest(parsed)


def _attest_org_state(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """MATERIALIZE present, FORBID absent, and no seeder PR left pending."""
    missing = [rel for rel in receipt.materialized if not _remote_has(cfg.slug, rel)]
    receipt.record(
        "github.materialized",
        "org files on remote",
        "PASS" if not missing else "FAIL",
        f"{len(receipt.materialized)} attested"
        if not missing
        else f"missing: {', '.join(missing)}",
    )

    leaked = [
        pattern
        for pattern in profile["forbid"]
        if _remote_has(cfg.slug, pattern[:-3] if pattern.endswith("/**") else pattern)
    ]
    receipt.record(
        "github.forbid",
        "forbid attested",
        "PASS" if not leaked else "FAIL",
        ", ".join(leaked) if leaked else f"{len(profile['forbid'])} probed",
    )

    # If the applicable org state really is in the initial commit, the seeder
    # has nothing left to offer. A pending seed PR means the repository was
    # born incomplete and then sent a patch.
    open_seed = gh_json_safe(
        ["api", f"repos/{cfg.slug}/pulls?state=open&head={cfg.org}:{SEED_BRANCH}", "--jq", "length"]
    )
    pending = open_seed if isinstance(open_seed, int) else 0
    receipt.record(
        "github.no_pending_seed",
        "no pending org PR",
        "PASS" if pending == 0 else "FAIL",
        "born with org state" if pending == 0 else f"{pending} seeder PR(s) still pending",
    )


def _attest_remote_apply(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Labels and settings are API state, proved by reading the API.

    Not by the bootstrap workflow having exited zero — that is the same
    dispatch-equals-done mistake one layer up.
    """
    if profile["remote_apply"].get("labels"):
        proc = run(
            ["gh", "api", f"repos/{cfg.slug}/labels?per_page=100", "--jq", "length"], check=False
        )
        count = int((proc.stdout or "0").strip() or 0) if proc.returncode == 0 else 0
        receipt.record(
            "github.labels",
            "labels applied",
            "PASS" if count >= MIN_ORG_LABELS else "FAIL",
            f"{count} labels on remote",
        )
    if profile["remote_apply"].get("repo_settings"):
        settings = gh_json_safe(["api", f"repos/{cfg.slug}"])
        ok = isinstance(settings, dict) and settings.get("delete_branch_on_merge") is True
        receipt.record(
            "github.settings",
            "repo settings applied",
            "PASS" if ok else "FAIL",
            "org policy applied" if ok else "settings not applied",
        )


def stage_attest(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Read the remote back. Local assembly proves nothing about GitHub.

    Every check queries the REMOTE. A birth that only re-inspects the work
    directory it just built has verified its own arithmetic, not the
    repository it claims to have created.
    """
    _attest_head(cfg, receipt)
    _attest_content(cfg, receipt, profile)
    _attest_org_state(cfg, receipt, profile)
    _attest_remote_apply(cfg, receipt, profile)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def build_config(args: argparse.Namespace) -> BirthConfig:
    return BirthConfig(
        org=(args.org or DEFAULT_ORG).strip(),
        repo=validate_repo_name(args.repo),
        pkg=validate_package_name(args.pkg),
        desc=validate_description(args.desc),
        work_dir=Path(args.work_dir).expanduser().resolve(),
        payload=Path(args.payload).expanduser().resolve() if args.payload else None,
        template_src=Path(args.template_src).expanduser().resolve(),
        org_profile_src=(
            Path(args.org_profile_src).expanduser().resolve() if args.org_profile_src else None
        ),
        repo_class=(args.repo_class or BIRTH_PROFILE_CLASS).strip(),
        remote=not args.no_remote,
        private=args.private,
        keep=args.keep,
        receipt_path=Path(args.receipt).expanduser().resolve() if args.receipt else None,
        bootstrap_timeout=args.bootstrap_timeout,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="new_repo.py",
        description="Birth a non-Constellation Quantum-L9 Python repository in one command.",
    )
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    parser.add_argument("--pkg", required=True, help="snake_case Python package name")
    parser.add_argument("--desc", required=True, help="one-line repository description")
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--payload", default=None, help="product files to overlay on the scaffold")
    parser.add_argument("--work-dir", default=os.environ.get("WORK_DIR") or str(default_work_dir()))
    parser.add_argument("--template-src", default=str(TEMPLATE_ROOT))
    parser.add_argument(
        "--org-profile-src",
        default=None,
        help=f"local {ORG_PROFILE_REPO} checkout (skips the gh read; enables an offline birth)",
    )
    parser.add_argument("--repo-class", default=BIRTH_PROFILE_CLASS)
    parser.add_argument(
        "--no-remote",
        action="store_true",
        help="stop after stage 5 — assemble, finalize, and validate locally only",
    )
    parser.add_argument("--private", action="store_true", help="create the repository private")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the work directory on failure (default: keep; kept for symmetry)",
    )
    parser.add_argument("--receipt", default=None, help="write the birth receipt JSON here")
    parser.add_argument(
        "--bootstrap-timeout",
        type=int,
        default=180,
        help="seconds to wait for the remote to become readable during attestation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        cfg = build_config(parse_args(argv))
    except (BirthError, prov.ProvenanceError) as exc:
        print(f"BIRTH FAIL (preflight): {exc}", file=sys.stderr)
        return 2

    receipt = BirthReceipt(
        org=cfg.org,
        repository=cfg.repo,
        package=cfg.pkg,
        description=cfg.desc,
        payload=str(cfg.payload) if cfg.payload else "",
        workdir=str(cfg.dest),
        born_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    receipt.template_sha = git_head(cfg.template_src)
    # What the template CHECKOUT says, recorded so a failure before stage 5 still
    # reports something. Stage 5 replaces it with the version the recorded commit
    # actually carries, and refuses the birth when the two disagree.
    version_file = cfg.template_src / prov.TEMPLATE_VERSION_PATH
    if version_file.is_file():
        receipt.template_version = version_file.read_text(encoding="utf-8").strip()

    profile: dict = {"name": cfg.repo_class, "forbid": []}
    try:
        stage_preflight(cfg, receipt)
        stage_assemble(cfg, receipt)
        stage_finalize(cfg, receipt)
        profile = stage_apply_org_profile(cfg, receipt)
        stage_stamp_provenance(cfg, receipt, profile)
        stage_validate(cfg, receipt)
        if cfg.remote:
            stage_create(cfg, receipt)
            stage_remote_bootstrap(cfg, receipt, profile)
            stage_attest(cfg, receipt, profile)
        else:
            receipt.record("github.create", "repository created", "SKIP", "--no-remote")
    except (BirthError, prov.ProvenanceError) as exc:
        receipt.record("birth.error", "birth", "FAIL", str(exc).splitlines()[0][:120])
        print(render_receipt(receipt))
        print(f"BIRTH FAIL: {exc}", file=sys.stderr)
        _write_receipt(cfg, receipt)
        return 1

    print(render_receipt(receipt))
    _write_receipt(cfg, receipt)
    return 1 if receipt.failed else 0


def _write_receipt(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    path = cfg.receipt_path or (cfg.work_dir / f"{cfg.repo}-birth-receipt.json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"birth receipt: {path}")
    except OSError as exc:
        print(f"warning: could not write birth receipt to {path}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
