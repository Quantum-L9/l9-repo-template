# Secret rotation checklist (local ops)

Opt-in process doc — not a scheduled GitHub Action.

Quarterly (or after any suspected leak):

- [ ] Rotate Gate / node signing keys (`L9_SIGNING_*` / verifying keys)
- [ ] Rotate `GATE_URL` credentials / admin tokens if applicable
- [ ] Update GitHub Actions secrets / Dependabot secrets for this repo
- [ ] Revoke old keys after cutover
- [ ] Confirm `make preflight` / worker health still pass against Gate

Org secret-scanning enablement: see Quantum-L9/.github `scripts/enable-secret-scanning.sh`.
