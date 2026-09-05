import json
import unittest
from pathlib import Path

from ideaos.errors import ContractValidationError
from ideaos.expansion import GATE_POLICY_DIGEST, gate_expansion

ROOT = Path(__file__).resolve().parents[1]

class ExpansionGateTests(unittest.TestCase):
    def fixture(self): return json.loads((ROOT/'tests'/'expansion_packet.ready.json').read_text())
    def test_ready(self):
        r=gate_expansion(self.fixture()); self.assertEqual(r['status'],'READY'); self.assertTrue(r['decision_node_handoff_allowed'])
    def test_missing_disposition_blocks(self):
        d=self.fixture(); d['candidate_dispositions']=d['candidate_dispositions'][:-1]
        r=gate_expansion(d); self.assertEqual(r['status'],'BLOCKED'); self.assertIn('DISPOSITION_COVERAGE_MISMATCH',r['blockers'])
    def test_blocked_upstream_stays_blocked(self):
        d=self.fixture(); d['decision_node_handoff']={'status':'BLOCKED','blockers':['MATERIAL_UNKNOWN']}
        r=gate_expansion(d); self.assertEqual(r['status'],'BLOCKED')
    def test_blocked_with_empty_blocker_list_still_blocks(self):
        """BLOCKED is the blocker. Enumerating the upstream list alone made an empty
        list contribute nothing, so a BLOCKED handoff was issued a READY receipt."""
        d=self.fixture(); d['decision_node_handoff']={'status':'BLOCKED','blockers':[]}
        r=gate_expansion(d)
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn('UPSTREAM_HANDOFF_BLOCKED',r['blockers'])
        self.assertFalse(r['decision_node_handoff_allowed'])
    def test_handoff_without_a_blocker_list_never_reaches_the_gate(self):
        """The schema already requires `blockers`, so the gate's `or []` is depth,
        not the guard. Asserting gate behaviour here would assert on input the
        contract forbids; assert the contract instead."""
        d=self.fixture(); d['decision_node_handoff']={'status':'BLOCKED'}
        with self.assertRaises(ContractValidationError): gate_expansion(d)
    def test_receipt_carries_gate_policy_digest(self):
        self.assertEqual(gate_expansion(self.fixture())['gate_policy_digest'],GATE_POLICY_DIGEST)

if __name__=='__main__': unittest.main()
