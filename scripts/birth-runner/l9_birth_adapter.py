#!/usr/bin/env python3
"""The product-to-birth adapter boundary: is THIS realization admissible for THIS birth?

Upstream, a product is authored as a ProductTopology, compiled by the semantic
compiler into a resolved ProductManifest, and realized as a source tree.
Downstream, this factory births a repository from an immutable snapshot of that
tree under a compiled, digest-bound `l9.birth-payload/v1`. Nothing in that chain
is this module's to decide. The adapter sits between the two and answers
exactly one question:

    Is this exact, compiler-resolved product realization admissible as input to
    this exact repository birth operation, and are the product, source,
    payload, factory, compiler and manifest coordinates mutually consistent?

It does not answer what the product should be, what ProductKind it has, which
archetype applies, how source is generated, what capabilities it possesses, or
how the organization classifies the repository. Those are upstream authority
(`Quantum-L9/.github` `semantics/`, the product semantic owner, the semantic
compiler) and the adapter only reads the coordinates they already resolved.

    ProductTopology  ->  semantic compiler (pinned)  ->  resolved ProductManifest
                                                               |
                                                    realized source snapshot
                                                               |
                                                    l9.birth-payload/v1
                                                               |
                                             l9.product-birth-binding/v2
                                                               |
                                                        THIS ADAPTER
                                                               |
                                      PREPARE re-runs the pinned compiler
                                      (product_resolution.py), then births

What the adapter consumes:

    binding          l9.product-birth-binding/v2 — the exact coordinates the
                     caller claims: product id + kind, manifest ref + digest,
                     topology ref + digest, source repository/revision/tree,
                     payload ref + digest, factory repository + revision, and
                     the compiler engine + the exact input paths it read.
    manifest         the ProductManifest artifact (l9.product-manifest/v1)
    payload          the compiled l9.birth-payload/v1 the binding names

What comes out is a BindingResult: admissible or not, the exact validated
coordinates when it is, and every deterministic reason when it is not. It is
EVIDENCE for the birth factory — authority class `evidence` in the organization
authority model — and grants nothing: not mutation, not governance, not
semantic, not release authority. Nothing here calls the birth engine, runs the
semantic compiler, reads a source tree, inspects repository shape, or infers a
ProductKind; the manifest either states the kind explicitly or the realization
is not admissible.

v2 (BIRTH-ARCH-REVISION-001). The v1 binding bound the realization through a
mandatory `l9.repo-birth-contract/v1` carrying IdeaOS, GAR, Plan, campaign and
Program Execution lineage digests. None of that is a birth prerequisite any
more: product resolution is reproduced by the pinned semantic compiler in
PREPARE, and source integrity is the compiled payload's. A binding that still
names a birth contract, or claims the v1 schema, is malformed here — there is
no compatibility path through v1 (schemas/superseded/).

Digests. The manifest's `manifest_digest` is a semantic digest whose
canonicalization belongs to the semantic compiler, so it is compared as an
exact opaque string and never recomputed here; PREPARE reproduces it by running
that compiler. The payload digest follows the factory's own artifact convention
— `sha256:` over the bytes of the artifact as written — the same one
`compile_birth_payload.py` and the packager (`package_birth_handoff.py`) use.

Unresolved state fails closed. The upstream schema says a manifest may carry
`unresolved` entries while only HARD gaps block the resolved-manifest gate, but
it does not define a per-entry severity this adapter could read without
interpreting semantics it does not own. So every unresolved entry is treated as
hard: an admissible realization carries an empty `unresolved` list. Authority
is explicit or nothing, for the same reason: a manifest whose `authority` block
does not name its semantic owner and the authority revision it was resolved
under is not a resolved manifest at this boundary.

    l9_birth_adapter.py --binding FILE --manifest FILE --payload FILE [--json]

Exit 0 when admissible, 1 when not, 2 when an input cannot be read at all.
Dependency-free at runtime, like the rest of the birth engine. Authority cited:
`Quantum-L9/.github@43600db3` `semantics/product_manifest.schema.yaml`,
`semantics/product_kinds.yaml`, `semantics/authority_model.yaml`; the engine
coordinate is this factory's own `scripts/birth-runner/semantic-compiler.pin.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


def _load_sibling(name: str):
    """Load a module that lives next to this file, wherever this file lives."""
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the birth module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# The payload document validator is the factory's existing l9.birth-payload/v1
# gate. Reused, not restated: a second validator is a second contract.
compiler = _load_sibling("compile_birth_payload")

SCHEMA = "l9.product-birth-binding/v2"
RESULT_SCHEMA = "l9.product-birth-binding-result/v2"
SCHEMA_PATH = "scripts/birth-runner/schemas/l9-product-birth-binding.schema.json"

MANIFEST_SCHEMA = "l9.product-manifest/v1"
PAYLOAD_SCHEMA = compiler.SCHEMA

# `required` of semantics/product_manifest.schema.yaml at the cited revision. A
# manifest missing one of these is not "resolved enough for birth" whatever its
# `unresolved` list says. Structural completeness only — no field is interpreted.
MANIFEST_REQUIRED_KEYS = (
    "schema",
    "product",
    "source_topology",
    "authority",
    "identity",
    "requirements",
    "capabilities",
    "architecture",
    "ports",
    "adapters",
    "relationships",
    "technology",
    "bindings",
    "providers",
    "admission",
    "lifecycle",
    "conformance",
    "compiler",
    "provenance",
    "unresolved",
    "manifest_digest",
)
MANIFEST_PRODUCT_KEYS = ("id", "kind", "archetype_ref")
MANIFEST_TOPOLOGY_KEYS = ("ref", "digest")
MANIFEST_COMPILER_KEYS = ("profile_ref", "profile_digest", "compiler_version")
MANIFEST_AUTHORITY_KEYS = ("semantic_owner", "authority_revision")

SLUG_RE = compiler.SLUG_RE
OID_RE = compiler.OID_RE
ARTIFACT_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# The engine inputs a binding names. Mirrored from product_resolution.py by
# value, not by import: that module spawns processes and this one must not.
COMPILER_REQUIRED_INPUTS = ("topology", "repository_spec", "workflow_spec", "authority_lock")
COMPILER_OPTIONAL_INPUTS = ("contract_catalog",)
COMPILER_INPUT_KEYS = (*COMPILER_REQUIRED_INPUTS, *COMPILER_OPTIONAL_INPUTS)

BINDING_SECTIONS: dict[str, tuple[str, ...]] = {
    "product": ("id", "kind"),
    "manifest": ("ref", "digest"),
    "topology": ("ref", "digest"),
    "source": ("repository", "revision", "tree_sha"),
    "payload": ("ref", "digest"),
    "factory": ("repository", "revision"),
    "compiler": ("engine", "revision", "version", "inputs"),
}


# Every coordinate an admissible result restates, in the order it is rendered.
COORDINATE_KEYS = (
    "product",
    "manifest",
    "topology",
    "source",
    "payload",
    "factory",
    "compiler",
)

# Every reason this adapter can refuse a binding. Closed, like the binding
# itself: a consumer that routes on these codes must be able to enumerate them,
# and a code emitted but not listed here is a contract change nobody declared.
FAILURE_CODES = frozenset(
    {
        "BINDING_MALFORMED",
        "MANIFEST_SCHEMA_IDENTITY",
        "MANIFEST_INCOMPLETE",
        "MANIFEST_UNRESOLVED",
        "MANIFEST_AUTHORITY_UNKNOWN",
        "MANIFEST_DIGEST_MISMATCH",
        "PRODUCT_KIND_NOT_EXPLICIT",
        "PRODUCT_ARCHETYPE_NOT_EXPLICIT",
        "PRODUCT_COORDINATE_MISMATCH",
        "TOPOLOGY_COORDINATE_MISMATCH",
        "COMPILER_COORDINATE_MISMATCH",
        "COMPILER_INPUT_NOT_IN_PAYLOAD",
        "PAYLOAD_MALFORMED",
        "PAYLOAD_DIGEST_MISMATCH",
        "PAYLOAD_SOURCE_MISMATCH",
    }
)


class AdapterInputError(RuntimeError):
    """An artifact could not be read at all. Distinct from an inadmissible one."""


# Artifacts and results


def artifact_digest(data: bytes) -> str:
    """The factory's artifact digest: `sha256:` over the bytes as written."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


