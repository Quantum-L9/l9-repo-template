#!/usr/bin/env python3
"""Birth does not trust a compiled payload. It reproduces it.

A compiled `l9.birth-payload/v1` is a claim about bytes that lived somewhere
else, at some earlier moment, on some other machine. Between compilation and
consumption the source tree can be edited, checked out to a different revision,
or replaced entirely — so the contract is only worth what the consumer re-derives
from the actual tree immediately before assembly (BP-007):

    CompiledBirthPayload.files  ==  actual source snapshot  ==  bytes copied

Not approximately, and not "the same paths". The same hashes. If one byte
changed after compilation, the birth stops here — before a GitHub repository
exists, which is the only point at which stopping is still free (BP-011).

The mode is re-derived too, from the same `payload-ownership.yaml` the compiler
read. The compiler PROPOSES a classification from evidence; this verifies it
against the contract, so a hand-edited `"mode": "authoritative"` cannot promote a
fragment into a payload that deletes product surfaces it never owned.

    verify_birth_payload.py --payload FILE --source DIR [--pkg NAME] [--json]

Exit 0 when every check passes, 1 when any does not.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_sibling(name: str):
    """Load a module that lives next to this file, wherever this file lives."""
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the birth module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prov = _load_sibling("birth_provenance")
ownership_contract = _load_sibling("payload_ownership")
compiler = _load_sibling("compile_birth_payload")

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA = "l9.birth-payload-verification/v1"

PayloadCompileError = compiler.PayloadCompileError
load_payload = compiler.load_payload


@dataclass
class Check:
    key: str
    label: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.source = ""

    def record(self, key: str, label: str, status: str, detail: str = "") -> Check:
        check = Check(key, label, status, detail)
        self.checks.append(check)
        return check

    def ok(self, key: str, label: str, condition: bool, good: str, bad: str) -> bool:
        self.record(key, label, "PASS" if condition else "FAIL", good if condition else bad)
        return condition

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def result(self) -> str:
        return "FAIL" if self.failed else "PASS"

    @property
    def reason(self) -> str:
        """One line naming every failure — what a caller raises with."""
        return "; ".join(f"{c.label}: {c.detail}" for c in self.failed)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": REPORT_SCHEMA,
            "source": self.source,
            "result": self.result,
            "checks": [
                {"key": c.key, "label": c.label, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }

    def render(self) -> str:
        lines = ["", f"L9 BIRTH PAYLOAD  {self.source or '(unknown source)'}"]
        for check in self.checks:
            detail = f"  {check.detail}" if check.detail else ""
            lines.append(f"  {check.label:<26} {check.status}{detail}")
        lines.append(f"BIRTH PAYLOAD: {self.result}")
        lines.append("")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# The checks
# ─────────────────────────────────────────────────────────────────────────────


def _check_revision(document: dict, source: Path, report: Report) -> None:
    """The snapshot must still be the snapshot that was compiled.

    The source's `owner/name` is deliberately NOT re-derived. Two different
    repositories cannot share a commit oid and a tree oid, so the revision check
    below is the stronger statement; re-reading `origin` would only add a way to
    fail a correct birth from a checkout that has no remote configured.
    """
    declared = document["source"]
    try:
        revision, tree_sha = compiler.source_revision(source)
    except (PayloadCompileError, prov.ProvenanceError) as exc:
        report.record("payload.revision", "source revision", "FAIL", str(exc).splitlines()[0][:160])
        return
    report.ok(
        "payload.revision",
        "source revision",
        revision == declared["revision"] and tree_sha == declared["tree_sha"],
        f"{revision[:12]} (tree {tree_sha[:12]})",
        f"source is at {revision[:12]}/{tree_sha[:12]}, payload pins "
        f"{str(declared['revision'])[:12]}/{str(declared['tree_sha'])[:12]} — recompile",
    )


def _check_manifest(document: dict, source: Path, report: Report) -> None:
    """Recompute every hash and compare. This is the invariant (BP-007)."""
    try:
        files = compiler.source_files(source)
    except (PayloadCompileError, prov.ProvenanceError) as exc:
        report.record("payload.manifest", "source manifest", "FAIL", str(exc).splitlines()[0][:160])
        return

    actual = {rel: hashlib.sha256(body).hexdigest() for rel, body in files.items()}
    declared = {str(entry["path"]): str(entry["sha256"]) for entry in document["files"]}

    missing = sorted(set(declared) - set(actual))
    extra = sorted(set(actual) - set(declared))
    changed = sorted(rel for rel in set(declared) & set(actual) if declared[rel] != actual[rel])
    if missing or extra or changed:
        parts = []
        if missing:
            parts.append(f"{len(missing)} authorized path(s) gone: {', '.join(missing[:5])}")
        if extra:
            parts.append(f"{len(extra)} unauthorized path(s) present: {', '.join(extra[:5])}")
        if changed:
            parts.append(f"{len(changed)} file(s) changed: {', '.join(changed[:5])}")
        report.record("payload.manifest", "source manifest", "FAIL", "; ".join(parts))
        return
    report.record("payload.manifest", "source manifest", "PASS", f"{len(actual)} file(s) identical")

    recomputed = prov.manifest_digest(files)
    report.ok(
        "payload.digest",
        "manifest digest",
        recomputed == document["manifest_sha256"],
        f"sha256:{recomputed[:12]}",
        f"recomputed {recomputed[:12]} != payload {str(document['manifest_sha256'])[:12]}",
    )


def _check_engine_paths(document: dict, report: Report) -> None:
    claimed = sorted({str(e["path"]) for e in document["files"]} & set(prov.ENGINE_OWNED_PATHS))
    report.ok(
        "payload.provenance",
        "birth paths unclaimed",
        not claimed,
        f"{len(prov.ENGINE_OWNED_PATHS)} engine-owned path(s) unclaimed",
        f"payload claims engine-owned birth path(s): {', '.join(claimed)}",
    )


def _check_mode(document: dict, source: Path, template_src: Path, report: Report) -> None:
    """Re-derive the classification rather than accepting the one declared."""
    try:
        ownership = ownership_contract.load_ownership(template_src)
    except ownership_contract.OwnershipContractError as exc:
        report.record("payload.mode", "payload mode", "FAIL", str(exc).splitlines()[0][:160])
        return
    derived = (
        "authoritative"
        if ownership_contract.is_repository_payload(source, ownership)
        else "additive"
    )
    declared = str(document["mode"])
    if not report.ok(
        "payload.mode",
        "payload mode",
        derived == declared,
        derived,
        f"payload declares {declared}, the ownership contract derives {derived} — "
        "the contract decides, and a payload does not get to promote itself",
    ):
        return
    matched = sorted(str(x) for x in document["repository_shape"]["matched"])
    report.ok(
        "payload.shape",
        "repository shape",
        matched == sorted(ownership_contract.matched_shape(source, ownership)),
        f"{len(matched)} shape path(s) matched",
        "recorded repository_shape.matched does not describe this source",
    )


def _check_package(document: dict, pkg: str | None, report: Report) -> None:
    """`PKG` must name a package the payload actually ships.

    Checked here rather than deep in assembly: under an authoritative payload the
    renamed template package is replaced by the payload's, so a PKG naming
    neither installs a package nothing points at.
    """
    packages = [str(name) for name in document["packages"]["python"]]
    if pkg is None:
        report.record("payload.package", "package identity", "SKIP", "no PKG given")
        return
    if not packages:
        report.record(
            "payload.package", "package identity", "SKIP", "payload ships no src/ package"
        )
        return
    report.ok(
        "payload.package",
        "package identity",
        pkg in packages,
        f"{pkg} is shipped by the payload",
        f"PKG={pkg} is not a package this payload ships ({', '.join(packages)})",
    )


def verify_payload(
    document: dict,
    source: Path,
    *,
    template_src: Path,
    pkg: str | None = None,
) -> Report:
    """Reproduce the compiled payload against the source tree, here and now."""
    report = Report()
    source = source.resolve()
    declared_source = document.get("source")
    if isinstance(declared_source, dict):
        report.source = (
            f"{declared_source.get('repository')}@{str(declared_source.get('revision'))[:12]}"
        )

    report.record("payload.schema", "payload contract", "PASS", compiler.SCHEMA)
    try:
        compiler.assert_immutable_snapshot(source)
    except (PayloadCompileError, prov.ProvenanceError) as exc:
        report.record("payload.snapshot", "source snapshot", "FAIL", str(exc).splitlines()[0][:160])
        return report
    report.record("payload.snapshot", "source snapshot", "PASS", "clean git worktree")

    _check_revision(document, source, report)
    _check_manifest(document, source, report)
    _check_engine_paths(document, report)
    _check_mode(document, source, template_src, report)
    _check_package(document, pkg, report)
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify_birth_payload.py",
        description="Reproduce a compiled birth payload against its source snapshot.",
    )
    parser.add_argument("--payload", required=True, help="compiled l9.birth-payload/v1 document")
    parser.add_argument("--source", required=True, help="the source checkout it was compiled from")
    parser.add_argument("--template-src", default=str(TEMPLATE_ROOT))
    parser.add_argument("--pkg", default=None, help="PKG the birth intends to use")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = load_payload(Path(args.payload).expanduser().resolve())
    except PayloadCompileError as exc:
        report = Report()
        report.record("payload.schema", "payload contract", "FAIL", str(exc).splitlines()[0][:200])
        print(json.dumps(report.to_dict(), indent=2) if args.json else report.render())
        return 1

    report = verify_payload(
        document,
        Path(args.source).expanduser(),
        template_src=Path(args.template_src).expanduser().resolve(),
        pkg=args.pkg,
    )
    print(json.dumps(report.to_dict(), indent=2) if args.json else report.render())
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
