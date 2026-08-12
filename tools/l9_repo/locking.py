from __future__ import annotations

import contextlib
import os
import pathlib
import time
from collections.abc import Iterator


class LockBusy(RuntimeError):
    """Raised when another repository mutation owns the single-flight lock."""


def _owner_is_alive(owner: pathlib.Path) -> bool:
    try:
        pid = int(owner.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def single_flight(path: pathlib.Path, *, stale_after: int = 1800) -> Iterator[None]:
    """Acquire a directory lock and remove it after the guarded operation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            age = 0
        if age <= stale_after:
            raise LockBusy(f"operation already running: {path}") from None
        try:
            entries = list(path.iterdir())
            if any(
                entry.name != "owner" or entry.is_symlink() or not entry.is_file()
                for entry in entries
            ):
                raise LockBusy(f"stale lock not safely removable: {path}")
            owner = path / "owner"
            if owner.is_file() and _owner_is_alive(owner):
                raise LockBusy(f"operation owner is still running: {path}")
            owner.unlink(missing_ok=True)
            path.rmdir()
            path.mkdir()
        except LockBusy:
            raise
        except OSError as error:
            raise LockBusy(f"stale lock not safely removable: {path}") from error

    try:
        (path / "owner").write_text(f"{os.getpid()}\n", encoding="utf-8")
        yield
    finally:
        try:
            (path / "owner").unlink(missing_ok=True)
            path.rmdir()
        except OSError:
            pass