# The one rendering the factory and its handoff packager write to
# disk. The compiler already owns it; a second definition here would be a second
# place for the on-disk bytes — and so the artifact digest — to drift from.
render_document = compiler.render_payload


@dataclass(frozen=True)
class Artifact:
    """A loaded JSON document and the digest of the bytes it was read from."""

    document: dict[str, object]
    digest: str

    @classmethod
    def from_bytes(cls, data: bytes, *, where: str = "artifact") -> Artifact:
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterInputError(f"{where} is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise AdapterInputError(f"{where} is not a JSON object")
        return cls(document, artifact_digest(data))

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> Artifact:
        """An in-memory document, digested as the factory would have written it."""
        return cls(dict(document), artifact_digest(render_document(document).encode("utf-8")))


def load_artifact(path: Path) -> Artifact:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AdapterInputError(f"cannot read {path}: {exc}") from exc
    return Artifact.from_bytes(data, where=str(path))


@dataclass(frozen=True)
class Failure:
    code: str
    detail: str


@dataclass
class BindingResult:
    """Evidence for the birth factory. Not authority.

    `coordinates` is populated only when the binding is admissible: a partially
    validated coordinate set reads like a validated one, and the factory must
    never be handed one.
    """

    admissible: bool
    coordinates: dict[str, object] = field(default_factory=dict)
    failures: list[Failure] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": RESULT_SCHEMA,
            "authority_class": "evidence",
            "admissible": self.admissible,
            "coordinates": self.coordinates,
            "failures": [{"code": f.code, "detail": f.detail} for f in self.failures],
        }

    def render(self) -> str:
        lines = ["", "L9 PRODUCT BIRTH BINDING"]
        if self.admissible:
            for key in COORDINATE_KEYS:
                lines.append(f"  {key:<16} {json.dumps(self.coordinates.get(key), sort_keys=True)}")
        for failure in self.failures:
            lines.append(f"  {failure.code:<36} {failure.detail}")
        lines.append(f"BINDING: {'ADMISSIBLE' if self.admissible else 'INADMISSIBLE'}")
        lines.append("")
        return "\n".join(lines)


