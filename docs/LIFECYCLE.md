# Lifecycle — L9 repository birth factory

## Birth

1. `make new-repo` (or the remote front door `make birth`) with a compiled
   product payload, or GitHub **Use this template** for a manual start.
2. `make rename PKG=your_pkg`
3. `make verify`
4. Optional: `make run` / `make obs-up` for the reference payload

Details: [ops/REPO_BIRTH.md](ops/REPO_BIRTH.md). What semantic product is being
born is decided upstream and arrives resolved; the factory assembles, validates,
seals, publishes, and attests.

## Day-to-day

- Edit `src/` and helpers; keep hygiene (no eval/exec/print).
- Re-render Cursor rules after `plugin-config.yaml` edits: `make render-rules`.
- Keep chassis and reference payload apart as declared in
  `scripts/birth-runner/payload-ownership.yaml`.

## Boundary

- The factory owns how a repository is born, never what product it is.
  ProductKind, ProductTopology, ProductManifest and archetype semantics are
  upstream inputs; nothing here infers them from repository shape.
- The Python/FastAPI package is a reference payload that exercises the chassis;
  it is not factory law and does not limit which products the factory births.
- Do not grow this repository into a product: a born repository owns its product
  tree, the factory owns the birth machinery.
