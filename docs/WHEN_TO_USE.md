# When to use l9-repo-template

`l9-repo-template` is the generic Quantum-L9 **repository birth factory**. Use
it whenever an L9 repository needs to be born — the factory assembles the
chassis, applies the organization's birth profile, verifies the compiled product
payload, seals provenance, publishes the root commit and attests the remote.

## What the factory decides

- How a repository is assembled, validated, sealed, published and attested.
- Which template surfaces are chassis and which are the reference example
  payload (`scripts/birth-runner/payload-ownership.yaml`).
- Whether a payload is additive or authoritative (by `repository_shape`, which
  is payload-authority evidence only).

## What the factory does not decide

- **Product semantics.** ProductTopology, ProductManifest, ProductKind (Node,
  Dependency) and archetype obligations are owned upstream by
  `Quantum-L9/.github` `semantics/` and the product semantic owner. They arrive
  as resolved inputs; the factory never infers them from repository shape,
  package contents, SDK presence, Gate presence, repo class, or template
  ancestry.
- **Product SDK compatibility.** Whether a born product uses a Gate SDK, a node
  SDK, or none is product-owned.
- **Organization policy.** What a repository receives at birth is decided by
  its org repo class in `Quantum-L9/.github` `policies/repo-classes.yml`.

## Reference payload

The Python/FastAPI package under `src/` is an example payload that exercises the
chassis. A real product supplies its own compiled payload; the example is then
removed where the payload is authoritative. The example is not factory law and
does not limit which product kinds the factory can birth.

## Not yet here

The birthing adapter that turns resolved product semantics into a birth request
is a separate, future campaign. This repository only names that boundary.
