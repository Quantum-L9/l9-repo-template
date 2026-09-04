from __future__ import annotations
from typing import Any
from .contracts import validate
from .digests import semantic_digest

FORBIDDEN_DECISIONS={"GO","CONDITIONAL_GO","HOLD","NO_GO"}

def gate_expansion(packet:dict[str,Any])->dict[str,Any]:
    validate(packet,"expansion_packet.schema.json")
    blockers=[]
    discoveries=packet["wide_discoveries"]+packet["deep_discoveries"]
    ids=[d["id"] for d in discoveries]
    disp=[d["candidate_id"] for d in packet["candidate_dispositions"]]
    if not discoveries: blockers.append("NO_MATERIAL_DISCOVERY")
    if len(ids)!=len(set(ids)): blockers.append("DUPLICATE_DISCOVERY_ID")
    if len(disp)!=len(set(disp)): blockers.append("DUPLICATE_DISPOSITION")
    if set(ids)!=set(disp): blockers.append("DISPOSITION_COVERAGE_MISMATCH")
    handoff=packet["decision_node_handoff"]
    if str(handoff.get("decision","")).upper() in FORBIDDEN_DECISIONS:
        blockers.append("UPSTREAM_DECISION_AUTHORITY_VIOLATION")
    if handoff["status"]=="READY" and handoff.get("blockers"):
        blockers.append("READY_HANDOFF_HAS_BLOCKERS")
    if handoff["status"]=="BLOCKED":
        blockers.extend(f"UPSTREAM_BLOCKER:{x}" for x in handoff.get("blockers",[]))
    result={
      "schema":"ideaos.expansion-gate-receipt/v1",
      "idea_id":packet["idea_id"],
      "status":"READY" if not blockers else "BLOCKED",
      "blockers":blockers,
      "input_digest":semantic_digest(packet),
      "decision_node_handoff_allowed":not blockers,
    }
    validate(result,"expansion_gate_receipt.schema.json")
    return result
