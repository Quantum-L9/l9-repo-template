#!/usr/bin/env python3
"""One-command repository birth for non-Constellation Quantum-L9 Python repos.

`make new-repo` runs this. When it returns PASS the repository is *born* — not
"created, now go do seven other things". The eight stages below are a state
machine, and every one of them either passes or stops the birth.

    [1] PREFLIGHT              tools, auth, identity validation, name is free
    [2] ASSEMBLE LOCALLY       template + identity stamp + optional payload
    [3] FINALIZE               LICENSE, uv lock, rules, manifest, metadata
    [4] APPLY ORG BIRTH PROFILE current Quantum-L9/.github, class capabilities
    [5] VALIDATE BEFORE CREATION  the full product gate, on the newborn
    [6] CREATE GITHUB REPOSITORY  create remote, push finalized initial repo
    [7] REMOTE ORG BOOTSTRAP      labels, settings, applicable seeding
    [8] REMOTE ATTESTATION        read the remote back and prove it

`uv lock` is stage 3, not something a product author is asked to remember. A
birth invariant belongs to the birth engine.

Ownership, unchanged by this script:

    l9-repo-template     owns HOW A REPO IS BORN
    Quantum-L9/.github   owns WHAT THE ORGANIZATION REQUIRES
    l9-ci-core           owns HOW CI EXECUTES
    l9-ci-control-plane  owns WHICH CI APPLIES WHERE
    the product repo     owns ITS PRODUCT

This script never decides what the organization requires. It reads
`policies/repo-classes.yml` from Quantum-L9/.github at a recorded SHA and
applies it.
"""

from __future__ import annotations

import argparse
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

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ORG = "Quantum-L9"
DEFAULT_WORK_DIR = "/tmp/l9-births"
ORG_PROFILE_REPO = "Quantum-L9/.github"
ORG_PROFILE_PATH = "policies/repo-classes.yml"
MARKER_PATH = ".l9/org-birth-profile.yaml"
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


def render_marker(
    *,
    profile_name: str,
    repository: str,
    template_sha: str,
    org_profile_sha: str,
    born_at: str,
) -> str:
    return (
        "# Organization birth profile marker.\n"
        "#\n"
        "# This repository declares its own class; Quantum-L9/.github decides what that\n"
        "# class receives (INHERIT / MATERIALIZE / REMOTE APPLY / FORBID), per\n"
        "# policies/repo-classes.yml over there.\n"
        "#\n"
        "# Written by scripts/birth-runner/new_repo.py at birth. The two SHAs below are\n"
        "# the exact pair of commits this repository was born from.\n"
        "schema: l9.org-birth-profile-marker/v1\n"
        f"profile: {profile_name}\n"
        f"authority: {ORG_PROFILE_REPO}\n"
        f"repository: {repository}\n"
        f"template_sha: {template_sha}\n"
        f"org_profile_sha: {org_profile_sha}\n"
        f"born_at: {born_at}\n"
    )


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
    workdir: str = ""
    head_sha: str = "unknown"
    born_at: str = ""
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
            },
            "workdir": self.workdir,
            "head_sha": self.head_sha,
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
        lines.append(f"  {'payload':<22} {receipt.payload}")

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


def copy_tree(src: Path, dest: Path) -> int:
    """Copy the template working tree, skipping git and machine state."""
    copied = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if _is_machine_state(rel):
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


def git_head(root: Path) -> str:
    proc = run(["git", "-C", str(root), "rev-parse", "HEAD"], check=False)
    sha = (proc.stdout or "").strip()
    return sha if SHA_RE.match(sha) else "unknown"


def gh_json(args: list[str]) -> object:
    proc = run(["gh", *args])
    return json.loads(proc.stdout or "null")


# ─────────────────────────────────────────────────────────────────────────────
# Stages
# ─────────────────────────────────────────────────────────────────────────────


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


