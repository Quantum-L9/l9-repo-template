"""Immutable health snapshot."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from ideaos import __version__
from ideaos.settings import get_example_config

_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class HealthResult:
    capability: str
    version: str
    enabled: bool
    status: str
    warnings: list[str]
    details: dict[str, object]

    def is_ok(self) -> bool:
        return self.status == "ok"


def health_check() -> HealthResult:
    with _LOCK:
        cfg = get_example_config()
        warnings = cfg.validate_safe()
        if not cfg.enabled:
            status = "disabled"
        elif warnings:
            status = "degraded"
        else:
            status = "ok"
        return HealthResult(
            capability=cfg.service_name,
            version=__version__,
            enabled=cfg.enabled,
            status=status,
            warnings=warnings,
            details={"service_name": cfg.service_name},
        )
