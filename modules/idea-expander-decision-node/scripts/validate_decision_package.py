#!/usr/bin/env python3
"""Validate a decision package against its declared schema and the board's decision law.

This script is an authorization gate, not a formatter. It previously performed a
handful of hand-written shape checks and never loaded decision-output.schema.json
at all, so a package declaring `decision: "BANANA"` with integer board votes passed,
and so did a GO carrying an unresolved critical red-team finding — the exact case
references/red-team-protocol.md says must force HOLD or NO_GO.

Two passes, both fail-closed:
  1. Draft 2020-12 validation against the declared contract.
  2. The semantic decision law that structure cannot express, quoted at each check
     from the reference that owns it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "decision-output.schema.json"
SCHEMA_ID = "ideaos.decision-node-output/v3"
STOPPED = {"HOLD", "NO_GO"}


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def schema_errors(doc: object) -> list[str]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:  # never degrade to "no schema check"
        fail(
            "jsonschema is required to validate the decision contract. "
            "Install it (pip install jsonschema) — this gate does not run without it."
        )
    validator = Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    return [
        f"{'.'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: validate_decision_package.py <decision-package.json>")
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    errors = schema_errors(doc)
    if errors:
        print("FAIL: decision package does not satisfy", SCHEMA.name)
        for e in errors:
            print("-", e)
        raise SystemExit(1)

    decision = doc["decision"]
    conditions = doc["conditions"]
    findings = doc["red_team"]["findings"]
    critical = [f for f in findings if f["severity"] == "critical"]

    # red-team-protocol.md: "unresolved critical findings force HOLD or NO_GO"
    unresolved = [f["id"] for f in critical if f["disposition"] == "unresolved"]
    if unresolved and decision not in STOPPED:
        fail(
            f"decision {decision} is not permitted with unresolved critical findings "
            f"{unresolved}; unresolved critical findings force HOLD or NO_GO"
        )

    # polycognitive-board.md: "any confirmed fatal blocker prevents unconditional GO"
    conditioned = [f["id"] for f in critical if f["disposition"] == "converted_to_condition"]
    if conditioned and decision == "GO":
        fail(
            f"unconditional GO is not permitted while critical findings {conditioned} are "
            "carried as conditions; the decision is CONDITIONAL_GO"
        )
    if conditioned and decision == "CONDITIONAL_GO" and not conditions:
        fail(
            f"critical findings {conditioned} were converted to conditions, but the package "
            "carries no conditions"
        )

    # polycognitive-board.md: "CONDITIONAL_GO requires executable gates"
    if decision == "CONDITIONAL_GO" and not conditions:
        fail("CONDITIONAL_GO requires at least one executable gate in conditions")
    if decision == "GO" and conditions:
        fail("GO is unconditional; a decision carrying conditions is CONDITIONAL_GO")

    # polycognitive-board.md: "preserve every member's memo and minority vote"
    minority = sorted({v["member"] for v in doc["board_votes"] if v["vote"] != decision})
    if minority and not doc["dissent"]:
        fail(f"board members {minority} voted against {decision} but dissent register is empty")

    # A stop must say what would change it.
    if decision in STOPPED and not doc["evidence_acquisition"] and not critical:
        fail(f"{decision} requires an evidence acquisition plan or a critical finding")

    print("PASS")


if __name__ == "__main__":
    main()
