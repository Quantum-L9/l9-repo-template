import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ideaos.lifecycle import build_decision_node_input
from ideaos.errors import IdeaOSError


def semantic_digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class DecisionHandoffTests(unittest.TestCase):
    def packet(self):
        return json.loads((ROOT / "tests" / "expansion_packet.ready.json").read_text())

    def receipt(self, packet):
        return {
            "schema": "ideaos.expansion-gate-receipt/v1",
            "idea_id": packet["idea_id"],
            "status": "READY",
            "blockers": [],
            "input_digest": semantic_digest(packet),
            "decision_node_handoff_allowed": True,
        }

    def context(self):
        return {"authority_rules": ["decision node owns adjudication"], "constraints": ["fail closed"]}

    def test_ready_packet_binds(self):
        packet = self.packet()
        output = build_decision_node_input(packet, self.receipt(packet), self.context())
        self.assertEqual(output["schema"], "ideaos.decision-node-input/v3")
        self.assertEqual(output["expansion_gate_receipt"]["input_digest"], semantic_digest(packet))

    def test_tamper_after_gate_fails(self):
        packet = self.packet()
        receipt = self.receipt(packet)
        packet["revised_center"]["wedge"] += " changed"
        with self.assertRaises(IdeaOSError):
            build_decision_node_input(packet, receipt, self.context())

    def test_blocked_receipt_fails(self):
        packet = self.packet()
        receipt = self.receipt(packet)
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = ["TEST"]
        receipt["decision_node_handoff_allowed"] = False
        with self.assertRaises(IdeaOSError):
            build_decision_node_input(packet, receipt, self.context())


if __name__ == "__main__":
    unittest.main()
