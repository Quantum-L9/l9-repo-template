"""Optional retry helper for local I/O (never peer/Constellation routing)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

_F = TypeVar("_F", bound=Callable[..., Any])


def with_retry(
    *,
    max_attempts: int = 3,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
    reraise: bool = True,
) -> Callable[[_F], _F]:
    """Retry with exponential back-off when tenacity is installed; else no-op."""
    try:
        from tenacity import retry, stop_after_attempt, wait_exponential
    except ImportError:

        def no_op_decorator(fn: _F) -> _F:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return fn(*args, **kwargs)

            return cast(_F, wrapper)

        return no_op_decorator

    decorator: Callable[[_F], _F] = retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=wait_min, max=wait_max),
        reraise=reraise,
    )
    return decorator
