from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Sequence


class PreflightError(RuntimeError):
    """Raised when a local push safety check fails."""


def run(
    argv: Sequence[str],
    root: pathlib.Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=root,
        text=True,
        capture_output=True,
        check=check,
    )


def verify_no_unmerged(root: pathlib.Path) -> None:
    result = run(["git", "diff", "--name-only", "--diff-filter=U"], root)
    if result.stdout.strip():
        names = result.stdout.strip().replace("\n", ", ")
        raise PreflightError(f"unmerged paths: {names}")


def verify_index(root: pathlib.Path) -> None:
    result = run(["git", "diff", "--cached", "--check"], root, check=False)
    if result.returncode:
        output = (result.stdout + result.stderr).strip()
        raise PreflightError(f"staged diff check failed:\n{output}")


def verify_lockfile(root: pathlib.Path, command: Sequence[str]) -> None:
    if not command:
        return
    result = run(command, root, check=False)
    if result.returncode:
        output = (result.stdout + result.stderr).strip()
        rendered = " ".join(command)
        raise PreflightError(f"lockfile check failed: {rendered}\n{output}")


def verify(root: pathlib.Path, lockfile_command: Sequence[str]) -> None:
    verify_no_unmerged(root)
    verify_index(root)
    verify_lockfile(root, lockfile_command)
