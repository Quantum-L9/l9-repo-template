"""Gate-routed worker FastAPI app (constellation-node-sdk)."""

from __future__ import annotations

from constellation_node_sdk import create_node_app

from . import handlers  # noqa: F401

app = create_node_app(
    service_name="l9-example-pkg",
    version="0.1.0",
)