# The binding document contract, enforced without a schema library


def _closed_object(errors: list[str], doc: Mapping, key: str, allowed: tuple[str, ...]):
    value = doc.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} is not an object")
        return None
    missing = sorted(set(allowed) - set(value))
    if missing:
        errors.append(f"{key} is missing {', '.join(missing)}")
    extra = sorted(set(value) - set(allowed))
    if extra:
        errors.append(f"{key} carries unknown key(s): {', '.join(extra)}")
    return value


def _check_pattern(errors: list[str], doc: Mapping, key: str, pattern: re.Pattern[str], where: str):
    value = doc.get(key)
    if not isinstance(value, str) or not pattern.match(value):
        errors.append(f"{where}.{key} is not a valid {pattern.pattern}")


def _check_nonempty(errors: list[str], doc: Mapping, key: str, where: str) -> None:
    """A semantic token: non-empty, no surrounding whitespace, one line.

    The same rule the published schema states as `^\\S(.*\\S)?$`. A token the
    gate trims but the schema rejects would be a binding two readers disagree
    on, and an exact coordinate is compared, never normalized.
    """
    value = doc.get(key)
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        errors.append(f"{where}.{key} is not a non-empty single-line token without padding")


def usable_relative_path(value: object) -> bool:
    """A repository-relative file path, as the published schema's `relativePath`."""
    if not isinstance(value, str) or not value or value.startswith("/"):
        return False
    if "\\" in value or "\0" in value or "\n" in value or "\r" in value:
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def _check_compiler_inputs(errors: list[str], compiler_block: Mapping) -> None:
    inputs = compiler_block.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("compiler.inputs is not an object")
        return
    missing = sorted(set(COMPILER_REQUIRED_INPUTS) - set(inputs))
    if missing:
        errors.append(f"compiler.inputs is missing {', '.join(missing)}")
    extra = sorted(set(inputs) - set(COMPILER_INPUT_KEYS))
    if extra:
        errors.append(f"compiler.inputs carries unknown key(s): {', '.join(extra)}")
    for key in COMPILER_INPUT_KEYS:
        if key in inputs and not usable_relative_path(inputs[key]):
            errors.append(f"compiler.inputs.{key} is not a repository-relative path")


