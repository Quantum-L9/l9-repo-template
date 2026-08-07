# Secret rotation checklist (local ops)

Opt-in process doc — not a scheduled GitHub Action.

Quarterly (or after any suspected leak):

- [ ] Rotate any app-specific API tokens / signing keys used by this service
- [ ] Update GitHub Actions secrets / Dependabot secrets for this repo
- [ ] Revoke old keys after cutover
- [ ] Confirm `make preflight` and `make verify` still pass

For Constellation node / Gate credential rotation, use L9-Node-Template / Gate ops docs.

Org secret-scanning enablement: see Quantum-L9/.github `scripts/enable-secret-scanning.sh`.
