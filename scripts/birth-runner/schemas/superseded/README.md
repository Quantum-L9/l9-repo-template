# Superseded birth contracts

Historical evidence only. Nothing under this directory is read by any gate,
packager, adapter, front door or workflow: these schemas describe artifacts that
earlier births carried, so a reader of an old bundle or an old birth record can
still interpret it exactly. No live code path admits them.

| File | Was | Superseded by |
|---|---|---|
| `l9-product-birth-binding.v1.schema.json` | `l9.product-birth-binding/v1` — bound a product realization through a mandatory `l9.repo-birth-contract/v1` | `l9.product-birth-binding/v2` (`../l9-product-birth-binding.schema.json`), BIRTH-ARCH-REVISION-001 |
| `birth-contract.v1.schema.json` | `l9.repo-birth-contract/v1` — carried IdeaOS / GAR / Plan / campaign / Program Execution lineage digests and acceptance evidence as a birth prerequisite | nothing: product resolution is reproduced from the source snapshot by the pinned semantic compiler in PREPARE; lineage is no longer a birth input |

The `l9.repo-birth-evidence/v1` document the v1 packager consumed had no
published schema; its shape is recoverable from the retired `lineage` block of
`birth-contract.v1.schema.json`.

A bundle that still carries a `birth_contract` coordinate, or a binding whose
`schema` is `l9.product-birth-binding/v1`, is refused by the v2 adapter as a
schema-identity failure. There is no compatibility path through v1.
