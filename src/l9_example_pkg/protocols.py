"""Optional typing protocols for pluggable checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from l9_example_pkg.health import HealthResult


@runtime_checkable
class HealthCheckable(Protocol):
    def check_health(self) -> HealthResult: ...


@runtime_checkable
class Configurable(Protocol):
    def validate_safe(self) -> list[str]: ...
