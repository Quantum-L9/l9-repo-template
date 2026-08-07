"""HTTP integration for the minimal FastAPI hello."""

from __future__ import annotations

from fastapi.testclient import TestClient

from l9_example_pkg.app import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded", "disabled"}
    assert "version" in body


def test_root() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "l9-example-pkg"
