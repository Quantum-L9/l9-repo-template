#!/usr/bin/env python3
"""Transport adapter for the canonical repository-birth engine.

This module owns no birth sequencing. ``new_repo.py`` owns prepare, seal,
publish, and all. This adapter only converts CLI arguments to the engine model,
serializes/validates ``l9.repo-birth-handoff/v1``, and reconstructs that model
on a fresh PUBLISH runner.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "schemas" / "birth-handoff.schema.json"


class BoundaryError(RuntimeError):
    """The transport/handoff contract is invalid or cannot be reconstructed."""


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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        # Evidence remains valid on filesystems that cannot apply POSIX modes.
        return


def _write_prepare_anchor(handoff: dict[str, Any]) -> None:
    """Export trusted PREPARE facts before this process exits.

    GitHub captures step outputs outside the uploaded artifact. A product-spawned
    process may mutate files after PREPARE returns, but it cannot redefine the
    already-emitted expected digest/root/tree that PUBLISH compares against.
    """
    output = (os.environ.get("GITHUB_OUTPUT") or "").strip()
    if not output:
        return
    prepared = handoff["prepared"]
    with Path(output).open("a", encoding="utf-8") as stream:
        stream.write(f"handoff_digest={handoff['handoff_digest']}\n")
        stream.write(f"root_sha={prepared['root_commit_sha']}\n")
        stream.write(f"tree_sha={prepared['root_tree_sha']}\n")


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
    if claimed != _sha256(unsigned):
        raise BoundaryError("birth handoff digest mismatch")


def _receipt_from_dict(data: dict[str, Any]) -> Any:
    product = data.get("product") or {}
    template = data.get("template") or {}
    organization = data.get("organization") or {}
    repository = str(product.get("repository") or "")
    owner, _, name = repository.partition("/")
    receipt = nr.BirthReceipt(
        org=owner,
        repository=name or owner,
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


def _prepare_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--repo", args.repo,
        "--pkg", args.pkg,
        "--desc", args.desc,
        "--org", args.org,
        "--work-dir", str(args.work_dir),
        "--template-src", str(args.template_src),
        "--repo-class", args.repo_class,
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
    return argv


def prepare(args: argparse.Namespace) -> int:
    nr.assert_prepare_unprivileged()
    cfg = nr.build_config(nr.parse_args(_prepare_argv(args)))
    receipt, profile, sealed = nr.prepare(cfg)
    request_basis = {
        "repository": cfg.slug,
        "package": cfg.pkg,
        "description": cfg.desc,
        "private": cfg.private,
        "repo_class": profile["name"],
        "template_sha": receipt.template_sha,
        "org_policy_sha": receipt.org_profile_sha,
        "payload_source": receipt.payload_source,
        "governance_sha": os.environ.get("L9_BIRTH_GOVERNANCE_SHA", ""),
        "payload_repository": os.environ.get("L9_BIRTH_PAYLOAD_REPOSITORY", ""),
        "payload_requested_ref": os.environ.get("L9_BIRTH_PAYLOAD_REQUESTED_REF", ""),
        "payload_resolved_sha": os.environ.get("L9_BIRTH_PAYLOAD_RESOLVED_SHA", ""),
    }
    handoff: dict[str, Any] = {
        "schema": "l9.repo-birth-handoff/v1",
        "request_digest": _sha256(request_basis),
        "repository": cfg.slug,
        "package": cfg.pkg,
        "description": cfg.desc,
        "private": cfg.private,
        "repo_class": profile["name"],
        "template": {"sha": receipt.template_sha, "version": receipt.template_version},
        "organization": {"sha": receipt.org_profile_sha},
        "payload": {"mode": receipt.payload_mode, "source": receipt.payload_source},
        "prepared": {
            **sealed,
            "root_path": str(cfg.dest),
            "contents_manifest_sha256": receipt.manifest_sha256,
            "permanent_receipt_digest": str(receipt.birth_receipt.get("digest") or ""),
        },
        "prepare_receipt": str(
            cfg.receipt_path or (cfg.work_dir / f"{cfg.repo}-birth-receipt.json")
        ),
        "bootstrap_timeout": cfg.bootstrap_timeout,
        "profile": profile,
        "receipt": receipt.to_dict(),
    }
    handoff["handoff_digest"] = _sha256(handoff)
    _write_json(args.handoff, handoff)
    _write_prepare_anchor(handoff)
    print(f"PREPARED SEALED {cfg.slug} {sealed['root_commit_sha']}")
    print(f"handoff: {args.handoff}")
    return 0


def _load_handoff(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundaryError(f"cannot read birth handoff {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BoundaryError("birth handoff must be a JSON object")
    _validate_handoff(value)
    return value


def _cfg_from_handoff(handoff: dict[str, Any], root: Path) -> Any:
    repository = str(handoff["repository"])
    org, _, repo = repository.partition("/")
    if not org or not repo:
        raise BoundaryError("handoff repository must be owner/name")
    return nr.BirthConfig(
        org=org,
        repo=repo,
        pkg=str(handoff["package"]),
        desc=str(handoff["description"]),
        work_dir=root.parent,
        payload=None,
        payload_contract=None,
        template_src=ROOT,
        org_profile_src=None,
        repo_class=str(handoff["repo_class"]),
        remote=True,
        private=bool(handoff["private"]),
        keep=True,
        receipt_path=root.parent / f"{repo}-birth-receipt.json",
        bootstrap_timeout=int(handoff["bootstrap_timeout"]),
    )


def _resolve_root(handoff: dict[str, Any], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    prepared = handoff.get("prepared") or {}
    recorded = Path(str(prepared.get("root_path") or ""))
    candidate = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "births" / Path(
        str(handoff["repository"])
    ).name
    if candidate.is_dir():
        return candidate.resolve()
    if recorded.is_dir():
        return recorded.resolve()
    raise BoundaryError("sealed root is not materialized on this runner")


def _assert_expected(value: str, expected: str | None, label: str) -> None:
    if expected is not None and value != expected:
        raise BoundaryError(f"{label} does not match trusted PREPARE output")


def verify(args: argparse.Namespace) -> int:
    handoff = _load_handoff(args.handoff)
    prepared = handoff["prepared"]
    _assert_expected(str(handoff["handoff_digest"]), args.expected_handoff_digest, "handoff digest")
    _assert_expected(str(prepared["root_commit_sha"]), args.expected_root_sha, "root SHA")
    _assert_expected(str(prepared["root_tree_sha"]), args.expected_tree_sha, "tree SHA")
    root = _resolve_root(handoff, args.root)
    nr.verify_sealed(
        root,
        str(prepared["root_commit_sha"]),
        str(prepared["root_tree_sha"]),
    )
    print(f"VERIFIED SEALED {handoff['repository']} {prepared['root_commit_sha']}")
    return 0


def publish(args: argparse.Namespace) -> int:
    handoff = _load_handoff(args.handoff)
    root = _resolve_root(handoff, args.root)
    prepared = handoff["prepared"]
    receipt = _receipt_from_dict(dict(handoff["receipt"]))
    cfg = _cfg_from_handoff(handoff, root)
    nr.publish(
        cfg,
        receipt,
        dict(handoff["profile"]),
        root_sha=str(prepared["root_commit_sha"]),
        tree_sha=str(prepared["root_tree_sha"]),
    )
    print(nr.render_receipt(receipt))
    return 1 if receipt.failed else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="birth_boundary.py")
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare")
    prep.add_argument("--repo", required=True)
    prep.add_argument("--pkg", required=True)
    prep.add_argument("--desc", required=True)
    prep.add_argument("--org", default=nr.DEFAULT_ORG)
    prep.add_argument("--payload", type=Path)
    prep.add_argument("--payload-contract", type=Path)
    prep.add_argument("--work-dir", type=Path, required=True)
    prep.add_argument("--template-src", type=Path, default=ROOT)
    prep.add_argument("--org-profile-src", type=Path, required=True)
    prep.add_argument("--repo-class", default=nr.BIRTH_PROFILE_CLASS)
    prep.add_argument("--private", action="store_true")
    prep.add_argument("--bootstrap-timeout", type=int, default=180)
    prep.add_argument("--handoff", type=Path, required=True)

    check = sub.add_parser("verify")
    check.add_argument("--handoff", type=Path, required=True)
    check.add_argument("--root", type=Path)
    check.add_argument("--expected-handoff-digest")
    check.add_argument("--expected-root-sha")
    check.add_argument("--expected-tree-sha")

    pub = sub.add_parser("publish")
    pub.add_argument("--handoff", type=Path, required=True)
    pub.add_argument("--root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "prepare":
            return prepare(args)
        if args.command == "verify":
            return verify(args)
        return publish(args)
    except (BoundaryError, nr.BirthError, nr.prov.ProvenanceError) as exc:
        print(f"BIRTH {args.command.upper()} FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
