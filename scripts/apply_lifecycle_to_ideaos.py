#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]

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
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout", help="Path to a full IdeaOS checkout")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    checkout = Path(args.checkout).resolve()

    required = [
        checkout / "src/ideaos/runtime.py",
        checkout / "src/ideaos/resources/schemas/ideaos_run_request.schema.json",
        checkout / "modules/idea-expander-decision-node/SKILL.md",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit("Refusing to apply: checkout does not look like the bound IdeaOS baseline:\n- " + "\n- ".join(missing))

    plan = []
    for src, rel in COPY_TREES:
        plan.append((src, checkout / rel, "tree"))
    for src, rel in COPY_FILES:
        plan.append((src, checkout / rel, "file"))

    for src, dst, kind in plan:
        print(f"{kind.upper()}: {src.relative_to(PACK)} -> {dst.relative_to(checkout)}")
        if args.dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if kind == "tree":
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    if not args.dry_run:
        print("APPLIED")


if __name__ == "__main__":
    main()