def stage_preflight(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Tools, auth, identity, and a target name that is actually free."""
    for tool in ("git", "python3", "uv"):
        if shutil.which(tool) is None:
            raise BirthError(f"{tool} not found on PATH")
    receipt.record("preflight.tools", "tools", "PASS", "git, python3, uv")

    needs_gh = cfg.remote or cfg.org_profile_src is None
    if needs_gh:
        if shutil.which("gh") is None:
            raise BirthError(
                "gh not found on PATH — required to read the org birth profile and to "
                "create the repository. Use --org-profile-src and --no-remote for a "
                "fully local birth."
            )
        proc = run(["gh", "auth", "status"], check=False)
        if proc.returncode != 0:
            raise BirthError("gh is not authenticated — run `gh auth login`")
        receipt.record("preflight.auth", "auth", "PASS", "gh authenticated")
    else:
        receipt.record("preflight.auth", "auth", "SKIP", "local birth, no gh needed")

    # Identity was validated when the config was built; record it as evidence.
    receipt.record(
        "preflight.identity",
        "identity",
        "PASS",
        f"{cfg.slug} / {cfg.pkg}",
    )

    if not (cfg.template_src / "pyproject.toml").is_file():
        raise BirthError(f"template source is not a repository checkout: {cfg.template_src}")
    if not (cfg.template_src / "src" / "l9_example_pkg").is_dir():
        raise BirthError(
            f"template source has already been renamed: {cfg.template_src} — "
            "birth needs a pristine l9-repo-template checkout"
        )

    if cfg.payload is not None and not cfg.payload.is_dir():
        raise BirthError(f"PAYLOAD is not a directory: {cfg.payload}")

    if cfg.dest.exists() and any(cfg.dest.iterdir()):
        raise BirthError(
            f"work directory already populated: {cfg.dest} — remove it or pass a different WORK_DIR"
        )

    if cfg.remote:
        proc = run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
        if proc.returncode == 0:
            raise BirthError(
                f"{cfg.slug} already exists — birth creates a repository, it does not adopt one"
            )
        receipt.record("preflight.name", "name available", "PASS", f"{cfg.slug} is free")
    else:
        receipt.record("preflight.name", "name available", "SKIP", "local birth")


def stage_assemble(cfg: BirthConfig, receipt: BirthReceipt) -> None:
    """Template + identity stamp + optional product payload."""
    cfg.dest.mkdir(parents=True, exist_ok=True)
    copied = copy_tree(cfg.template_src, cfg.dest)
    receipt.record("assemble.template", "template copied", "PASS", f"{copied} files")

    run(["git", "init", "-q", "-b", "main"], cwd=cfg.dest)
    run(["git", "remote", "add", "origin", f"https://github.com/{cfg.slug}.git"], cwd=cfg.dest)

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

    if cfg.payload is not None:
        written = overlay_payload(cfg.payload, cfg.dest)
        receipt.record("assemble.payload", "payload overlay", "PASS", f"{len(written)} files")
    else:
        receipt.record("assemble.payload", "payload overlay", "SKIP", "no PAYLOAD given")


def _stamp_description(cfg: BirthConfig) -> None:
    """Replace the template's own description with the product's.

    Only the `description = "..."` line in `[project]` is rewritten; prose that
    happens to quote the template description is left alone.
    """
    pyproject = cfg.dest / "pyproject.toml"
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
    import base64

    decoded = base64.b64decode("".join(text.split())).decode("utf-8")
    head = gh_json(["api", f"repos/{ORG_PROFILE_REPO}/commits/HEAD", "--jq", "{sha:.sha}"])
    sha = head.get("sha", "unknown") if isinstance(head, dict) else "unknown"
    return decoded, sha


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

    marker_rel = doc.get("marker_path", MARKER_PATH)
    (cfg.dest / marker_rel).parent.mkdir(parents=True, exist_ok=True)
    (cfg.dest / marker_rel).write_text(
        render_marker(
            profile_name=profile["name"],
            repository=cfg.slug,
            template_sha=receipt.template_sha,
            org_profile_sha=org_sha,
            born_at=receipt.born_at,
        ),
        encoding="utf-8",
    )
    receipt.record("org.profile", "org defaults", "PASS", f"{profile['name']} @ {org_sha[:12]}")

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
            f"chore: birth {cfg.slug} from l9-repo-template@{receipt.template_sha[:12]}",
        ],
        cwd=cfg.dest,
    )
    receipt.head_sha = git_head(cfg.dest)

    visibility = "--private" if cfg.private else "--public"
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
        ]
    )
    receipt.record("github.create", "repository created", "PASS", cfg.slug)

    run(["git", "push", "-u", "origin", "main"], cwd=cfg.dest)
    receipt.record("github.push", "initial push", "PASS", receipt.head_sha[:12])


def stage_remote_bootstrap(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Invoke the org capabilities now, instead of waiting for the hourly sweep."""
    dispatches = [
        (
            "github.labels",
            "labels applied",
            [
                "gh",
                "workflow",
                "run",
                "repo-birth-bootstrap.yml",
                "--repo",
                ORG_PROFILE_REPO,
                "-f",
                f"target_repo={cfg.repo}",
                "-f",
                f"repo_class={profile['name']}",
                "-f",
                "dry_run=false",
            ],
        ),
        (
            "github.seed",
            "org files seeded",
            [
                "gh",
                "workflow",
                "run",
                "auto-seed-new-repo.yml",
                "--repo",
                ORG_PROFILE_REPO,
                "-f",
                f"target_repo={cfg.repo}",
                "-f",
                f"repo_class={profile['name']}",
                "-f",
                "dry_run=false",
            ],
        ),
    ]
    for key, label, cmd in dispatches:
        proc = run(cmd, check=False)
        if proc.returncode == 0:
            receipt.record(key, label, "PASS", "dispatched")
        else:
            detail = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
            receipt.record(key, label, "FAIL", detail[-1] if detail else "dispatch failed")


def stage_attest(cfg: BirthConfig, receipt: BirthReceipt, profile: dict) -> None:
    """Read the remote back. Local assembly proves nothing about GitHub."""
    deadline = time.monotonic() + cfg.bootstrap_timeout
    remote_head = ""
    while time.monotonic() < deadline:
        proc = run(
            ["gh", "api", f"repos/{cfg.slug}/commits/main", "--jq", ".sha"],
            check=False,
        )
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

    for rel in ("README.md", CANONICAL_LICENSE, MARKER_PATH, "pyproject.toml", "uv.lock"):
        proc = run(["gh", "api", f"repos/{cfg.slug}/contents/{rel}", "--jq", ".name"], check=False)
        receipt.record(
            f"github.present.{rel}",
            f"remote {rel}",
            "PASS" if proc.returncode == 0 else "FAIL",
            rel,
        )

    proc = run(
        ["gh", "api", f"repos/{cfg.slug}/contents/{MARKER_PATH}", "--jq", ".content"],
        check=False,
    )
    remote_class = None
    if proc.returncode == 0:
        import base64

        remote_class = parse_marker_profile(
            base64.b64decode("".join((proc.stdout or "").split())).decode("utf-8")
        )
    receipt.record(
        "github.class",
        "org policy attested",
        "PASS" if remote_class == profile["name"] else "FAIL",
        remote_class or "marker unreadable",
    )

    leaked = []
    for pattern in profile["forbid"]:
        probe = pattern[:-3] if pattern.endswith("/**") else pattern
        proc = run(
            ["gh", "api", f"repos/{cfg.slug}/contents/{probe}", "--jq", ".name"], check=False
        )
        if proc.returncode == 0:
            leaked.append(pattern)
    receipt.record(
        "github.forbid",
        "forbid attested",
        "PASS" if not leaked else "FAIL",
        ", ".join(leaked) if leaked else f"{len(profile['forbid'])} probed",
    )


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
    parser.add_argument("--work-dir", default=os.environ.get("WORK_DIR", DEFAULT_WORK_DIR))
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
    except BirthError as exc:
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
    version_file = cfg.template_src / ".l9-template-version"
    if version_file.is_file():
        receipt.template_version = version_file.read_text(encoding="utf-8").strip()

    profile: dict = {"name": cfg.repo_class, "forbid": []}
    try:
        stage_preflight(cfg, receipt)
        stage_assemble(cfg, receipt)
        stage_finalize(cfg, receipt)
        profile = stage_apply_org_profile(cfg, receipt)
        stage_validate(cfg, receipt)
        if cfg.remote:
            stage_create(cfg, receipt)
            stage_remote_bootstrap(cfg, receipt, profile)
            stage_attest(cfg, receipt, profile)
        else:
            receipt.record("github.create", "repository created", "SKIP", "--no-remote")
    except BirthError as exc:
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
