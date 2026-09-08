"""Deterministic lifecycle logic: routing, promotion, and the execution handoff.

The engine decides nothing a human owns. It reads artifacts the lifecycle already
defines and answers three mechanical questions:

  route                 which canonical stage does the evidence place this idea in
  evaluate_packet       what promotion state does this decision imply
  build_execution_packet  does that promotion authorize execution

`decide` is deliberately absent. The decision authority is
`modules/idea-expander-decision-node`, and `expansion.py` already fails closed on
an upstream artifact that tries to carry a decision (FORBIDDEN_DECISIONS). This
module is the same rule facing the other way: IdeaOS consumes an IdeaDecisionPacket
and never authors one.
"""

from __future__ import annotations

from typing import Any

from .contracts import validate
from .digests import semantic_digest
from .errors import IdeaOSError

# The lifecycle's own vocabulary (pipeline/IDEA_LIFECYCLE.yaml `decisions:`).
AUTHORIZING_DECISIONS = frozenset({"GO", "CONDITIONAL_GO"})
REFUSING_DECISIONS = frozenset({"HOLD", "NO_GO"})


class IdeaOSEngine:
    """Stateless. Every method is a pure function of its argument.

    Statelessness is the point rather than an implementation detail: the runtime
    digests each input and output into a receipt, and a digest only means
    something if the same input always produces the same output.
    """

    def route(self, artifact: dict[str, Any]) -> dict[str, Any]:
        """Place an idea at the earliest stage its evidence does not yet satisfy.

        Routing reads held artifacts, never confidence. An idea advances because
        the previous stage's output exists, so the walk stops at the first gap —
        reporting the furthest stage would invite skipping the one before it,
        which is exactly what `bypass_policy` in the lifecycle forbids.
        """
        validate(artifact, "idea_classification.schema.json")
        evidence = artifact["stage_evidence"]

        # Ordered: each entry is the stage to run when the evidence before it is
        # present and its own artifact is not.
        ladder = (
            ("has_developed_idea_dossier", "create", "no DevelopedIdeaDossier yet"),
            ("has_expansion_packet", "expand", "no ExpandedIdeaDossierPacket yet"),
            (
                "has_ready_expansion_gate_receipt",
                "expansion_gate",
                "expansion dossier is not gated READY yet",
            ),
            (
                "has_decision_node_input",
                "decision_handoff",
                "no IdeaExpanderDecisionNodeInput yet",
            ),
            (
                "has_authorizing_decision_packet",
                "decide",
                "no authorizing IdeaDecisionPacket yet",
            ),
        )

        next_stage = "execute"
        rationale = ["every lifecycle artifact is present; the idea is ready to execute"]
        for key, stage, why in ladder:
            if not evidence.get(key, False):
                next_stage = stage
                rationale = [why]
                break

        decision: dict[str, Any] = {
            "schema": "ideaos.route-decision/v1",
            "idea_id": artifact["idea_id"],
            "next_stage": next_stage,
            "rationale": rationale,
            "input_digest": semantic_digest(artifact),
        }
        validate(decision, "route_decision.schema.json")
        return decision

    def evaluate_packet(self, artifact: dict[str, Any]) -> dict[str, Any]:
        """Read a decision packet's promotion state.

        CONDITIONAL_GO is the only decision whose state depends on more than the
        decision word: it promotes only when every stated condition is met.
        Treating it as ready while a condition is unmet would let the runtime
        authorize execution the decision node conditioned.
        """
        validate(artifact, "idea_decision_packet.schema.json")
        decision = artifact["decision"]
        conditions = artifact.get("conditions") or []
        unmet = [c["id"] for c in conditions if not c["met"]]

        if decision == "GO":
            state, reasons = "execution_ready", ["decision node returned GO"]
        elif decision == "CONDITIONAL_GO" and not unmet:
            state, reasons = (
                "execution_ready",
                ["decision node returned CONDITIONAL_GO and every condition is met"],
            )
        elif decision == "CONDITIONAL_GO":
            state = "conditional"
            reasons = [f"{len(unmet)} condition(s) not met"]
        elif decision == "HOLD":
            state, reasons = "blocked", ["decision node returned HOLD"]
        elif decision == "NO_GO":
            state, reasons = "rejected", ["decision node returned NO_GO"]
        else:  # pragma: no cover - the schema enum already forbids this
            raise IdeaOSError(f"unsupported decision: {decision}")

        promotion: dict[str, Any] = {"state": state, "reasons": reasons}
        if unmet:
            promotion["unmet_conditions"] = unmet

        evaluation: dict[str, Any] = {
            "schema": "ideaos.idea-evaluation/v1",
            "idea_id": artifact["idea_id"],
            "decision": decision,
            "computed_promotion": promotion,
            "input_digest": semantic_digest(artifact),
        }
        validate(evaluation, "idea_evaluation.schema.json")
        return evaluation

    def build_execution_packet(
        self,
        artifact: dict[str, Any],
        *,
        decision_ref: str | None = None,
        produced_at: str | None = None,
    ) -> dict[str, Any]:
        """Turn an authorizing decision into the execute stage's input.

        A refusing decision is not an error. HOLD and NO_GO produce a valid packet
        whose status is `no_execution_required` — the caller asked what execution
        this decision implies, and "none" is a complete answer. Callers that need
        execution say so with the `require_execution` option, and the runtime
        turns that same status into a blocked receipt.
        """
        evaluation = self.evaluate_packet(artifact)
        state = evaluation["computed_promotion"]["state"]
        decision = artifact["decision"]

        if state == "execution_ready":
            status = "execution_authorized"
            reasons = [f"{decision} promotes to execution_ready"]
        elif decision in REFUSING_DECISIONS:
            status = "no_execution_required"
            reasons = [f"{decision} authorizes no execution"]
        else:
            status = "blocked"
            reasons = list(evaluation["computed_promotion"]["reasons"])

        packet: dict[str, Any] = {
            "schema": "ideaos.idea-execution-packet/v1",
            "idea_id": artifact["idea_id"],
            "status": status,
            "reasons": reasons,
            "input_digest": semantic_digest(artifact),
        }
        if decision_ref is not None:
            packet["decision_ref"] = decision_ref
        if produced_at is not None:
            packet["produced_at"] = produced_at

        validate(packet, "idea_execution_packet.schema.json")
        return packet


__all__ = ["AUTHORIZING_DECISIONS", "REFUSING_DECISIONS", "IdeaOSEngine"]
