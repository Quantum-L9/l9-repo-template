#!/usr/bin/env python3
"""Apply the 11.4 lifecycle overlay to a bound IdeaOS 11.2 checkout.

This installer deletes whole module trees with rmtree and overwrites runtime
source. Its previous admission test was the presence of three paths, which any
scaffold can satisfy — a synthetic tree containing three placeholder files was
accepted — and there was no backup, so a wrong target was unrecoverable for any
uncommitted work in it.

Admission is now identity, not shape: the target must be a git repository whose
HEAD is the commit this pack is bound to in TRACEABILITY.yaml, with a clean
worktree. Every destination that already exists is copied into a timestamped
backup before anything is written, and any failure mid-apply restores from it,
so the tree is either fully overlaid or untouched.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
BACKUP_ROOT = Path(".ideaos-lifecycle-backup")

COPY_TREES = [
    (PACK / "modules" / "idea-expander", Path("modules/idea-expander")),
    (PACK / "modules" / "idea-expander-decision-node", Path("modules/idea-expander-decision-node")),
]

COPY_FILES = [
    (PACK / "src/ideaos/expansion.py", Path("src/ideaos/expansion.py")),
    (PACK / "src/ideaos/lifecycle.py", Path("src/ideaos/lifecycle.py")),
    (PACK / "src/ideaos/runtime.py", Path("src/ideaos/runtime.py")),
    (PACK / "src/ideaos/resources/schemas/expansion_packet.schema.json", Path("src/ideaos/resources/schemas/expansion_packet.schema.json")),
    (PACK / "src/ideaos/resources/schemas/expansion_gate_receipt.schema.json", Path("src/ideaos/resources/schemas/expansion_gate_receipt.schema.json")),
    (PACK / "src/ideaos/resources/schemas/decision_context.schema.json", Path("src/ideaos/resources/schemas/decision_context.schema.json")),
    (PACK / "src/ideaos/resources/schemas/decision_handoff_request.schema.json", Path("src/ideaos/resources/schemas/decision_handoff_request.schema.json")),
    (PACK / "src/ideaos/resources/schemas/decision_node_input.schema.json", Path("src/ideaos/resources/schemas/decision_node_input.schema.json")),
    (PACK / "src/ideaos/resources/schemas/ideaos_run_request.schema.json", Path("src/ideaos/resources/schemas/ideaos_run_request.schema.json")),
    (PACK / "pipeline/IDEA_LIFECYCLE.yaml", Path("pipeline/IDEA_LIFECYCLE.yaml")),
    (PACK / "architecture/06_CANONICAL_IDEA_LIFECYCLE.md", Path("docs/architecture/06_CANONICAL_IDEA_LIFECYCLE.md")),
    (PACK / "protocols/08A_IDEA_EXPANSION.md", Path("protocols/08A_IDEA_EXPANSION.md")),
    (PACK / "protocols/08B_EXPANSION_TO_DECISION_HANDOFF.md", Path("protocols/08B_EXPANSION_TO_DECISION_HANDOFF.md")),
    (PACK / "protocols/09_DECISION_NODE.md", Path("protocols/09_DECISION_NODE.md")),
    # Behaviour travels with the regressions that prove it. Installing the gate
    # without these leaves the host unable to detect a re-opened bypass.
    (PACK / "tests/test_expansion_gate.py", Path("tests/test_expansion_gate.py")),
    (PACK / "tests/test_decision_handoff.py", Path("tests/test_decision_handoff.py")),
    (PACK / "tests/test_decision_package.py", Path("tests/test_decision_package.py")),
    (PACK / "tests/expansion_packet.ready.json", Path("tests/expansion_packet.ready.json")),
]


def bound_head() -> str:
    text = (PACK / "TRACEABILITY.yaml").read_text(encoding="utf-8")
    match = re.search(r"^\s*git_head:\s*([0-9a-f]{40})\s*$", text, re.MULTILINE)
    if not match:
        raise SystemExit("TRACEABILITY.yaml does not declare a 40-character baseline git_head")
    return match.group(1)


def git(checkout: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(checkout), *args], capture_output=True, text=True, check=False
    )


def check_admission(checkout: Path, allow_head: str | None, force: bool) -> None:
    problems: list[str] = []

    head = git(checkout, "rev-parse", "HEAD")
    if head.returncode != 0:
        problems.append(f"{checkout} is not a git repository (git rev-parse HEAD failed)")
    else:
        actual = head.stdout.strip()
        expected = allow_head or bound_head()
        if actual != expected:
            problems.append(
                f"HEAD is {actual}, but this pack is bound to {expected}. "
                "Check out the bound commit, or pass --allow-head <sha> to name the "
                "commit you intend to overlay."
            )
        status = git(checkout, "status", "--porcelain")
        if status.returncode == 0 and status.stdout.strip():
            problems.append(
                "worktree is not clean; uncommitted changes cannot be restored by "
                "git after this installer overwrites them:\n    "
                + "\n    ".join(status.stdout.strip().splitlines()[:20])
            )

    if not problems:
        return
    if force:
        print("WARNING: --force overrides admission:", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        return
    raise SystemExit(
        "Refusing to apply:\n- " + "\n- ".join(problems) + "\nPass --force to override."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("checkout", help="Path to a full IdeaOS checkout at the bound commit")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    ap.add_argument("--allow-head", metavar="SHA", help="overlay this commit instead of the bound one")
    ap.add_argument("--force", action="store_true", help="apply despite failed admission checks")
    args = ap.parse_args()
    checkout = Path(args.checkout).resolve()

    if not checkout.is_dir():
        raise SystemExit(f"Refusing to apply: {checkout} is not a directory")
    check_admission(checkout, args.allow_head, args.force)

    plan = [(src, checkout / rel, "tree") for src, rel in COPY_TREES]
    plan += [(src, checkout / rel, "file") for src, rel in COPY_FILES]

    missing = [str(src) for src, _, _ in plan if not src.exists()]
    if missing:
        raise SystemExit("Pack is incomplete, refusing to apply:\n- " + "\n- ".join(missing))

    for src, dst, kind in plan:
        print(f"{kind.upper()}: {src.relative_to(PACK)} -> {dst.relative_to(checkout)}")
    if args.dry_run:
        return

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = checkout / BACKUP_ROOT / stamp
    restored: list[Path] = []
    for _, dst, kind in plan:
        if not dst.exists():
            continue
        target = backup / dst.relative_to(checkout)
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tree":
            shutil.copytree(dst, target)
        else:
            shutil.copy2(dst, target)
        restored.append(dst)
    print(f"BACKUP: {backup.relative_to(checkout)} ({len(restored)} existing destination(s))")

    try:
        for src, dst, kind in plan:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if kind == "tree":
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    except Exception as exc:
        print(f"ERROR during apply: {exc}\nRolling back from {backup}", file=sys.stderr)
        for dst in restored:
            source = backup / dst.relative_to(checkout)
            if dst.is_dir():
                shutil.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            if source.is_dir():
                shutil.copytree(source, dst)
            else:
                shutil.copy2(source, dst)
        raise SystemExit("ROLLED BACK: the checkout is as it was before this run") from exc

    print("APPLIED")
    print(f"Restore with: rm -rf <destinations> && cp -a {backup}/. {checkout}/")


if __name__ == "__main__":
    main()
