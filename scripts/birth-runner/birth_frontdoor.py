#!/usr/bin/env python3
"""Public operator/agent front door for secure repository birth.

This command does not perform birth locally. It validates operator intent and
sends a workflow_dispatch request to the canonical factory workflow in
Quantum-L9/l9-repo-template. The workflow owns the fresh-runner PREPARE ->
PUBLISH privilege boundary; this client never mints publication authority and
never copies CI into the newborn.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

FACTORY_REPO = "Quantum-L9/l9-repo-template"
FACTORY_WORKFLOW = "repo-birth-dispatch.yml"
DEFAULT_FACTORY_REF = "main"
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
PKG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class BirthFrontDoorError(RuntimeError):
    """The requested dispatch is invalid or could not be accepted."""


@dataclass(frozen=True)
class BirthIntent:
    repo: str
    pkg: str
    desc: str
    visibility: str = "private"
    repo_class: str = ""
    ci_unverified_reason: str = ""
    governance_ref: str = ""
    payload_repo: str = ""
    payload_ref: str = ""
    payload_subpath: str = ""
    payload_contract_path: str = ""
    factory_ref: str = DEFAULT_FACTORY_REF


def validate_intent(intent: BirthIntent) -> None:
    if not REPO_RE.fullmatch(intent.repo):
        raise BirthFrontDoorError("REPO must be a GitHub repository name without an owner prefix")
    if not PKG_RE.fullmatch(intent.pkg) or not intent.pkg.isidentifier():
        raise BirthFrontDoorError("PKG must be a snake_case Python identifier")
    if not intent.desc.strip():
        raise BirthFrontDoorError("DESC must be a non-empty one-line description")
    if "\n" in intent.desc or "\r" in intent.desc:
        raise BirthFrontDoorError("DESC must be one line")
    if intent.visibility not in {"private", "public"}:
        raise BirthFrontDoorError("visibility must be private or public")
    if intent.payload_repo and not intent.payload_ref:
        raise BirthFrontDoorError("PAYLOAD_REF is required when PAYLOAD_REPO is set")
    if intent.payload_ref and not intent.payload_repo:
        raise BirthFrontDoorError("PAYLOAD_REPO is required when PAYLOAD_REF is set")
    if intent.payload_repo and not intent.payload_repo.startswith("Quantum-L9/"):
        raise BirthFrontDoorError("PAYLOAD_REPO must be inside Quantum-L9")
    for name, value in (
        ("factory_ref", intent.factory_ref),
        ("governance_ref", intent.governance_ref),
        ("payload_ref", intent.payload_ref),
        ("payload_subpath", intent.payload_subpath),
        ("payload_contract_path", intent.payload_contract_path),
    ):
        if ".." in value.split("/"):
            raise BirthFrontDoorError(f"{name} must not contain '..' path segments")
    for name, value in (
        ("payload_subpath", intent.payload_subpath),
        ("payload_contract_path", intent.payload_contract_path),
    ):
        if value.startswith("/"):
            raise BirthFrontDoorError(f"{name} must be relative")


def dispatch_fields(intent: BirthIntent) -> list[tuple[str, str]]:
    fields = [
        ("repo_name", intent.repo),
        ("package_name", intent.pkg),
        ("description", intent.desc),
        ("visibility", intent.visibility),
    ]
    optional = [
        ("repo_class", intent.repo_class),
        ("ci_unverified_reason", intent.ci_unverified_reason),
        ("governance_ref", intent.governance_ref),
        ("payload_repo", intent.payload_repo),
        ("payload_ref", intent.payload_ref),
        ("payload_subpath", intent.payload_subpath),
        ("payload_contract_path", intent.payload_contract_path),
    ]
    fields.extend((key, value) for key, value in optional if value)
    return fields


def build_dispatch_command(intent: BirthIntent) -> list[str]:
    validate_intent(intent)
    command = [
        "gh",
        "workflow",
        "run",
        FACTORY_WORKFLOW,
        "--repo",
        FACTORY_REPO,
        "--ref",
        intent.factory_ref,
    ]
    for key, value in dispatch_fields(intent):
        command.extend(["-f", f"{key}={value}"])
    return command


def dispatch(intent: BirthIntent) -> None:
    if shutil.which("gh") is None:
        raise BirthFrontDoorError("gh is required for remote birth dispatch")
    command = build_dispatch_command(intent)
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise BirthFrontDoorError(f"birth dispatch was not accepted: {detail[-1600:]}")
    print(f"BIRTH DISPATCHED: Quantum-L9/{intent.repo}")
    print(f"FACTORY: {FACTORY_REPO}@{intent.factory_ref}")
    print(f"WORKFLOW: {FACTORY_WORKFLOW}")
    print("STATE: REQUESTED")
    print(f"NEXT: make birth-status REPO={intent.repo}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch canonical Quantum-L9 repository birth")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pkg", required=True)
    parser.add_argument("--desc", required=True)
    parser.add_argument("--visibility", choices=("private", "public"), default="private")
    parser.add_argument("--repo-class", default="")
    parser.add_argument("--ci-unverified-reason", default="")
    parser.add_argument("--governance-ref", default="")
    parser.add_argument("--payload-repo", default="")
    parser.add_argument("--payload-ref", default="")
    parser.add_argument("--payload-subpath", default="")
    parser.add_argument("--payload-contract-path", default="")
    parser.add_argument("--factory-ref", default=DEFAULT_FACTORY_REF)
    return parser.parse_args(argv)


def intent_from_args(args: argparse.Namespace) -> BirthIntent:
    return BirthIntent(
        repo=args.repo,
        pkg=args.pkg,
        desc=args.desc,
        visibility=args.visibility,
        repo_class=args.repo_class,
        ci_unverified_reason=args.ci_unverified_reason,
        governance_ref=args.governance_ref,
        payload_repo=args.payload_repo,
        payload_ref=args.payload_ref,
        payload_subpath=args.payload_subpath,
        payload_contract_path=args.payload_contract_path,
        factory_ref=args.factory_ref,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        dispatch(intent_from_args(parse_args(argv)))
    except BirthFrontDoorError as exc:
        print(f"BIRTH DISPATCH FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