def validate_binding_document(document: object) -> list[str]:
    """Every way a binding fails its own contract, or an empty list.

    The binding is a closed shape on purpose. A key this contract does not name
    — a `repository_shape`, a `kind_hint`, a `birth_contract`, a `lineage` — is
    not a tolerated extra; it is the one input this adapter exists to refuse.
    """
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["binding is not a JSON object"]
    if document.get("schema") != SCHEMA:
        return [
            f"unrecognized binding schema {document.get('schema')!r}: this adapter reads {SCHEMA}"
        ]
    extra = sorted(set(document) - {"schema", *BINDING_SECTIONS})
    if extra:
        errors.append(f"binding carries unknown key(s): {', '.join(extra)}")

    product = _closed_object(errors, document, "product", BINDING_SECTIONS["product"])
    if product is not None:
        _check_nonempty(errors, product, "id", "product")
        _check_nonempty(errors, product, "kind", "product")

    for section in ("manifest", "topology"):
        coord = _closed_object(errors, document, section, BINDING_SECTIONS[section])
        if coord is not None:
            # Semantic refs and digests: syntax owned upstream, opaque here.
            _check_nonempty(errors, coord, "ref", section)
            _check_nonempty(errors, coord, "digest", section)

    source = _closed_object(errors, document, "source", BINDING_SECTIONS["source"])
    if source is not None:
        _check_pattern(errors, source, "repository", SLUG_RE, "source")
        _check_pattern(errors, source, "revision", OID_RE, "source")
        _check_pattern(errors, source, "tree_sha", OID_RE, "source")

    payload = _closed_object(errors, document, "payload", BINDING_SECTIONS["payload"])
    if payload is not None:
        _check_nonempty(errors, payload, "ref", "payload")
        _check_pattern(errors, payload, "digest", ARTIFACT_DIGEST_RE, "payload")

    factory = _closed_object(errors, document, "factory", BINDING_SECTIONS["factory"])
    if factory is not None:
        _check_pattern(errors, factory, "repository", SLUG_RE, "factory")
        _check_pattern(errors, factory, "revision", OID_RE, "factory")

    engine = _closed_object(errors, document, "compiler", BINDING_SECTIONS["compiler"])
    if engine is not None:
        _check_pattern(errors, engine, "engine", SLUG_RE, "compiler")
        _check_pattern(errors, engine, "revision", OID_RE, "compiler")
        _check_nonempty(errors, engine, "version", "compiler")
        _check_compiler_inputs(errors, engine)
    return errors


def load_binding(path: Path) -> dict[str, object]:
    return load_artifact(path).document


# The checks


def _explicit_token(value: object) -> bool:
    """An explicitly declared semantic token: a non-empty string, not an Unknown.

    The topology vocabulary allows a kind or archetype to be an explicit Unknown
    while the product is still being authored; a resolved manifest may not carry
    one, and this adapter will never fill one in.
    """
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() != "unknown"


