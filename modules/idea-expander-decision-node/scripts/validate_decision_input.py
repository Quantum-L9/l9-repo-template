#!/usr/bin/env python3
"""Defence-in-depth admission check for an IdeaExpanderDecisionNodeInput v3.

This runs at the decision node's door, so it must reach the same verdict as
ideaos.lifecycle.build_decision_node_input rather than a weaker approximation of
it. Checking that a receipt says READY and that its digest matches the packet
proves the packet was not edited after the receipt was written — it does not
prove a gate wrote the receipt at all. Both are recomputed here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[3]
SRC = CHECKOUT / "src"


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_decision_input.py <node-input.json>")
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if doc.get("schema") != "ideaos.decision-node-input/v3":
        fail("bad schema")

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    try:
        from ideaos.errors import IdeaOSError
        from ideaos.lifecycle import build_decision_node_input
    except ImportError as exc:  # a gate that cannot check is not a gate
        fail(
            f"cannot import the IdeaOS runtime from {SRC} ({exc}). This validator "
            "re-runs the real expansion gate; it does not approximate it."
        )

    try:
        build_decision_node_input(
            doc.get("expansion_packet", {}),
            doc.get("expansion_gate_receipt", {}),
            doc.get("decision_context", {}),
        )
    except IdeaOSError as exc:
        fail(str(exc))

    packet = doc["expansion_packet"]
    for key in ("dream", "invariant", "wedge", "proof"):
        if not packet.get("revised_center", {}).get(key):
            fail(f"missing revised_center.{key}")

    print("PASS")


if __name__ == "__main__":
    main()
