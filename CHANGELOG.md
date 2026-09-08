# Changelog

## 11.4.1 — Fail-Closed Authority Chain

Adversarial review of 11.4.0 reproduced four bypasses of the fail-closed promise.
Each is closed here with the regression that reproduces it.

- **decision handoff recomputes the expansion gate.** A structurally valid READY
  `ExpansionGateReceipt` could be hand-written for a packet the real gate BLOCKS:
  digest binding proved the packet was unedited, never that a gate issued the
  receipt. `build_decision_node_input` now recomputes `gate_expansion` and accepts
  only the receipt the gate itself produces.
- **`ExpansionGateReceipt` carries `gate_policy_digest`**, so a receipt issued
  under a different gate policy is not equal to the current gate's and is rejected.
- **a BLOCKED handoff can no longer yield a READY receipt.** The gate enumerated
  upstream blockers, so `{"status": "BLOCKED", "blockers": []}` contributed none
  and passed. BLOCKED is now itself a blocker (`UPSTREAM_HANDOFF_BLOCKED`).
- **`validate_decision_package.py` validates its declared contract.** It never
  loaded `decision-output.schema.json`; a package with `decision: "BANANA"` and
  integer board votes returned PASS. It now runs Draft 2020-12 validation, then
  the board's own decision law: unresolved critical findings force HOLD or NO_GO,
  a conditioned critical finding forbids unconditional GO, CONDITIONAL_GO requires
  executable gates, and a minority vote requires a dissent register.
- **decision output is `ideaos.decision-node-output/v3`**: red-team findings carry
  the full shape `red-team-protocol.md` declares (severity and disposition, so
  "unresolved" is machine-checkable), conditions carry a `trigger`, board votes
  carry `confidence`, and the package binds to `decision_node_input_digest`.
- **`validate_decision_input.py` re-runs the real gate** rather than approximating
  it, and fails closed when the runtime is unavailable.
- **the installer is bound to the baseline commit.** Admission was three path
  existence checks, which a synthetic tree satisfied; it is now git identity plus
  a clean worktree, with a timestamped backup and rollback on failure, and it
  installs the lifecycle regression tests alongside the behaviour they guard.
- archived the 11.3 validator and report, which assert a `runtime_overlay/` layout
  this pack does not have; repaired the same dead path in `TRACEABILITY.yaml`.
- converged `composition.md` and `integration-patch.md` onto the canonical 11.4
  topology and removed the backward-compatible direct-dossier language.

Known and unchanged: the decision-node-output to canonical `IdeaDecisionPacket`
mapping is still not evidenced in this pack (it may be baseline-owned), and the
1-5 five-dimension scoring in `three-perspective-swot.md` still does not match the
schema's single 0-10 perspective score. Both need the bound 11.2 baseline to
settle and neither is repaired here.

## 11.4.0 — Lifecycle Complete

- promoted `idea-expander` into the canonical IdeaOS lifecycle
- added machine-readable `pipeline/IDEA_LIFECYCLE.yaml`
- added first-class `decision_handoff` runtime operation
- added `DecisionHandoffRequest`, `DecisionContext`, and `IdeaExpanderDecisionNodeInput v3` schemas
- bound decision input to the exact READY `ExpansionGateReceipt`
- enforced `receipt.input_digest == semantic_digest(expansion_packet)`
- hardened decision-node validator against stale/tampered post-gate dossiers
- added tamper regression fixture
- added lifecycle handoff unit tests
- updated expander and decision-node Skill contracts
- added canonical lifecycle and handoff architecture/protocol docs
- removed the conceptual trust-by-claim path from expand to decide

## 11.3.0 — Expansion Hardened

- added `idea-expander`
- added deterministic expansion gate
- added expanded dossier contracts and decision-node handoff doctrine