def _incomplete(failures: list[Failure], detail: str) -> None:
    failures.append(Failure("MANIFEST_INCOMPLETE", detail))


def _check_manifest_structure(manifest: Mapping[str, object], failures: list[Failure]) -> None:
    """Structural completeness against the upstream schema's `required` lists."""
    missing = sorted(set(MANIFEST_REQUIRED_KEYS) - set(manifest))
    if missing:
        _incomplete(failures, f"manifest is missing required key(s): {', '.join(missing)}")
    for key, required in (
        ("product", MANIFEST_PRODUCT_KEYS),
        ("source_topology", MANIFEST_TOPOLOGY_KEYS),
        ("compiler", MANIFEST_COMPILER_KEYS),
        ("authority", MANIFEST_AUTHORITY_KEYS),
    ):
        if key not in manifest:
            continue
        block = manifest[key]
        if not isinstance(block, dict):
            _incomplete(failures, f"manifest.{key} is not an object")
            continue
        absent = sorted(set(required) - set(block))
        if absent:
            _incomplete(failures, f"manifest.{key} is missing required key(s): {', '.join(absent)}")
    digest = manifest.get("manifest_digest")
    if "manifest_digest" in manifest and (not isinstance(digest, str) or not digest.strip()):
        _incomplete(failures, "manifest.manifest_digest is not a non-empty string")


def _check_manifest_resolved(manifest: Mapping[str, object], failures: list[Failure]) -> None:
    """Fail closed on any unresolved entry: upstream defines no severity to read."""
    if "unresolved" not in manifest:
        return
    unresolved = manifest["unresolved"]
    if not isinstance(unresolved, list):
        _incomplete(failures, "manifest.unresolved is not an array")
    elif unresolved:
        failures.append(
            Failure(
                "MANIFEST_UNRESOLVED",
                f"manifest carries {len(unresolved)} unresolved entr"
                f"{'y' if len(unresolved) == 1 else 'ies'} — every unresolved entry is hard "
                "at this boundary, and birth does not lower an unresolved manifest",
            )
        )


def _check_manifest_authority(manifest: Mapping[str, object], failures: list[Failure]) -> None:
    """The authority the manifest was resolved under is explicit or the birth is refused."""
    authority = manifest.get("authority")
    if not isinstance(authority, dict):
        return
    for key in MANIFEST_AUTHORITY_KEYS:
        if key in authority and not _explicit_token(authority.get(key)):
            failures.append(
                Failure(
                    "MANIFEST_AUTHORITY_UNKNOWN",
                    f"manifest.authority.{key} is not an explicit token — a manifest resolved "
                    "under an unknown authority is not a resolved manifest at this boundary",
                )
            )


def _check_manifest_product(manifest: Mapping[str, object], failures: list[Failure]) -> None:
    """ProductKind and archetype are explicit upstream or the realization is refused."""
    product = manifest.get("product")
    if not isinstance(product, dict):
        return
    if not _explicit_token(product.get("kind")):
        failures.append(
            Failure(
                "PRODUCT_KIND_NOT_EXPLICIT",
                "manifest.product.kind is not an explicit ProductKind — the kind is "
                "resolved upstream and is never inferred or supplied at this boundary",
            )
        )
    if not _explicit_token(product.get("archetype_ref")):
        failures.append(
            Failure(
                "PRODUCT_ARCHETYPE_NOT_EXPLICIT",
                "manifest.product.archetype_ref is not an explicit archetype reference",
            )
        )


def _check_manifest(manifest: Mapping[str, object], failures: list[Failure]) -> bool:
    """Schema identity, structural completeness, resolved state, authority, explicit kind.

    Returns False when the manifest is not even the contract this adapter reads;
    every other check describes v1 and would be noise against a different one.
    """
    schema = manifest.get("schema")
    if schema != MANIFEST_SCHEMA:
        failures.append(
            Failure(
                "MANIFEST_SCHEMA_IDENTITY",
                f"manifest schema {schema!r} is not admitted: this adapter reads {MANIFEST_SCHEMA}",
            )
        )
        return False
    _check_manifest_structure(manifest, failures)
    _check_manifest_resolved(manifest, failures)
    _check_manifest_authority(manifest, failures)
    _check_manifest_product(manifest, failures)
    return True


