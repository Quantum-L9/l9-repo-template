"""Single source of the runtime version.

The value is the pack's own `VERSION` file. It is duplicated here rather than
read at import time because `runtime_capabilities()` stamps it into every
receipt: a runtime that cannot state its version without touching the filesystem
cannot state it when installed as a wheel.
"""

from __future__ import annotations

__version__ = "11.4.0"

__all__ = ["__version__"]
