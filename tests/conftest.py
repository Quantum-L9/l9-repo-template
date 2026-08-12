"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from constellation_node_sdk.runtime.config import NodeRuntimeConfig
from constellation_node_sdk.runtime.handlers import clear_handlers


@pytest.fixture(autouse=True)
def _clear_handler_registry() -> Iterator[None]:
    clear_handlers()
    yield
    clear_handlers()


@pytest.fixture()
def example_runtime_config() -> NodeRuntimeConfig:
    return NodeRuntimeConfig(
        environment="test",
        node_name="l9-example-pkg",
        service_name="l9-example-pkg",
        service_version="0.1.0",
        dev_mode=True,
        require_signature=False,
        expose_internal_errors=True,
        return_transport_errors=True,
        signing_algorithm="hmac-sha256",
        signing_key=None,
        allowed_actions=("example",),
        allowed_packet_types=("request",),
        max_packet_bytes=262_144,
        max_attachments=0,
        max_attachment_size_bytes=0,
        gate_url=None,
    )
