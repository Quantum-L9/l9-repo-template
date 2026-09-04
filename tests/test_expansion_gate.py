import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ideaos.expansion import gate_expansion

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
if __name__=='__main__': unittest.main()
