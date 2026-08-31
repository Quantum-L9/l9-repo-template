#!/usr/bin/env python3
"""The template's payload-ownership contract, read once for every reader of it.

`payload-ownership.yaml` answers one question — *what does a product inherit
from this template, and what does it own?* — and three components now need that
answer:

    compile_birth_payload.py   classifies a source snapshot: authoritative or additive
    verify_birth_payload.py    re-derives that classification rather than trusting it
    new_repo.py                reconciles product surfaces during assembly

Two copies of a contract reader are two contracts. This module is the one
reader; the file it reads stays the one authority (BP-008).

Dependency-free on purpose, exactly like `birth_provenance.py`: the contract is
JSON-in-YAML so it can document itself in comments without this template taking
a YAML dependency to read its own birth rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Read from the TEMPLATE source, never from a payload: a payload does not get to
# widen the set of template surfaces it silently keeps.
OWNERSHIP_PATH = "scripts/birth-runner/payload-ownership.yaml"

REQUIRED_KEYS = ("repository_shape", "product", "chassis")

# Directories never carried from one tree into another. `.git` would make a
# newborn a fork of somebody else's history; the rest is machine state.
COPY_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".eggs",
        "node_modules",
    }
)

# Build metadata carries the *source's* package name. Copying it would hand a
# newborn a stale `l9_example_pkg.egg-info` describing a package it does not have.
COPY_EXCLUDE_SUFFIXES = (".egg-info",)


class OwnershipContractError(RuntimeError):
    """The ownership contract is missing or unusable. Callers translate this."""


def is_machine_state(rel: Path) -> bool:
    return any(part in COPY_EXCLUDE_DIRS for part in rel.parts) or any(
        part.endswith(COPY_EXCLUDE_SUFFIXES) for part in rel.parts
    )


def load_ownership(template_src: Path) -> dict:
    """Read the template's payload-ownership contract.

    JSON-in-YAML, exactly like the organization policy, and for the same reason:
    the file has to explain itself in comments and this script has no YAML
    dependency. Fails closed — a missing or unreadable contract must stop a
    birth, not silently fall back to "the template owns everything", which is
    the defect this contract exists to remove.
    """
    path = template_src / OWNERSHIP_PATH
    if not path.is_file():
        raise OwnershipContractError(
            f"template has no payload ownership contract at {OWNERSHIP_PATH} — "
            "an authoritative payload cannot be reconciled without it"
        )
    stripped = re.sub(r"^[ \t]*#.*$", "", path.read_text(encoding="utf-8"), flags=re.M)
    try:
        doc = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise OwnershipContractError(f"{OWNERSHIP_PATH} is not JSON-in-YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise OwnershipContractError(f"{OWNERSHIP_PATH} is not a mapping")
    for key in REQUIRED_KEYS:
        value = doc.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
            raise OwnershipContractError(f"{OWNERSHIP_PATH} has no usable {key!r} list")
    return doc


def is_repository_payload(payload: Path, ownership: dict) -> bool:
    """Is this payload a standalone repository, or a fragment?

    Positive identification only, against the declared `repository_shape`. Every
    listed path must be present. A payload that is merely large, or that happens
    to carry a `src/` directory, stays an additive overlay — the pre-existing
    behavior, which products already depend on.
    """
    return all((payload / rel).exists() for rel in ownership["repository_shape"])


def matched_shape(payload: Path, ownership: dict) -> list[str]:
    """The `repository_shape` paths this payload actually carries.

    Evidence, not intent: a compiled payload records what was found, so a reader
    can see WHY the classification came out the way it did without re-running
    the compiler against a tree that may no longer exist.
    """
    return [rel for rel in ownership["repository_shape"] if (payload / rel).exists()]


def payload_package_dirs(payload: Path) -> list[str]:
    """The Python packages a repository-shaped payload declares under `src/`."""
    src = payload / "src"
    if not src.is_dir():
        return []
    return sorted(
        child.name
        for child in src.iterdir()
        if child.is_dir()
        and child.name not in COPY_EXCLUDE_DIRS
        and not child.name.endswith(COPY_EXCLUDE_SUFFIXES)
    )
