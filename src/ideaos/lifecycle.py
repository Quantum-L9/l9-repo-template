from __future__ import annotations

from typing import Any

from .contracts import validate
from .digests import semantic_digest
from .errors import IdeaOSError


def build_decision_node_input(
    expansion_packet: dict[str, Any],
    expansion_gate_receipt: dict[str, Any],
    decision_context: dict[str, Any],
) -> dict[str, Any]:
    """Bind the exact validated expansion dossier to the decision-node handoff.

    The gate receipt is authoritative only for the exact packet digest it validated.
    Any mutation after the gate invalidates the handoff.
    """
    validate(expansion_packet, "expansion_packet.schema.json")
    validate(expansion_gate_receipt, "expansion_gate_receipt.schema.json")
    validate(decision_context, "decision_context.schema.json")

    if expansion_gate_receipt["status"] != "READY":
        raise IdeaOSError("decision handoff requires a READY ExpansionGateReceipt")
    if not expansion_gate_receipt["decision_node_handoff_allowed"]:
        raise IdeaOSError("decision handoff is not allowed by ExpansionGateReceipt")
    if expansion_gate_receipt["blockers"]:
        raise IdeaOSError("READY ExpansionGateReceipt must not contain blockers")
    if expansion_gate_receipt["idea_id"] != expansion_packet["idea_id"]:
        raise IdeaOSError("expansion packet and gate receipt idea_id mismatch")

    actual_digest = semantic_digest(expansion_packet)
    if expansion_gate_receipt["input_digest"] != actual_digest:
        raise IdeaOSError(
            "expansion packet digest does not match ExpansionGateReceipt; "
            "the dossier was changed after validation"
        )

    handoff = expansion_packet["decision_node_handoff"]
    if handoff["status"] != "READY" or handoff.get("blockers"):
        raise IdeaOSError("expansion packet does not declare a clean decision-node handoff")

    output = {
        "schema": "ideaos.decision-node-input/v3",
        "expansion_packet": expansion_packet,
        "expansion_gate_receipt": expansion_gate_receipt,
        "decision_context": decision_context,
    }
    validate(output, "decision_node_input.schema.json")
    return output
