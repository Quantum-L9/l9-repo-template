# Expansion Stage Boundary

## Problem closed

Earlier IdeaOS doctrine described Wide -> Deep -> Return-to-Center, but the upstream expansion responsibility was not a first-class module. The decision node therefore depended on a "developed dossier" without a canonical producer contract.

## Canonical seam

```text
IdeaOS cognition
  -> idea-expander
  -> ExpandedIdeaDossierPacket
  -> expansion gate
  -> idea-expander-decision-node
  -> IdeaDecisionPacket / authorization
```

The stage is deliberately split:
- creativity stays model-owned;
- structural handoff validity is deterministic;
- investment/execution adjudication stays downstream.

This prevents both failure modes: rigid code pretending to invent the idea, and creative expansion silently declaring itself execution-ready.