def _check_product_coordinates(
    binding: Mapping, manifest: Mapping[str, object], failures: list[Failure]
) -> None:
    """The binding may restate product coordinates; it may never supply them."""
    claimed = binding["product"]
    product = manifest.get("product")
    if not isinstance(product, dict):
        return
    for key in ("id", "kind"):
        actual = product.get(key)
        if _explicit_token(actual) and str(actual).strip() != str(claimed[key]).strip():
            failures.append(
                Failure(
                    "PRODUCT_COORDINATE_MISMATCH",
                    f"binding names product {key} {claimed[key]!r}, the manifest resolves {actual!r}",
                )
            )


def _check_manifest_coordinates(
    binding: Mapping, manifest: Mapping[str, object], failures: list[Failure]
) -> None:
    declared = manifest.get("manifest_digest")
    if isinstance(declared, str) and declared.strip() and declared != binding["manifest"]["digest"]:
        failures.append(
            Failure(
                "MANIFEST_DIGEST_MISMATCH",
                f"binding names manifest digest {binding['manifest']['digest']!r}, "
                f"the manifest declares {declared!r}",
            )
        )
    topology = manifest.get("source_topology")
    if isinstance(topology, dict):
        for key in MANIFEST_TOPOLOGY_KEYS:
            if key in topology and topology.get(key) != binding["topology"][key]:
                failures.append(
                    Failure(
                        "TOPOLOGY_COORDINATE_MISMATCH",
                        f"binding names topology {key} {binding['topology'][key]!r}, "
                        f"the manifest was compiled from {topology.get(key)!r}",
                    )
                )


def _check_compiler_coordinates(
    binding: Mapping, manifest: Mapping[str, object], failures: list[Failure]
) -> None:
    """The manifest records the compiler that resolved it; the binding must name that one.

    Only the version is comparable here: the manifest does not carry the
    engine's repository or revision, and PREPARE holds those to the factory's
    pin. A version disagreement is already a different compiler.
    """
    block = manifest.get("compiler")
    if not isinstance(block, dict) or "compiler_version" not in block:
        return
    recorded = block.get("compiler_version")
    claimed = binding["compiler"]["version"]
    if recorded != claimed:
        failures.append(
            Failure(
                "COMPILER_COORDINATE_MISMATCH",
                f"binding names compiler version {claimed!r}, the manifest was resolved by "
                f"{recorded!r}",
            )
        )


def _check_payload(binding: Mapping, payload: Artifact, failures: list[Failure]) -> None:
    """The compiled payload, held to the factory's own gate and to the binding."""
    errors = compiler.validate_payload_document(payload.document)
    if errors:
        failures.append(Failure("PAYLOAD_MALFORMED", "; ".join(errors)[:300]))
        return
    if payload.digest != binding["payload"]["digest"]:
        failures.append(
            Failure(
                "PAYLOAD_DIGEST_MISMATCH",
                f"binding names payload {binding['payload']['digest']}, "
                f"the artifact hashes to {payload.digest}",
            )
        )
    source = payload.document["source"]
    assert isinstance(source, dict)
    for key in BINDING_SECTIONS["source"]:
        if source.get(key) != binding["source"][key]:
            failures.append(
                Failure(
                    "PAYLOAD_SOURCE_MISMATCH",
                    f"binding names source {key} {binding['source'][key]!r}, "
                    f"the compiled payload was taken from {source.get(key)!r}",
                )
            )
    _check_compiler_inputs_in_payload(binding, payload.document, failures)


