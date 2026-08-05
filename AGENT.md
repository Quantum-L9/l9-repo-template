# AGENT.md — L9 governance context (l9-repo-template)

Governance contract scaffold. This template ships `AGENT.md` so repos created
from it satisfy the L9 Implementer preflight out of the box. Customize the
"Repository role" and protected paths for your repo; keep the invariants.

## Repository role

`l9-repo-template` is the starter template for new L9 repos. It owns only the
thin caller workflow (`ci.yml` → `Quantum-L9/l9-ci-core` reusable workflows) and
default config (pyproject, pre-commit, gitleaks). It must not copy SDK logic,
workflow internals, or policy engines.

## Wire contract

TransportPacket is the only supported wire contract. `PacketEnvelope` is
superseded and must not be reintroduced. Retired legacy tooling has no
references here, and there is no public packet-envelope command. (The
`pr-checks.yml` template-validation gate enforces zero legacy references.)

## Implementer invariants (non-negotiable)

1. **Write, never merge.** `GITHUB_TOKEN` (or `L9_IMPLEMENTER_BOT_TOKEN`) with
   `pull-requests: write` / `issues: write`. Never merge, never edit branch
   protection, never mutate repository settings.
2. **Proposal-only by default:** `dry_run`, `PR_FIX_LLM_APPLY=0`, no push.
3. **Deterministic autofixes never call an LLM;** the LLM lane respects protected
   paths and never-auto-repair categories, with verify/rollback on every change.
4. **Fork safety.** Secret-dependent jobs are same-repo only. Never
   `pull_request_target`.

## Protected paths (never auto-repair) — customize per repo

- `.github/workflows/**` (the caller wiring).
- release/tag configuration.

## Never-auto-repair categories

- Security findings requiring human judgement.
- Governance policy changes.
- Anything altering the TransportPacket contract.

## Escalation

See `docs/ci-enablement/RUNBOOK.md`. Autonomy is raised only by explicit
operator dispatch.
