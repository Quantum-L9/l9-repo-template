#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

required = [
    "modules/idea-expander/SKILL.md",
    "modules/idea-expander-decision-node/SKILL.md",
    "pipeline/IDEA_LIFECYCLE.yaml",
    "architecture/06_CANONICAL_IDEA_LIFECYCLE.md",
    "protocols/08B_EXPANSION_TO_DECISION_HANDOFF.md",
    "src/ideaos/expansion.py",
    "src/ideaos/lifecycle.py",
    "src/ideaos/runtime.py",
    "src/ideaos/resources/schemas/expansion_packet.schema.json",
    "src/ideaos/resources/schemas/expansion_gate_receipt.schema.json",
    "src/ideaos/resources/schemas/decision_handoff_request.schema.json",
    "src/ideaos/resources/schemas/decision_node_input.schema.json",
    "tests/test_decision_handoff.py",
]
for rel in required:
    if not (ROOT / rel).exists():
        errors.append(f"missing {rel}")

# No parallel decision-node input schema drift.
a = ROOT / "src/ideaos/resources/schemas/decision_node_input.schema.json"
b = ROOT / "modules/idea-expander-decision-node/schemas/node-input.schema.json"
if a.exists() and b.exists() and a.read_bytes() != b.read_bytes():
    errors.append("decision-node input schema drift between runtime and module")

# Canonical lifecycle contract text checks.
lifecycle = (ROOT / "pipeline/IDEA_LIFECYCLE.yaml").read_text(encoding="utf-8")
for token in ("create", "expand", "expansion_gate", "decision_handoff", "decide", "execute"):
    if token not in lifecycle:
        errors.append(f"lifecycle missing stage/token {token}")
if "input_digest == semantic_digest(expansion_packet)" not in lifecycle:
    errors.append("lifecycle missing exact digest-binding invariant")

# Decision module must require v3 + receipt.
skill = (ROOT / "modules/idea-expander-decision-node/SKILL.md").read_text(encoding="utf-8")
if "IdeaExpanderDecisionNodeInput v3" not in skill:
    errors.append("decision skill does not require v3 input")
if "ExpansionGateReceipt" not in skill:
    errors.append("decision skill does not require gate receipt")

if errors:
    print("FAIL")
    for e in errors:
        print("-", e)
    raise SystemExit(1)

print("PASS")
print("IdeaOS 11.4 lifecycle topology and exact expansion-to-decision binding are present")
