"""Immutable health snapshot (PackageTemplate pattern)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from l9_example_pkg.settings import get_example_config

_LOCK = threading.Lock()

try:
    _VERSION = version("l9-example-pkg")
except PackageNotFoundError:
    _VERSION = "0.0.0+unknown"


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
            version=_VERSION,
            enabled=cfg.enabled,
            status=status,
            warnings=warnings,
            details={"service_name": cfg.service_name},
        )
