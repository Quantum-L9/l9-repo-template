"""The runtime's one external read, kept behind a contract.

`commercial_research` is the only operation the registry marks
`deterministic=False` and `side_effect_class="external_read"`. Everything else in
IdeaOS is a pure function of its input; this reaches the outside world, so the
boundary is explicit and narrow.

The provider supplies findings. This module supplies the discipline: the request
is validated before the provider sees it, the answers are checked against the
questions actually asked, and the packet is bound to the request digest that
produced it. A provider cannot answer a question nobody asked, cannot silently
drop one, and cannot hand back a packet that outlives the request.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .contracts import validate
from .digests import semantic_digest
from .errors import IdeaOSError


@runtime_checkable
class CommercialResearchProvider(Protocol):
    """A source of commercial evidence.

    Deliberately one method. A provider is an answer source, not a participant in
    the lifecycle: it never sees the idea's decision state, and nothing it returns
    can promote an idea by itself.
    """

    @property
    def name(self) -> str:
        """Stable identifier recorded in the packet's provenance."""

    def research(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """Answer a validated CommercialEvidenceRequest.

        Returns one finding per question, each carrying the `question_id` it
        answers. Raising is a legitimate outcome; returning something shaped
        wrongly is not, and is caught here rather than downstream.
        """


class CommercialEvidenceService:
    """Runs a provider against a request and certifies what came back."""

    def __init__(self, provider: CommercialResearchProvider) -> None:
        self.provider = provider

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        validate(request, "commercial_evidence_request.schema.json")
        asked = [q["id"] for q in request["questions"]]

        findings = self.provider.research(request)
        if not isinstance(findings, list):
            raise IdeaOSError("commercial provider must return a list of findings")

        answered = [f.get("question_id") for f in findings]
        # Checked as sets and as counts: the first catches a provider inventing or
        # dropping a question, the second catches it answering one twice, which a
        # set comparison alone would call correct.
        if set(answered) != set(asked):
            missing = sorted(set(asked) - set(answered))
            extra = sorted(x for x in set(answered) - set(asked) if x is not None)
            raise IdeaOSError(
                "commercial provider findings do not match the questions asked: "
                f"missing={missing!r} unrequested={extra!r}"
            )
        if len(answered) != len(asked):
            raise IdeaOSError("commercial provider answered a question more than once")

        packet: dict[str, Any] = {
            "schema": "ideaos.commercial-evidence-packet/v1",
            "idea_id": request["idea_id"],
            "findings": findings,
            "provider": {"name": self.provider.name, "deterministic": False},
            # The request, not the questions: the packet is evidence for exactly
            # the request that produced it, scope and all.
            "input_digest": semantic_digest(request),
        }
        validate(packet, "commercial_evidence_packet.schema.json")
        return packet


__all__ = ["CommercialEvidenceService", "CommercialResearchProvider"]
