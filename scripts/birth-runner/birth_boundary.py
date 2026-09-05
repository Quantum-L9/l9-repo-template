#!/usr/bin/env python3
"""Privilege boundary for repository birth.

PREPARE runs all product-controlled work with no repository-create token present,
then sanitizes Git process configuration, validates, and seals one root commit.
PUBLISH accepts only the sealed handoff and permits only git/gh control-plane
commands while privileged authority exists.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "schemas" / "birth-handoff.schema.json"
PRIVILEGED_TOKEN_ENV = "L9_BIRTH_PRIVILEGED_TOKEN"
ALLOWED_PUBLISH_TOOLS = frozenset({"git", "gh"})


class BoundaryError(RuntimeError):
    pass


def _load_new_repo():
    path = Path(__file__).resolve().parent / "new_repo.py"
    spec = importlib.util.spec_from_file_location("l9_birth_new_repo", path)
    if spec is None or spec.loader is None:
        raise BoundaryError(f"cannot load birth engine at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


nr = _load_new_repo()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=_sanitized_env(),
    )
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BoundaryError(f"git {' '.join(args)} failed ({proc.returncode}): {detail[-1200:]}")
    return (proc.stdout or "").strip()


def _sanitized_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key != PRIVILEGED_TOKEN_ENV
    }
    if extra:
        env.update(extra)
    return env


def _assert_no_privileged_token() -> None:
    if (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip():
        raise BoundaryError(
            f"{PRIVILEGED_TOKEN_ENV} must not exist during PREPARE; privilege is minted after seal"
        )


def _sanitize_git_config(root: Path) -> None:
    config = root / ".git" / "config"
    if not config.is_file():
        raise BoundaryError("prepared repository has no .git/config")
    # Product code ran before this point and may have written hooks/fsmonitor/
    # aliases/credential helpers into local Git config. Replace that mutable
    # process configuration with the minimum repository config before sealing.
    filemode = "true" if os.name != "nt" else "false"
    config.write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        f"\tfilemode = {filemode}\n"
        "\tbare = false\n"
        "\tlogallrefupdates = true\n"
        "\thooksPath = /dev/null\n",
        encoding="utf-8",
    )


def _seal(cfg: Any, receipt: Any) -> dict[str, str]:
    _assert_no_privileged_token()
    _sanitize_git_config(cfg.dest)
    _git(cfg.dest, "add", "-A")
    message = "\n".join(
        [
            f"chore: birth {cfg.slug} from l9-repo-template@{receipt.template_sha[:12]}",
            "",
            *nr.prov.commit_trailers(receipt.birth_receipt),
        ]
    )
    proc = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
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
        check=False,
        capture_output=True,
        text=True,
        env=_sanitized_env(),
    )
    if proc.returncode != 0:
        raise BoundaryError(
            "root seal failed: " + (((proc.stderr or "") + (proc.stdout or "")).strip()[-1200:])
        )
    root_sha = _git(cfg.dest, "rev-parse", "HEAD")
    tree_sha = _git(cfg.dest, "rev-parse", "HEAD^{tree}")
    parents = _git(cfg.dest, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 1:
        raise BoundaryError("sealed birth commit is not a root commit")
    if _git(cfg.dest, "status", "--porcelain"):
        raise BoundaryError("prepared repository is dirty after root seal")
    receipt.head_sha = root_sha
    nr._verify_provenance(cfg, receipt, "seal.provenance", "sealed birth record proved")
    return {"root_commit_sha": root_sha, "root_tree_sha": tree_sha}


def _receipt_from_dict(data: dict[str, Any]) -> Any:
    product = data.get("product") or {}
    template = data.get("template") or {}
    organization = data.get("organization") or {}
    receipt = nr.BirthReceipt(
        org=str(product.get("repository", "")).split("/", 1)[0],
        repository=str(product.get("repository", "")).split("/", 1)[-1],
        package=str(product.get("package") or ""),
        description=str(product.get("description") or ""),
        template_repo=str(template.get("repository") or "Quantum-L9/l9-repo-template"),
        template_sha=str(template.get("sha") or "unknown"),
        template_version=str(template.get("template_version") or "unknown"),
        org_profile_repo=str(organization.get("repository") or nr.ORG_PROFILE_REPO),
        org_profile_sha=str(organization.get("sha") or "unknown"),
        birth_profile=str(organization.get("birth_profile") or ""),
        payload=str(product.get("payload") or ""),
        payload_mode=str(product.get("payload_mode") or "none"),
        payload_contract=str(product.get("payload_contract") or ""),
        payload_source=dict(product.get("payload_source") or {}),
        workdir=str(data.get("workdir") or ""),
        head_sha=str(data.get("head_sha") or "unknown"),
        born_at=str(data.get("born_at") or ""),
        manifest_sha256=str(data.get("manifest_sha256") or ""),
        birth_receipt=dict(data.get("birth_receipt") or {}),
        materialized=list(data.get("materialized") or []),
        state=str(data.get("state") or nr.canonical_ci.LOCAL),
        ci=dict(data.get("ci") or {}),
    )
    for stage in data.get("stages") or []:
        if isinstance(stage, dict):
            receipt.record(
                str(stage.get("key") or "unknown"),
                str(stage.get("label") or "unknown"),
                str(stage.get("status") or "UNKNOWN"),
                str(stage.get("detail") or ""),
            )
    return receipt


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _validate_handoff(value: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise BoundaryError(f"invalid birth handoff: {detail}")
    claimed = str(value.get("handoff_digest") or "")
    unsigned = dict(value)
    unsigned.pop("handoff_digest", None)
    actual = _sha256(unsigned)
    if claimed != actual:
        raise BoundaryError("birth handoff digest mismatch")


def prepare(args: argparse.Namespace) -> int:
    _assert_no_privileged_token()
    argv = [
        "--repo",
        args.repo,
        "--pkg",
        args.pkg,
        "--desc",
        args.desc,
        "--org",
        args.org,
        "--work-dir",
        str(args.work_dir),
        "--template-src",
        str(args.template_src),
        "--repo-class",
        args.repo_class,
        "--no-remote",
        "--keep",
    ]
    if args.payload:
        argv += ["--payload", str(args.payload)]
    if args.payload_contract:
        argv += ["--payload-contract", str(args.payload_contract)]
    if args.org_profile_src:
        argv += ["--org-profile-src", str(args.org_profile_src)]
    if args.private:
        argv += ["--private"]
    cfg = nr.build_config(nr.parse_args(argv))
    receipt = nr.BirthReceipt(
        org=cfg.org,
        repository=cfg.repo,
        package=cfg.pkg,
        description=cfg.desc,
        payload=str(cfg.payload) if cfg.payload else "",
        workdir=str(cfg.dest),
        born_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    receipt.template_sha = nr.git_head(cfg.template_src)
    version_file = cfg.template_src / nr.prov.TEMPLATE_VERSION_PATH
    if version_file.is_file():
        receipt.template_version = version_file.read_text(encoding="utf-8").strip()

    nr.stage_preflight(cfg, receipt)
    nr.stage_assemble(cfg, receipt)
    nr.stage_finalize(cfg, receipt)
    profile = nr.stage_apply_org_profile(cfg, receipt)
    nr.stage_stamp_provenance(cfg, receipt, profile)
    nr.stage_validate(cfg, receipt)
    sealed = _seal(cfg, receipt)
    receipt.state = "SEALED"
    nr._write_receipt(cfg, receipt)

    request_basis = {
        "repository": cfg.slug,
        "package": cfg.pkg,
        "description": cfg.desc,
        "private": cfg.private,
        "repo_class": profile["name"],
        "template_sha": receipt.template_sha,
        "org_policy_sha": receipt.org_profile_sha,
        "payload_source": receipt.payload_source,
    }
    handoff: dict[str, Any] = {
        "schema": "l9.repo-birth-handoff/v1",
        "request_digest": _sha256(request_basis),
        "repository": cfg.slug,
        "package": cfg.pkg,
        "description": cfg.desc,
        "private": cfg.private,
        "repo_class": profile["name"],
        "template": {
            "sha": receipt.template_sha,
            "version": receipt.template_version,
        },
        "organization": {"sha": receipt.org_profile_sha},
        "payload": {
            "mode": receipt.payload_mode,
            "source": receipt.payload_source,
        },
        "prepared": {
            **sealed,
            "root_path": str(cfg.dest),
            "contents_manifest_sha256": receipt.manifest_sha256,
            "permanent_receipt_digest": str(receipt.birth_receipt.get("digest") or ""),
        },
        "prepare_receipt": str(cfg.receipt_path or (cfg.work_dir / f"{cfg.repo}-birth-receipt.json")),
        "bootstrap_timeout": cfg.bootstrap_timeout,
        "profile": profile,
        "receipt": receipt.to_dict(),
    }
    handoff["handoff_digest"] = _sha256(handoff)
    _write_json(args.handoff, handoff)
    print(f"PREPARED SEALED {cfg.slug} {sealed['root_commit_sha']}")
    print(f"handoff: {args.handoff}")
    return 0


def _control_run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    tool = Path(cmd[0]).name
    if tool not in ALLOWED_PUBLISH_TOOLS:
        raise BoundaryError(f"PUBLISH refused non-control-plane executable: {tool}")
    merged = _sanitized_env()
    token = (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip()
    if token:
        merged["GH_TOKEN"] = token
    if env:
        # Caller may add non-privileged values but cannot replace the token.
        merged.update({k: v for k, v in env.items() if k != "GH_TOKEN"})
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
        raise BoundaryError(f"{' '.join(cmd)} failed ({proc.returncode})\n{detail[-1600:]}")
    return proc


def _remote_head(slug: str) -> str | None:
    proc = _control_run(["gh", "api", f"repos/{slug}/commits/main", "--jq", ".sha"], check=False)
    value = (proc.stdout or "").strip()
    return value if len(value) == 40 else None


def _publish_root(cfg: Any, receipt: Any, root_sha: str) -> None:
    existing = _control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if existing.returncode == 0:
        head = _remote_head(cfg.slug)
        if head == root_sha:
            receipt.record("github.create", "repository created", "PASS", "already exact")
            receipt.record("github.push", "initial push", "PASS", root_sha[:12])
            return
        state = "QUARANTINED_PARTIAL_CREATE" if head is None else "CONFLICT"
        receipt.state = state
        raise BoundaryError(f"{cfg.slug} already exists but sealed root cannot be proven ({state})")

    visibility = "--private" if cfg.private else "--public"
    proc = _control_run(
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
        ],
        check=False,
    )
    if proc.returncode == 0:
        receipt.record("github.create", "repository created", "PASS", cfg.slug)
        receipt.record("github.push", "initial push", "PASS", root_sha[:12])
        return

    # gh repo create is not atomic. Probe instead of guessing what half happened.
    probe = _control_run(["gh", "repo", "view", cfg.slug, "--json", "name"], check=False)
    if probe.returncode != 0:
        receipt.state = "PUBLISH_FAILED_NO_REMOTE"
        raise BoundaryError("publication failed and target repository is absent; safe to retry")
    head = _remote_head(cfg.slug)
    if head == root_sha:
        receipt.record("github.create", "repository created", "PASS", "recovered after command failure")
        receipt.record("github.push", "initial push", "PASS", root_sha[:12])
        return
    receipt.state = "QUARANTINED_PARTIAL_CREATE"
    raise BoundaryError("repository exists after failed publication but exact sealed root is not present")


def publish(args: argparse.Namespace) -> int:
    token = (os.environ.get(PRIVILEGED_TOKEN_ENV) or "").strip()
    if not token:
        raise BoundaryError(f"{PRIVILEGED_TOKEN_ENV} is required for PUBLISH")
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if not isinstance(handoff, dict):
        raise BoundaryError("birth handoff must be a JSON object")
    _validate_handoff(handoff)

    prepared = handoff["prepared"]
    root = Path(prepared["root_path"]).resolve()
    root_sha = str(prepared["root_commit_sha"])
    tree_sha = str(prepared["root_tree_sha"])
    if _git(root, "rev-parse", "HEAD") != root_sha:
        raise BoundaryError("prepared HEAD changed after seal")
    if _git(root, "rev-parse", "HEAD^{tree}") != tree_sha:
        raise BoundaryError("prepared tree changed after seal")
    if _git(root, "status", "--porcelain"):
        raise BoundaryError("prepared working tree changed after seal")
    hooks = _git(root, "config", "--local", "--get", "core.hooksPath")
    if hooks != "/dev/null":
        raise BoundaryError("prepared repository does not disable Git hooks")

    data = handoff["receipt"]
    receipt = _receipt_from_dict(data)
    work_dir = root.parent
    cfg = nr.BirthConfig(
        org=handoff["repository"].split("/", 1)[0],
        repo=handoff["repository"].split("/", 1)[1],
        pkg=handoff["package"],
        desc=handoff["description"],
        work_dir=work_dir,
        payload=None,
        payload_contract=None,
        template_src=ROOT,
        org_profile_src=None,
        repo_class=handoff["repo_class"],
        remote=True,
        private=bool(handoff["private"]),
        keep=True,
        receipt_path=Path(handoff["prepare_receipt"]),
        bootstrap_timeout=int(handoff.get("bootstrap_timeout") or 180),
    )
    cfg.verified_payload_mode = str((handoff.get("payload") or {}).get("mode") or "none")

    # Fail closed if any future remote stage tries to execute product/toolchain code.
    nr.run = _control_run
    try:
        _publish_root(cfg, receipt, root_sha)
        receipt.state = nr.canonical_ci.PROVISIONAL
        profile = dict(handoff["profile"])
        nr.stage_remote_bootstrap(cfg, receipt, profile)
        nr.stage_verify_ci_enrollment(cfg, receipt)
        nr.stage_attest(cfg, receipt, profile)
        receipt.state = (
            nr.canonical_ci.PROVISIONAL if not receipt.failed else nr.canonical_ci.QUARANTINED
        )
        receipt.ci["state"] = receipt.state
    except Exception as exc:
        receipt.record("birth.error", "birth", "FAIL", str(exc).splitlines()[0][:120])
        nr._write_receipt(cfg, receipt)
        raise
    nr._write_receipt(cfg, receipt)
    print(nr.render_receipt(receipt))
    return 1 if receipt.failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="birth_boundary.py")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare")
    prep.add_argument("--repo", required=True)
    prep.add_argument("--pkg", required=True)
    prep.add_argument("--desc", required=True)
    prep.add_argument("--org", default=nr.DEFAULT_ORG)
    prep.add_argument("--work-dir", type=Path, required=True)
    prep.add_argument("--template-src", type=Path, default=ROOT)
    prep.add_argument("--org-profile-src", type=Path)
    prep.add_argument("--payload", type=Path)
    prep.add_argument("--payload-contract", type=Path)
    prep.add_argument("--repo-class", default=nr.BIRTH_PROFILE_CLASS)
    prep.add_argument("--private", action="store_true")
    prep.add_argument("--handoff", type=Path, required=True)

    pub = sub.add_parser("publish")
    pub.add_argument("--handoff", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return prepare(args) if args.command == "prepare" else publish(args)
    except (BoundaryError, nr.BirthError, nr.prov.ProvenanceError, nr.canonical_ci.CanonicalCIError) as exc:
        print(f"BIRTH {args.command.upper()} FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