def _check_compiler_inputs_in_payload(
    binding: Mapping, payload: Mapping[str, object], failures: list[Failure]
) -> None:
    """Every compiler input the binding names is a byte the payload authorizes.

    The manifest is reproduced in PREPARE from the files the binding names; a
    file the compiled payload does not list is not part of the snapshot the
    birth consumes, so a manifest compiled from it describes something else.
    """
    files = payload.get("files")
    listed = (
        {entry.get("path") for entry in files if isinstance(entry, dict)}
        if isinstance(files, list)
        else set()
    )
    inputs = binding["compiler"]["inputs"]
    for key in COMPILER_INPUT_KEYS:
        rel = inputs.get(key)
        if rel is not None and rel not in listed:
            failures.append(
                Failure(
                    "COMPILER_INPUT_NOT_IN_PAYLOAD",
                    f"binding names compiler input {key} {rel!r}, which the compiled payload "
                    "does not authorize",
                )
            )


def _validated_coordinates(binding: Mapping, manifest: Mapping[str, object]) -> dict[str, object]:
    """Exactly what was held consistent, restated — never a superset."""
    product = manifest["product"]
    assert isinstance(product, dict)
    engine = binding["compiler"]
    return {
        "product": {
            "id": product["id"],
            "kind": product["kind"],
            "archetype_ref": product["archetype_ref"],
        },
        "manifest": {
            "schema": MANIFEST_SCHEMA,
            "ref": binding["manifest"]["ref"],
            "digest": binding["manifest"]["digest"],
        },
        "topology": dict(binding["topology"]),
        "source": dict(binding["source"]),
        "payload": {
            "schema": PAYLOAD_SCHEMA,
            "ref": binding["payload"]["ref"],
            "digest": binding["payload"]["digest"],
        },
        "factory": dict(binding["factory"]),
        "compiler": {
            "engine": engine["engine"],
            "revision": engine["revision"],
            "version": engine["version"],
            "inputs": dict(engine["inputs"]),
        },
    }


def bind(binding: object, *, manifest: Artifact, payload: Artifact) -> BindingResult:
    """Decide admissibility. Pure: no filesystem, no git, no network, no compiler.

    Every failure is reported, not only the first, for the same reason the
    payload validator reports all of its: a binding is produced by a machine,
    and a gate that has to be re-run six times to learn six facts is a gate that
    gets switched off.
    """
    failures: list[Failure] = []
    errors = validate_binding_document(binding)
    if errors:
        failures.append(Failure("BINDING_MALFORMED", "; ".join(errors)))
        return BindingResult(admissible=False, failures=failures)
    assert isinstance(binding, dict)

    if _check_manifest(manifest.document, failures):
        _check_product_coordinates(binding, manifest.document, failures)
        _check_manifest_coordinates(binding, manifest.document, failures)
        _check_compiler_coordinates(binding, manifest.document, failures)
    _check_payload(binding, payload, failures)

    if failures:
        return BindingResult(admissible=False, failures=failures)
    return BindingResult(
        admissible=True, coordinates=_validated_coordinates(binding, manifest.document)
    )


# Entry point


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="l9_birth_adapter.py",
        description="Bind a compiler-resolved product realization to repository-birth coordinates.",
    )
    parser.add_argument("--binding", required=True, help=f"{SCHEMA} document")
    parser.add_argument("--manifest", required=True, help=f"{MANIFEST_SCHEMA} artifact (JSON)")
    parser.add_argument("--payload", required=True, help=f"compiled {PAYLOAD_SCHEMA} artifact")
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        binding = load_binding(Path(args.binding).expanduser())
        manifest = load_artifact(Path(args.manifest).expanduser())
        payload = load_artifact(Path(args.payload).expanduser())
    except AdapterInputError as exc:
        print(f"BINDING INPUT FAIL: {exc}", file=sys.stderr)
        return 2

    result = bind(binding, manifest=manifest, payload=payload)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True) if args.json else result.render())
    return 0 if result.admissible else 1


if __name__ == "__main__":
    raise SystemExit(main())
