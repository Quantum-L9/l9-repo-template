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
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "schemas" / "birth-handoff.schema.json"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


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


def _trusted_base(fallback: Path) -> Path:
    """The directory every handoff and sealed-root path must stay inside."""
    runner_temp = os.environ.get("RUNNER_TEMP")
    return Path(runner_temp).resolve() if runner_temp else fallback.resolve()


def _confine(path: Path, base: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved != base and base not in resolved.parents:
        raise BoundaryError(f"{label} must stay inside {base}")
    return resolved


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        # Evidence remains valid on filesystems that cannot apply POSIX modes.
        return


def _write_prepare_anchor(handoff: dict[str, Any], output_path: str | None) -> None:
    """Export trusted PREPARE facts through a channel hidden from product code."""
    if not output_path:
        return
    prepared = handoff["prepared"]
    with Path(output_path).open("a", encoding="utf-8") as stream:
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


def _text(mapping: dict[str, Any], key: str, default: str = "") -> str:
    value = mapping.get(key)
    return str(value) if value else default


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _receipt_from_dict(data: dict[str, Any]) -> Any:
    product = _mapping(data, "product")
    template = _mapping(data, "template")
    organization = _mapping(data, "organization")
    owner, _, name = _text(product, "repository").partition("/")
    receipt = nr.BirthReceipt(
        org=owner,
        repository=name or owner,
        package=_text(product, "package"),
        description=_text(product, "description"),
        template_repo=_text(template, "repository", "Quantum-L9/l9-repo-template"),
        template_sha=_text(template, "sha", "unknown"),
        template_version=_text(template, "template_version", "unknown"),
        org_profile_repo=_text(organization, "repository", nr.ORG_PROFILE_REPO),
        org_profile_sha=_text(organization, "sha", "unknown"),
        birth_profile=_text(organization, "birth_profile"),
        payload=_text(product, "payload"),
        payload_mode=_text(product, "payload_mode", "none"),
        payload_contract=_text(product, "payload_contract"),
        payload_source=_mapping(product, "payload_source"),
        workdir=_text(data, "workdir"),
        head_sha=_text(data, "head_sha", "unknown"),
        born_at=_text(data, "born_at"),
        manifest_sha256=_text(data, "manifest_sha256"),
        birth_receipt=_mapping(data, "birth_receipt"),
        materialized=list(data.get("materialized") or []),
        state=_text(data, "state", nr.canonical_ci.LOCAL),
        ci=_mapping(data, "ci"),
    )
    for stage in data.get("stages") or []:
        if isinstance(stage, dict):
            receipt.record(
                _text(stage, "key", "unknown"),
                _text(stage, "label", "unknown"),
                _text(stage, "status", "UNKNOWN"),
                _text(stage, "detail"),
            )
    return receipt


def _prepare_argv(args: argparse.Namespace) -> list[str]:
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
    return argv


def prepare(args: argparse.Namespace) -> int:
    nr.assert_prepare_unprivileged()
    handoff_path = _confine(
        args.handoff, _trusted_base(args.work_dir.resolve().parent), "handoff path"
    )
    cfg = nr.build_config(nr.parse_args(_prepare_argv(args)))
    # GITHUB_OUTPUT is an integrity channel for the trusted boundary process.
    # Removing it from the mapping keeps it out of every product-controlled
    # child environment, but the kernel still shows this process's startup
    # environment to same-UID descendants, so hiding is not the boundary. The
    # boundary is that nr.prepare() terminates every product descendant before
    # the seal, and the anchor below is refused while any survives: nothing
    # product-controlled is alive to recover the path or rewrite the outputs.
    github_output = os.environ.pop("GITHUB_OUTPUT", None)
    receipt, profile, sealed = nr.prepare(cfg)
    nr.assert_no_product_descendants("PREPARE anchor")
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
    _write_json(handoff_path, handoff)
    _write_prepare_anchor(handoff, github_output)
    print(f"PREPARED SEALED {cfg.slug} {sealed['root_commit_sha']}")
    print(f"handoff: {handoff_path}")
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


def _repo_name(handoff: dict[str, Any]) -> str:
    owner, _, name = str(handoff.get("repository") or "").partition("/")
    if not NAME_RE.match(owner) or not NAME_RE.match(name):
        raise BoundaryError("handoff repository must be a plain owner/name")
    return name


def _resolve_root(handoff: dict[str, Any], explicit: Path | None, base: Path) -> Path:
    """Locate the sealed root strictly inside the trusted base directory.

    The handoff is untrusted data on the fresh runner: only a validated
    repository name, never a recorded path, may select the directory.
    """
    if explicit is not None:
        root = _confine(explicit, base, "sealed root")
    else:
        root = _confine(base / "births" / _repo_name(handoff), base, "sealed root")
    if not root.is_dir():
        raise BoundaryError("sealed root is not materialized on this runner")
    return root


def _publish_base(args: argparse.Namespace) -> Path:
    fallback = (
        args.root.resolve().parents[1] if args.root is not None else args.handoff.resolve().parent
    )
    return _trusted_base(fallback)


def _assert_expected(value: str, expected: str | None, label: str) -> None:
    if expected is not None and value != expected:
        raise BoundaryError(f"{label} does not match trusted PREPARE output")


def verify(args: argparse.Namespace) -> int:
    base = _publish_base(args)
    handoff = _load_handoff(_confine(args.handoff, base, "handoff path"))
    prepared = handoff["prepared"]
    _assert_expected(str(handoff["handoff_digest"]), args.expected_handoff_digest, "handoff digest")
    _assert_expected(str(prepared["root_commit_sha"]), args.expected_root_sha, "root SHA")
    _assert_expected(str(prepared["root_tree_sha"]), args.expected_tree_sha, "tree SHA")
    root = _resolve_root(handoff, args.root, base)
    nr.verify_sealed(root, str(prepared["root_commit_sha"]), str(prepared["root_tree_sha"]))
    print(f"VERIFIED SEALED {handoff['repository']} {prepared['root_commit_sha']}")
    return 0


def publish(args: argparse.Namespace) -> int:
    base = _publish_base(args)
    handoff = _load_handoff(_confine(args.handoff, base, "handoff path"))
    root = _resolve_root(handoff, args.root, base)
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
