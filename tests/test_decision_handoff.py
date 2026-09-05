import hashlib
import json
import unittest
from pathlib import Path

from ideaos.errors import IdeaOSError
from ideaos.expansion import gate_expansion
from ideaos.lifecycle import build_decision_node_input

ROOT = Path(__file__).resolve().parents[1]


def semantic_digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class DecisionHandoffTests(unittest.TestCase):
    def packet(self):
        return json.loads((ROOT / "tests" / "expansion_packet.ready.json").read_text())

    def receipt(self, packet):
        return gate_expansion(packet)

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

    def test_forged_ready_receipt_for_blocked_packet_is_rejected(self):
        """The gate bypass: every structural check passes, and the gate is skipped.

        The packet is mutated so the real gate BLOCKS it, then a READY receipt is
        hand-written whose digest matches the mutated packet — so nothing was
        "changed after validation" and the receipt is internally consistent. Only
        recomputing the gate distinguishes this from a genuine handoff.
        """
        packet = self.packet()
        packet["candidate_dispositions"] = packet["candidate_dispositions"][:-1]
        self.assertEqual(gate_expansion(packet)["status"], "BLOCKED")

        forged = {
            "schema": "ideaos.expansion-gate-receipt/v1",
            "idea_id": packet["idea_id"],
            "status": "READY",
            "blockers": [],
            "input_digest": semantic_digest(packet),
            "gate_policy_digest": gate_expansion(self.packet())["gate_policy_digest"],
            "decision_node_handoff_allowed": True,
        }
        with self.assertRaises(IdeaOSError) as caught:
            build_decision_node_input(packet, forged, self.context())
        self.assertIn("expansion gate does not authorize this packet", str(caught.exception))

    def test_receipt_from_a_different_gate_policy_is_rejected(self):
        packet = self.packet()
        receipt = self.receipt(packet)
        receipt["gate_policy_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(IdeaOSError):
            build_decision_node_input(packet, receipt, self.context())

    def test_receipt_for_a_different_idea_is_rejected(self):
        packet = self.packet()
        receipt = self.receipt(packet)
        receipt["idea_id"] = "some-other-idea"
        with self.assertRaises(IdeaOSError):
            build_decision_node_input(packet, receipt, self.context())


if __name__ == "__main__":
    unittest.main()
