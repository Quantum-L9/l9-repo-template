# l9-repo-template

Thin **Python** GitHub Template for Quantum-L9.

Use this repository instead of `cryptoxdog/golden-repo`.

## Quick start (derived repo)

1. **Use this template** on GitHub (or clone).
2. Rename the example package:

   ```bash
   make rename PKG=your_pkg
   ```

3. Verify locally:

   ```bash
   make verify
   ```

4. Refresh CI from the org pack (after pin bumps):

   ```bash
   make sync-ci
   ```

## Org source vs inherit

CI pack, Dependabot, CODEOWNERS, and LICENSE are pulled from
[Quantum-L9/.github](https://github.com/Quantum-L9/.github) via `make sync-ci`
(see `.l9/ci-pin`).

Community health files (`CONTRIBUTING`, `SECURITY`, `SUPPORT`, `CODE_OF_CONDUCT`,
`FUNDING`, issue/PR templates) **inherit** from the org — do not fork copies here.

## Layout

See [ARCHITECTURE.md](ARCHITECTURE.md) and [TEMPLATE_INVENTORY.md](TEMPLATE_INVENTORY.md).
