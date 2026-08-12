"""Worker app factory smoke tests."""

from __future__ import annotations

from typing import Any

from constellation_node_sdk import create_node_app, register_handler
from constellation_node_sdk.runtime.config import NodeRuntimeConfig
from constellation_node_sdk.runtime.lifecycle import NoOpLifecycle
from fastapi.testclient import TestClient


def test_health_endpoint(example_runtime_config: NodeRuntimeConfig) -> None:
    async def _handle(_tenant: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "completed", "entity_id": payload.get("entity_id", "")}

    register_handler("example")(_handle)

    app = create_node_app(
        service_name="l9-example-pkg",
        version="0.1.0",
        lifecycle_hook=NoOpLifecycle(),
        config=example_runtime_config,
        auto_register_with_gate=False,
    )
    with TestClient(app) as client:
        health = client.get("/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["ready"] is True
        assert body["node_name"] == "l9-example-pkg"
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
