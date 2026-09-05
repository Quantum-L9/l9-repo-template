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
    "tests/test_expansion_gate.py",
    "tests/test_decision_package.py",
]
for rel in required:
    if not (ROOT / rel).exists():
        errors.append(f"missing {rel}")

# Fail-closed authority chain. Each check below exists because the corresponding
# bypass was reproduced against 11.4.0: a forged READY receipt was accepted, a
# BLOCKED handoff with an empty blocker list was issued a READY receipt, the
# decision validator never loaded its own schema, and the installer admitted a
# synthetic tree containing three placeholder files.
lifecycle_src = (ROOT / "src/ideaos/lifecycle.py").read_text(encoding="utf-8")
if "gate_expansion(expansion_packet)" not in lifecycle_src:
    errors.append("decision handoff does not recompute the expansion gate")

expansion_src = (ROOT / "src/ideaos/expansion.py").read_text(encoding="utf-8")
if "UPSTREAM_HANDOFF_BLOCKED" not in expansion_src:
    errors.append("expansion gate does not block on a BLOCKED handoff with no listed blockers")
if "gate_policy_digest" not in expansion_src:
    errors.append("expansion gate receipt does not carry a gate policy digest")

package_validator = (
    ROOT / "modules/idea-expander-decision-node/scripts/validate_decision_package.py"
).read_text(encoding="utf-8")
if "decision-output.schema.json" not in package_validator:
    errors.append("decision package validator does not load its declared schema")
if "Draft202012Validator" not in package_validator:
    errors.append("decision package validator does not perform Draft 2020-12 validation")

installer = (ROOT / "scripts/apply_lifecycle_to_ideaos.py").read_text(encoding="utf-8")
for token, why in (
    ("rev-parse", "installer does not check the target's git HEAD"),
    ("--porcelain", "installer does not require a clean worktree"),
    ("BACKUP", "installer does not take a backup before overwriting"),
    ("tests/test_expansion_gate.py", "installer does not install the lifecycle regression tests"),
):
    if token not in installer:
        errors.append(why)

# No evidence path may point at a layout this pack does not have.
for rel in ("TRACEABILITY.yaml", "VALIDATION.md", "README.md"):
    if "runtime_overlay" in (ROOT / rel).read_text(encoding="utf-8"):
        errors.append(f"{rel} references the removed runtime_overlay/ layout")

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
