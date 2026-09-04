#!/usr/bin/env python3
import json, sys
from pathlib import Path
VALID_DISPOSITIONS={"integrate_now","sequence_later","preserve_option","discard"}
VALID_EVIDENCE={"VERIFIED","SUPPORTED_INFERENCE","HYPOTHESIS","UNKNOWN"}
FORBIDDEN_DECISIONS={"GO","CONDITIONAL_GO","HOLD","NO_GO"}

def fail(msg): print(f"FAIL: {msg}"); raise SystemExit(1)
def center_ok(c,name):
    if not isinstance(c,dict): fail(f"{name} must be object")
    for k in ("dream","invariant","wedge","proof"):
        if not isinstance(c.get(k),str) or not c[k].strip(): fail(f"{name}.{k} missing")

def main():
    if len(sys.argv)!=2: fail("usage: validate_expansion_package.py <expansion_packet.json>")
    d=json.loads(Path(sys.argv[1]).read_text())
    req=["schema_version","idea_id","source_refs","original_center","wide_discoveries","deep_discoveries","compounding_loops","persona_effects","candidate_dispositions","revised_center","evidence_register","unknowns","modifications","decision_node_handoff"]
    for k in req:
        if k not in d: fail(f"missing {k}")
    if d["schema_version"]!=1: fail("unsupported schema_version")
    center_ok(d["original_center"],"original_center"); center_ok(d["revised_center"],"revised_center")
    discoveries=d["wide_discoveries"]+d["deep_discoveries"]
    if not discoveries: fail("at least one wide/deep discovery required")
    ids=[]
    for x in discoveries:
        if x.get("evidence_state") not in VALID_EVIDENCE: fail("invalid discovery evidence state")
        if not x.get("id"): fail("discovery id missing")
        ids.append(x["id"])
    if len(ids)!=len(set(ids)): fail("duplicate discovery id")
    dispositions=d["candidate_dispositions"]
    if not dispositions: fail("candidate_dispositions empty")
    disp_ids=[]
    for x in dispositions:
        if x.get("disposition") not in VALID_DISPOSITIONS: fail("invalid disposition")
        disp_ids.append(x.get("candidate_id"))
    if set(disp_ids)!=set(ids): fail("candidate dispositions must cover every discovery exactly once")
    if len(disp_ids)!=len(set(disp_ids)): fail("duplicate candidate disposition")
    handoff=d["decision_node_handoff"]
    if str(handoff.get("decision","")).upper() in FORBIDDEN_DECISIONS: fail("expander must not make final decision")
    if handoff.get("status") not in {"READY","BLOCKED"}: fail("handoff status invalid")
    if handoff["status"]=="READY" and handoff.get("blockers"): fail("READY handoff cannot carry blockers")
    print("PASS")
if __name__=="__main__": main()
