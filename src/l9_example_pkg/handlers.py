"""Domain action handlers — replace/extend for your worker."""

from __future__ import annotations

from typing import Any

from constellation_node_sdk import register_handler


@register_handler("example")
async def handle_example(_tenant: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Example domain handler. Rename the action and implement real logic."""
    entity_id = str(payload.get("entity_id", "unknown"))
    return {
        "status": "completed",
        "entity_id": entity_id,
        "message": "replace this handler with domain logic",
    }
