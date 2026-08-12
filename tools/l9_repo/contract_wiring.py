from __future__ import annotations

from pathlib import Path
from typing import Any


class ContractWiringError(RuntimeError):
    """Raised when authoritative contracts are absent or undiscoverable."""


def _reference_patterns(target: str) -> tuple[str, str]:
    return (f"]({target})", f"`{target}`")


def validate_contract_wiring(root: Path, spec: dict[str, Any]) -> None:
    errors: list[str] = []
    for relative in spec["required_files"]:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing authoritative file: {relative}")

    for requirement in spec["reference_requirements"]:
        target = requirement["target"]
        matched = False
        inspected: list[str] = []
        for instruction_relative in requirement["instruction_files"]:
            instruction_path = root / instruction_relative
            inspected.append(instruction_relative)
            if not instruction_path.is_file():
                continue
            try:
                content = instruction_path.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                errors.append(
                    f"cannot read instruction file {instruction_relative}: {error}"
                )
                continue
            if any(pattern in content for pattern in _reference_patterns(target)):
                matched = True
                break
        if not matched:
            errors.append(
                f"authoritative path {target} is not referenced exactly by "
                + ", ".join(inspected)
            )

    if errors:
        raise ContractWiringError("; ".join(errors))
