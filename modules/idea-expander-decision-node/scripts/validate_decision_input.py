#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def semantic_digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_decision_input.py <node-input.json>")
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if doc.get("schema") != "ideaos.decision-node-input/v3":
        fail("bad schema")

    packet = doc.get("expansion_packet", {})
    receipt = doc.get("expansion_gate_receipt", {})

    if receipt.get("schema") != "ideaos.expansion-gate-receipt/v1":
        fail("missing or invalid ExpansionGateReceipt")
    if receipt.get("status") != "READY":
        fail("ExpansionGateReceipt is not READY")
    if receipt.get("blockers"):
        fail("ExpansionGateReceipt still has blockers")
    if receipt.get("decision_node_handoff_allowed") is not True:
        fail("ExpansionGateReceipt does not authorize decision-node handoff")
    if receipt.get("idea_id") != packet.get("idea_id"):
        fail("idea_id mismatch between expansion packet and gate receipt")
    if receipt.get("input_digest") != semantic_digest(packet):
        fail("expansion packet digest mismatch: packet changed after expansion gate")

    handoff = packet.get("decision_node_handoff", {})
    if handoff.get("status") != "READY":
        fail("expansion handoff is not READY")
    if handoff.get("blockers"):
        fail("expansion handoff still has blockers")
    for key in ("dream", "invariant", "wedge", "proof"):
        if not packet.get("revised_center", {}).get(key):
            fail(f"missing revised_center.{key}")

    print("PASS")


if __name__ == "__main__":
    main()
