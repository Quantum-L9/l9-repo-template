# Secret rotation checklist (local ops)

Opt-in process doc — not a scheduled GitHub Action.

Quarterly (or after any suspected leak):

- [ ] Rotate any app-specific API tokens / signing keys used by this service
- [ ] Update GitHub Actions secrets / Dependabot secrets for this repo
- [ ] Revoke old keys after cutover
- [ ] Confirm `make preflight` and `make verify` still pass

This checklist covers credentials this repository itself holds. A credential
owned by another product (a Constellation node, the Gate, a shared provider) is
rotated under that product's own runbook, by that product's owner; do not route
it through this repository or through this factory.

Org secret-scanning enablement: see Quantum-L9/.github `scripts/enable-secret-scanning.sh`.
