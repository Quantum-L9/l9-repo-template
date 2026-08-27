#!/usr/bin/env python3
"""BIRTH INTEGRITY: is this repository genuinely what it claims it was born from?

Not "is it up to date" — that is CURRENT CONFORMANCE, a different question with a
different answer, owned by the central drift engine and read out of the mutable
`.l9/template-state.yaml`. This checker only ever asks about the immutable
record, so it keeps returning the same answer years after the repository has been
reconciled onto a newer baseline.

One birth produces three independently comparable things:

    root commit  ──────────  birth receipt  ──────────  repository contents
       trailers                  digest                    manifest_sha256

Each is derived from the other two. A mismatch anywhere means the birth record is
not describing this repository, and that is a P0 — provenance corruption, not
drift. It cannot be reconciled away, because there is nothing trustworthy left to
reconcile toward.

    verify_birth_integrity.py [--root PATH] [--require-receipt] [--json]

A repository with no `.l9/birth-receipt.json` reports UNBORN and passes: this
template was not born from itself, and repositories that predate the receipt have
nothing to attest. `--require-receipt` turns that into a failure, which is what
the birth engine uses on a newborn it has just stamped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
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


prov = _load_sibling("birth_provenance")


@dataclass
class Check:
    key: str
    label: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.repository = ""

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

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "l9.birth-integrity-report/v1",
            "repository": self.repository,
            "result": self.result,
            "checks": [
                {"key": c.key, "label": c.label, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }

    def render(self) -> str:
        lines = ["", f"L9 BIRTH INTEGRITY  {self.repository or '(unknown repository)'}"]
        for check in self.checks:
            detail = f"  {check.detail}" if check.detail else ""
            lines.append(f"  {check.label:<24} {check.status}{detail}")
        lines.append(f"BIRTH INTEGRITY: {self.result}")
        lines.append("")
        return "\n".join(lines)


def _read_text(root: Path, rel: str) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _load_receipt(root: Path) -> tuple[dict[str, object] | None, str]:
    """(receipt, state) where state is `ok`, `absent`, or a reason it is unreadable.

    Absent and unreadable are different answers. An absent receipt is a
    repository that was never born from a template; an unreadable one is a birth
    record someone damaged, which is the failure this whole checker exists for.
    """
    raw = _read_text(root, prov.BIRTH_RECEIPT_PATH)
    if raw is None:
        return None, "absent"
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"not JSON: {exc}"
    if not isinstance(receipt, dict):
        return None, "receipt is not an object"
    return receipt, "ok"


def _check_digest(receipt: dict[str, object], report: Report) -> None:
    recorded = str(receipt.get("digest") or "")
    recomputed = prov.receipt_digest(receipt)
    report.ok(
        "receipt.digest",
        "receipt digest",
        bool(recorded) and recorded == recomputed,
        f"sha256:{recomputed[:12]}",
        f"recorded {recorded[:12] or '(none)'} != recomputed {recomputed[:12]}",
    )


def _check_template_version(root: Path, receipt: dict[str, object], report: Report) -> None:
    template = receipt.get("template")
    expected = str((template or {}).get("version") or "") if isinstance(template, dict) else ""
    found = (_read_text(root, prov.TEMPLATE_VERSION_PATH) or "").strip()
    report.ok(
        "birth.version",
        "template version",
        bool(expected) and found == expected,
        f"{prov.TEMPLATE_VERSION_PATH} = {found}",
        f"{prov.TEMPLATE_VERSION_PATH} says {found or '(absent)'}, receipt says {expected or '(none)'}",
    )


def _check_marker(root: Path, receipt: dict[str, object], report: Report) -> None:
    text = _read_text(root, prov.MARKER_PATH)
    if text is None:
        report.record("birth.marker", "birth marker", "FAIL", f"{prov.MARKER_PATH} is absent")
        return
    marker = prov.parse_flat_yaml(text)
    birth = prov.birth_block(text)
    template = receipt.get("template") if isinstance(receipt.get("template"), dict) else {}
    policy = receipt.get("org_policy") if isinstance(receipt.get("org_policy"), dict) else {}
    expected = {
        "profile": str(receipt.get("repo_class") or ""),
        "repository": str(receipt.get("repository") or ""),
        "birth.template_sha": str(template.get("sha") or ""),
        "birth.template_version": str(template.get("version") or ""),
        "birth.org_policy_sha": str(policy.get("sha") or ""),
        "birth.born_at": str(receipt.get("born_at") or ""),
    }
    found = {
        "profile": str(marker.get("profile") or ""),
        "repository": str(marker.get("repository") or ""),
        "birth.template_sha": str(birth.get("template_sha") or ""),
        "birth.template_version": str(birth.get("template_version") or ""),
        "birth.org_policy_sha": str(birth.get("org_policy_sha") or ""),
        "birth.born_at": str(birth.get("born_at") or ""),
    }
    disagree = sorted(key for key, value in expected.items() if found[key] != value)
    report.ok(
        "birth.marker",
        "birth marker",
        not disagree,
        f"{expected['profile']} @ {expected['birth.template_sha'][:12]}",
        f"disagrees with the receipt on: {', '.join(disagree)}",
    )


def _check_template_state(root: Path, report: Report) -> None:
    """Present and readable — NOT equal to the birth record.

    A repository reconciled onto a newer baseline is supposed to disagree with
    its own birth record here. That is the entire point of the split, so this
    check asserts the conformance record exists and is legible, and says nothing
    about drift.
    """
    text = _read_text(root, prov.TEMPLATE_STATE_PATH)
    if text is None:
        report.record(
            "conformance.state",
            "conformance state",
            "FAIL",
            f"{prov.TEMPLATE_STATE_PATH} is absent — a born repository carries one",
        )
        return
    doc = prov.parse_flat_yaml(text)
    template = doc.get("template")
    template = template if isinstance(template, dict) else {}
    version = str(template.get("current_version") or "")
    sha = str(template.get("current_sha") or "")
    report.ok(
        "conformance.state",
        "conformance state",
        bool(version) and bool(sha),
        f"conforms to {version} @ {sha[:12]}",
        f"{prov.TEMPLATE_STATE_PATH} declares no current template sha/version",
    )


def _check_root_commit(root: Path, receipt: dict[str, object], report: Report) -> None:
    """The git leg: trailers, immutability, and the contents digest.

    Every check here reads the ROOT COMMIT, never HEAD. The root commit is what a
    birth produced, and it is the only thing in the repository that still says so
    after three years of ordinary development on top of it.
    """
    if not prov.is_git_repo(root):
        report.record("root.commit", "root commit", "SKIP", "not a git repository")
        return
    if not prov.has_commits(root):
        report.record("root.commit", "root commit", "SKIP", "no commits yet")
        return
    try:
        commit = prov.root_commit(root)
    except prov.ProvenanceError as exc:
        report.record("root.commit", "root commit", "FAIL", str(exc))
        return
    report.record("root.commit", "root commit", "PASS", commit[:12])

    expected = prov.expected_trailers(receipt)
    found = prov.parse_trailers(prov.commit_message(root, commit))
    missing = [key for key in prov.REQUIRED_TRAILERS if key not in found]
    wrong = sorted(key for key, value in expected.items() if key in found and found[key] != value)
    report.ok(
        "root.trailers",
        "commit trailers",
        not missing and not wrong,
        f"{len(expected)} trailers agree",
        (f"missing: {', '.join(missing)}; " if missing else "")
        + (f"disagree: {', '.join(wrong)}" if wrong else ""),
    )

    mutated = []
    for rel in sorted(prov.BIRTH_OWNED_PATHS):
        at_root = prov.read_blob(root, commit, rel)
        path = root / rel
        current = path.read_bytes() if path.is_file() else None
        if at_root != current:
            mutated.append(rel)
    report.ok(
        "root.immutable",
        "birth record intact",
        not mutated,
        f"{len(prov.BIRTH_OWNED_PATHS)} birth-owned paths unchanged since the root commit",
        f"mutated since birth: {', '.join(mutated)}",
    )

    recorded = str(receipt.get("manifest_sha256") or "")
    try:
        files = prov.commit_manifest(root, commit, exclude={prov.BIRTH_RECEIPT_PATH})
    except prov.ProvenanceError as exc:
        report.record("root.manifest", "contents digest", "FAIL", str(exc))
        return
    recomputed = prov.manifest_digest(files)
    report.ok(
        "root.manifest",
        "contents digest",
        bool(recorded) and recorded == recomputed,
        f"{len(files)} files, sha256:{recomputed[:12]}",
        f"receipt records {recorded[:12] or '(none)'}, root commit hashes to {recomputed[:12]}",
    )


def verify(root: Path, *, require_receipt: bool) -> tuple[Report, bool]:
    """Returns the report and whether a receipt was found at all."""
    report = Report()
    receipt, state = _load_receipt(root)
    if state == "absent":
        report.record(
            "receipt.present",
            "birth receipt",
            "FAIL" if require_receipt else "SKIP",
            f"{prov.BIRTH_RECEIPT_PATH} is absent"
            + (
                " and a receipt was required"
                if require_receipt
                else " — this repository was not born from a template"
            ),
        )
        return report, False
    if receipt is None:
        report.record("receipt.present", "birth receipt", "FAIL", state)
        return report, True
    report.record("receipt.present", "birth receipt", "PASS", prov.BIRTH_RECEIPT_PATH)
    report.repository = str(receipt.get("repository") or "")
    _check_digest(receipt, report)
    _check_template_version(root, receipt, report)
    _check_marker(root, receipt, report)
    _check_template_state(root, report)
    _check_root_commit(root, receipt, report)
    return report, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_birth_integrity.py",
        description="Prove a repository is what its birth record claims it is.",
    )
    parser.add_argument("--root", default=".", help="repository to verify (default: cwd)")
    parser.add_argument(
        "--require-receipt",
        action="store_true",
        help="fail when the repository carries no birth receipt (default: report UNBORN and pass)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    report, born = verify(root, require_receipt=args.require_receipt)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif not born and not args.require_receipt:
        print(f"birth integrity: UNBORN — no {prov.BIRTH_RECEIPT_PATH} in {root}")
    else:
        print(report.render())

    if report.failed:
        for check in report.failed:
            print(f"birth-integrity FAIL: {check.label}: {check.detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
