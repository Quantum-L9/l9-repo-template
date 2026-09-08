"""HTTP health surface for the born IdeaOS package."""

from __future__ import annotations

from fastapi import FastAPI

from ideaos import __version__
from ideaos.health import health_check

app = FastAPI(title="ideaos", version=__version__)


def health() -> dict[str, object]:
    result = health_check()
    return {
        "status": result.status,
        "version": result.version,
        "capability": result.capability,
        "details": result.details,
    }


def root() -> dict[str, str]:
    return {"service": "ideaos", "version": __version__}


app.get("/v1/health")(health)
app.get("/")(root)
