from __future__ import annotations
from typing import Any
from .contracts import validate
from .digests import semantic_digest

FORBIDDEN_DECISIONS={"GO","CONDITIONAL_GO","HOLD","NO_GO"}

# The gate's own rule set, named so a receipt can say which policy produced it.
# A receipt carries GATE_POLICY_DIGEST; changing, adding or removing a rule below
# changes that digest, so a receipt issued under an older policy is no longer
# equal to what this gate would issue and is rejected at the decision handoff.
GATE_POLICY_VERSION="ideaos.expansion-gate-policy/v2"
GATE_RULES=(
  "NO_MATERIAL_DISCOVERY",
  "DUPLICATE_DISCOVERY_ID",
  "DUPLICATE_DISPOSITION",
  "DISPOSITION_COVERAGE_MISMATCH",
  "UPSTREAM_DECISION_AUTHORITY_VIOLATION",
  "READY_HANDOFF_HAS_BLOCKERS",
  "UPSTREAM_HANDOFF_BLOCKED",
)
GATE_POLICY_DIGEST=semantic_digest({"version":GATE_POLICY_VERSION,"rules":list(GATE_RULES)})

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
        # BLOCKED is itself a blocker. Enumerating the upstream list alone let an
        # empty `blockers: []` produce zero gate blockers and therefore a READY
        # receipt — the state machine is fail-closed, so the status governs.
        upstream=list(handoff.get("blockers") or [])
        blockers.extend(f"UPSTREAM_BLOCKER:{x}" for x in upstream)
        if not upstream: blockers.append("UPSTREAM_HANDOFF_BLOCKED")
    result={
      "schema":"ideaos.expansion-gate-receipt/v1",
      "idea_id":packet["idea_id"],
      "status":"READY" if not blockers else "BLOCKED",
      "blockers":blockers,
      "input_digest":semantic_digest(packet),
      "gate_policy_digest":GATE_POLICY_DIGEST,
      "decision_node_handoff_allowed":not blockers,
    }
    validate(result,"expansion_gate_receipt.schema.json")
    return result
