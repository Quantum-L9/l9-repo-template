#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,subprocess,sys,re,yaml
ROOT=Path(__file__).resolve().parents[1]
errs=[]
def req(rel):
    if not (ROOT/rel).exists(): errs.append('missing '+rel)
for rel in [
 'modules/idea-expander/SKILL.md','modules/idea-expander-decision-node/SKILL.md','protocols/08A_IDEA_EXPANSION.md','architecture/05_EXPANSION_STAGE.md','runtime_overlay/src/ideaos/expansion.py','runtime_overlay/src/ideaos/runtime.py','runtime_overlay/src/ideaos/resources/schemas/expansion_packet.schema.json','runtime_overlay/src/ideaos/resources/schemas/expansion_gate_receipt.schema.json']:
    req(rel)
# parse json/yaml
for p in ROOT.rglob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errs.append(f'bad json {p.relative_to(ROOT)}: {e}')
for p in list(ROOT.rglob('*.yaml'))+list(ROOT.rglob('*.yml')):
    try: yaml.safe_load(p.read_text())
    except Exception as e: errs.append(f'bad yaml {p.relative_to(ROOT)}: {e}')
# frontmatter only name/description for the two skill entrypoints
for rel in ['modules/idea-expander/SKILL.md','modules/idea-expander-decision-node/SKILL.md']:
    txt=(ROOT/rel).read_text(); m=re.match(r'^---\n(.*?)\n---',txt,re.S)
    if not m: errs.append('missing frontmatter '+rel); continue
    fm=yaml.safe_load(m.group(1)); extra=set(fm)-{'name','description'}
    if extra: errs.append(f'noncanonical frontmatter keys {rel}: {sorted(extra)}')
# schema mirrors identical
p1=(ROOT/'modules/idea-expander/references/expansion-packet.schema.json').read_bytes(); p2=(ROOT/'runtime_overlay/src/ideaos/resources/schemas/expansion_packet.schema.json').read_bytes()
if p1!=p2: errs.append('expansion schema mirror drift')
# docs authority order
pipe=(ROOT/'architecture/01_PIPELINE_STATE_MACHINE.md').read_text().lower()
for token in ['expanding','expansion_gate','decision_node']:
    if token not in pipe: errs.append('pipeline missing '+token)
# run module validators and gate tests
cmds=[
 [sys.executable,str(ROOT/'modules/idea-expander/scripts/validate_expansion_package.py'),str(ROOT/'runtime_overlay/tests/expansion_packet.ready.json')],
 [sys.executable,str(ROOT/'modules/idea-expander-decision-node/scripts/validate_decision_input.py'),str(ROOT/'modules/idea-expander-decision-node/tests/node-input.ready.json')],
 [sys.executable,str(ROOT/'modules/idea-expander-decision-node/scripts/validate_decision_package.py'),str(ROOT/'modules/idea-expander-decision-node/tests/decision-package.valid.json')],
 [sys.executable,'-m','unittest','discover','-s',str(ROOT/'runtime_overlay/tests'),'-p','test_*.py']]
for c in cmds:
    r=subprocess.run(c,capture_output=True,text=True)
    if r.returncode: errs.append('command failed: '+' '.join(c)+'\n'+r.stdout+r.stderr)
if errs:
    print('FAIL'); [print('-',e) for e in errs]; raise SystemExit(1)
print('PASS')
print('IdeaOS 11.3 expansion seam, module contracts, schema mirrors, decision handoff, and overlay tests validated')
