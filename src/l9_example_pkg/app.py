"""Minimal FastAPI hello app (non-Gate, non-Constellation)."""

from __future__ import annotations

from fastapi import FastAPI

from l9_example_pkg import __version__
from l9_example_pkg.health import health_check

app = FastAPI(title="l9-example-pkg", version=__version__)


@app.get("/v1/health")
def health() -> dict[str, object]:
    result = health_check()
    return {
        "status": result.status,
        "version": result.version,
        "capability": result.capability,
        "details": result.details,
    }


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "l9-example-pkg", "version": __version__}
