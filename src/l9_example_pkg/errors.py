"""Structured package errors (PackageTemplate pattern)."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    UNKNOWN = "EXAMPLE_UNKNOWN"
    CONFIG_INVALID = "EXAMPLE_CONFIG_INVALID"
    RUNTIME_FAILURE = "EXAMPLE_RUNTIME_FAILURE"


class PackageError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str | ErrorCode = ErrorCode.UNKNOWN,
        context: dict[str, object] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code.value if isinstance(code, ErrorCode) else code
        self.context: dict[str, object] = context or {}
        self.cause: BaseException | None = cause
        if cause is not None:
            self.__cause__ = cause


class PackageConfigError(PackageError):
    def __init__(
        self,
        message: str,
        *,
        code: str | ErrorCode = ErrorCode.CONFIG_INVALID,
        context: dict[str, object] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context, cause=cause)
