#!/usr/bin/env python3
import json,sys
from pathlib import Path

def fail(m): print('FAIL:',m); raise SystemExit(1)
def main():
    if len(sys.argv)!=2: fail('usage: validate_decision_package.py <decision-package.json>')
    d=json.loads(Path(sys.argv[1]).read_text())
    if d.get('schema')!='ideaos.decision-node-output/v2': fail('bad schema')
    for p in ('deployability','marketability','economics'):
        if p not in d.get('perspectives',{}): fail('missing perspective '+p)
    votes=d.get('board_votes',[])
    if len(votes)<3: fail('fewer than 3 independent board votes')
    if d.get('decision')=='CONDITIONAL_GO' and not d.get('conditions'): fail('CONDITIONAL_GO requires conditions')
    if d.get('decision') in {'HOLD','NO_GO'} and not d.get('evidence_acquisition') and not d.get('red_team',{}).get('critical_findings'): fail('stopped decision needs evidence/critical rationale')
    print('PASS')
if __name__=='__main__': main()
