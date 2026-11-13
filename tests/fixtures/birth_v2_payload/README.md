# V2 + Biome repository-shaped payload fixture

Copied verbatim from `Quantum-L9/l9-ci-core` at `ff4d6c9a11c2` and stored here
under `.fixture` names, so that nothing in this template ever reads them as its
own execution surfaces:

| Fixture | Core source |
|---|---|
| `Makefile.fixture` | `tools/l9_repo/facades/make-v1.mk` (the generated make-v1 facade) |
| `repo-workflow.json.fixture` | `.l9/repo-workflow.json` (`l9.repo-execution/v2`) |
| `biome.json.fixture` | `presets/typescript/biome.json` |
| `biomeignore.fixture` | `presets/typescript/.biomeignore` |
| `editorconfig.fixture` | `presets/typescript/.editorconfig` |

`tests/integration/test_v2_payload_birth.py` assembles a synthetic
repository-shaped payload from these plus a repository-owned `Repo.mk`. It then
proves that a local birth under `org_seeded_self_governed` carries every surface
through byte for byte, and that it retires the template's own V1 execution runtime.

The bytes only need to be Core-shaped. They do not track Core, and a Core
release does not oblige an update here.
