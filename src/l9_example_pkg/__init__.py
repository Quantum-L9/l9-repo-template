"""Example Quantum-L9 Python package (non-Constellation museum)."""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ErrorCode",
    "PackageError",
    "PackageConfigError",
    "get_example_config",
    "health_check",
]


def __getattr__(name: str) -> Any:
    if name in {"ErrorCode", "PackageError", "PackageConfigError"}:
        from l9_example_pkg.errors import ErrorCode, PackageConfigError, PackageError

        return {
            "ErrorCode": ErrorCode,
            "PackageError": PackageError,
            "PackageConfigError": PackageConfigError,
        }[name]
    if name == "get_example_config":
        from l9_example_pkg.settings import get_example_config

        return get_example_config
    if name == "health_check":
        from l9_example_pkg.health import health_check

        return health_check
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
