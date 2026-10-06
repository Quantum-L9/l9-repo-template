#!/usr/bin/env python3
"""Package a verified source snapshot for an adapter-backed repository birth.

The factory owns every executable and schema that defines, produces, validates,
prepares, assembles, seals, publishes or attests a repository birth. This is the
packaging step: it turns a clean realized source checkout, its upstream lineage
evidence and an already-resolved ProductManifest into exactly the bundle the
PREPARE gate (`_preflight_product_birth_adapter`) admits.

    birth-payload.json           l9.birth-payload/v1       the existing compiler's output
    birth-contract.json          l9.repo-birth-contract/v1 schemas/birth-contract.schema.json
    product-birth-binding.json   l9.product-birth-binding/v1

It does not own product semantics. The ProductManifest is read, never written,
and its ref is an explicit input: nothing here derives a manifest ref, a
ProductKind or an archetype from a product id, a repository name, a topology, a
filename or a directory. The compiler compiles, the adapter decides, and this
module only carries proven coordinates between them.

The running repository is the factory. Its coordinate is its own clean, committed
HEAD, and only a checkout whose `origin` names Quantum-L9/l9-repo-template is the
factory; there is no `--factory` argument to point the packager somewhere else.

    package_birth_handoff.py --source DIR --evidence FILE --manifest FILE
                             --manifest-ref REF --out-dir DIR
                             [--operation local_validation|remote_birth]
                             [--source-repository OWNER/NAME]

Exit 0 and a PASS document when the existing adapter admits the bundle, 1
otherwise. A refused bundle leaves the output directory exactly as it was, and
the output directory may lie inside neither the source nor the factory checkout.
Dependency-free at runtime, like the rest of the birth engine. Moved from
Cursor-Governance `skills/l9-repo-birth` (BIRTH-OWNERSHIP-CONSOLIDATION-001A).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
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


# Reused, not restated: the compiler owns snapshot cleanliness, revision/tree
# resolution, source identity, payload mode, digests and rendering; the adapter
# owns every realization-consistency check.
compiler = _load_sibling("compile_birth_payload")
birth_adapter = _load_sibling("l9_birth_adapter")
prov = compiler.prov

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
FACTORY_REPOSITORY = "Quantum-L9/l9-repo-template"
CONTRACT_SCHEMA = birth_adapter.BIRTH_CONTRACT_SCHEMA
CONTRACT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "birth-contract.schema.json"
EVIDENCE_SCHEMA = "l9.repo-birth-evidence/v1"
OPERATIONS = ("local_validation", "remote_birth")
COMPILER_REL = "scripts/birth-runner/compile_birth_payload.py"
FRONT_DOOR_REL = "scripts/birth-runner/new_repo.py"
LINEAGE_KEYS = (
    "idea_execute_receipt",
    "gar_decision",
    "plan",
    "campaign_source",
    "pe_receipt",
)
PAYLOAD_NAME = "birth-payload.json"
CONTRACT_NAME = "birth-contract.json"
BINDING_NAME = "product-birth-binding.json"


class HandoffError(RuntimeError):
    """The bundle could not be packaged, or the adapter did not admit it."""


def sha256(path: Path) -> str:
    return birth_adapter.artifact_digest(path.read_bytes())


def load_json(path: Path, what: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"cannot load {what} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{what} {path} must be a JSON object")
    return value


# ─────────────────────────────────────────────────────────────────────────────
# The birth contract, validated against its own schema without a schema library
# ─────────────────────────────────────────────────────────────────────────────

# The keywords `birth-contract.schema.json` uses. A keyword outside this set is
# a schema change this validator cannot honor, so it refuses instead of
# silently ignoring it.
_SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "type",
        "additionalProperties",
        "required",
        "properties",
        "const",
        "enum",
        "pattern",
        "minLength",
        "minItems",
        "items",
    }
)
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
}


def _same_json_value(a: object, b: object) -> bool:
    """JSON equality: `true` is not `1`, as JSON Schema `const`/`enum` read it."""
    return type(a) is type(b) and a == b


# The patterns `birth-contract.schema.json` uses, compiled once. Like the
# keyword set, the pattern set is closed: a schema value never becomes a
# regular expression at runtime, and a pattern outside this set refuses.
_KNOWN_PATTERNS: dict[str, re.Pattern[str]] = {
    source: re.compile(source)
    for source in (
        r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$",
        r"^[0-9a-f]{40}$",
        r"^sha256:[0-9a-f]{64}$",
    )
}


def _known_pattern(pattern: str) -> re.Pattern[str]:
    compiled = _KNOWN_PATTERNS.get(pattern)
    if compiled is None:
        raise HandoffError(f"birth contract schema uses unsupported pattern {pattern!r}")
    return compiled


def _check_type(schema: Mapping[str, object], value: object, where: str) -> str | None:
    expected = schema.get("type")
    if expected is None:
        return None
    if not isinstance(expected, str) or expected not in _JSON_TYPES:
        raise HandoffError(f"birth contract schema uses unsupported type {expected!r}")
    return None if isinstance(value, _JSON_TYPES[expected]) else f"{where} is not a JSON {expected}"


def _check_values(schema: Mapping[str, object], value: object, where: str) -> list[str]:
    errors: list[str] = []
    if "const" in schema and not _same_json_value(value, schema["const"]):
        errors.append(f"{where} must equal {schema['const']!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_same_json_value(value, item) for item in enum):
        errors.append(f"{where} must be one of {enum}")
    return errors


def _check_string(schema: Mapping[str, object], value: str, where: str) -> list[str]:
    errors: list[str] = []
    pattern = schema.get("pattern")
    # search, as JSON Schema `pattern` is defined; the schema anchors its own.
    if isinstance(pattern, str) and not _known_pattern(pattern).search(value):
        errors.append(f"{where} does not match {pattern}")
    min_length = schema.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        errors.append(f"{where} is shorter than {min_length}")
    return errors


def _check_array(schema: Mapping[str, object], value: list, where: str) -> list[str]:
    errors: list[str] = []
    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        errors.append(f"{where} has fewer than {min_items} item(s)")
    items = schema.get("items")
    if isinstance(items, Mapping):
        for index, item in enumerate(value):
            errors.extend(validate_against(items, item, f"{where}[{index}]"))
    return errors


def _check_object(schema: Mapping[str, object], value: dict, where: str) -> list[str]:
    properties = schema.get("properties")
    props = properties if isinstance(properties, Mapping) else {}
    required = schema.get("required")
    errors = [
        f"{where}.{key} is required"
        for key in (required if isinstance(required, list) else [])
        if key not in value
    ]
    if schema.get("additionalProperties") is False:
        errors.extend(f"{where}.{key} is not allowed" for key in sorted(set(value) - set(props)))
    for key, subschema in props.items():
        if key in value and isinstance(subschema, Mapping):
            errors.extend(validate_against(subschema, value[key], f"{where}.{key}"))
    return errors


def validate_against(schema: Mapping[str, object], value: object, where: str) -> list[str]:
    """Every way `value` fails `schema`, for the closed keyword subset above."""
    unsupported = sorted(set(schema) - _SUPPORTED_KEYWORDS)
    if unsupported:
        raise HandoffError(
            f"birth contract schema uses unsupported keyword(s) at {where}: "
            f"{', '.join(unsupported)}"
        )
    wrong_type = _check_type(schema, value, where)
    if wrong_type:
        return [wrong_type]
    errors = _check_values(schema, value, where)
    if isinstance(value, str):
        errors.extend(_check_string(schema, value, where))
    elif isinstance(value, list):
        errors.extend(_check_array(schema, value, where))
    elif isinstance(value, dict):
        errors.extend(_check_object(schema, value, where))
    return errors


def load_contract_schema() -> dict[str, object]:
    return load_json(CONTRACT_SCHEMA_PATH, "birth contract schema")


def validate_contract_document(document: object) -> list[str]:
    """Every way a birth contract fails `schemas/birth-contract.schema.json`."""
    return validate_against(load_contract_schema(), document, "birth_contract")


# ─────────────────────────────────────────────────────────────────────────────
# Inputs: upstream lineage, the running factory, the ProductManifest
# ─────────────────────────────────────────────────────────────────────────────


def _require_digest(evidence: Mapping[str, object], key: str) -> str:
    value = str(evidence.get(key) or "")
    if not value.startswith("sha256:") or len(value) != 71:
        raise HandoffError(f"evidence.{key} must be a sha256: digest")
    return value


def _resolve_lineage_path(source: Path, ref: str) -> Path:
    """A lineage or acceptance artifact inside the verified source snapshot.

    Relative refs resolve against the source; an absolute ref is accepted only
    when it lies inside it. Symlinks are resolved first, so a link that leaves
    the snapshot is refused too. Lineage is bound to the snapshot it was
    verified with, and nothing outside it is probed.
    """
    raw = str(ref or "").strip()
    if not raw:
        raise HandoffError("lineage path is empty")
    base = os.path.realpath(source)
    candidate = os.path.realpath(os.path.join(base, raw))
    if os.path.commonpath([base, candidate]) != base:
        raise HandoffError(
            f"lineage artifact {ref!r} is outside the source checkout — lineage is bound "
            "to the snapshot it was verified with"
        )
    path = Path(candidate)
    if not path.is_file():
        raise HandoffError(f"lineage artifact missing: {ref}")
    return path


def _verify_lineage(evidence: Mapping[str, object], source: Path) -> None:
    """Each lineage digest hashes its `*_path` artifact; the PE receipt has a schema."""
    for key in LINEAGE_KEYS:
        digest = _require_digest(evidence, key)
        path_key = f"{key}_path"
        raw_path = str(evidence.get(path_key) or "").strip()
        if not raw_path:
            raise HandoffError(f"evidence.{path_key} must locate the {key} artifact")
        artifact = _resolve_lineage_path(source, raw_path)
        if sha256(artifact) != digest:
            raise HandoffError(f"evidence.{key} does not match hashed {path_key}")
        if key == "pe_receipt":
            receipt = load_json(artifact, "pe_receipt artifact")
            if not str(receipt.get("schema") or "").strip():
                raise HandoffError("pe_receipt artifact must declare schema")


def _verify_acceptance(evidence: Mapping[str, object], source: Path) -> None:
    refs = evidence.get("acceptance_evidence_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or not all(isinstance(ref, str) and ref.strip() for ref in refs)
    ):
        raise HandoffError("evidence.acceptance_evidence_refs must be a non-empty string list")
    for ref in refs:
        _resolve_lineage_path(source, ref)


def validate_evidence(evidence: Mapping[str, object], source: Path) -> tuple[str, str, str]:
    """`(source repository, revision, tree)` of a clean snapshot the evidence binds."""
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise HandoffError(f"evidence.schema must equal {EVIDENCE_SCHEMA}")
    _verify_lineage(evidence, source)
    _verify_acceptance(evidence, source)
    try:
        compiler.assert_immutable_snapshot(source)
        revision, tree_sha = compiler.source_revision(source)
    except (compiler.PayloadCompileError, prov.ProvenanceError) as exc:
        raise HandoffError(str(exc)) from exc
    if evidence.get("source_revision") != revision or evidence.get("source_tree_sha") != tree_sha:
        raise HandoffError(
            "PE evidence source revision/tree does not match the current clean source"
        )
    repository = str(evidence.get("source_repository") or "").strip()
    if "/" not in repository:
        raise HandoffError("evidence.source_repository must be owner/name")
    return repository, revision, tree_sha


def factory_revision(factory_root: Path) -> str:
    """The running factory's exact HEAD — only when it is a clean factory snapshot."""
    try:
        compiler.assert_immutable_snapshot(factory_root)
        revision, _tree = compiler.source_revision(factory_root)
        identity = compiler.source_repository(factory_root)
    except (compiler.PayloadCompileError, prov.ProvenanceError) as exc:
        raise HandoffError(f"the running factory is not a trustworthy coordinate: {exc}") from exc
    if identity != FACTORY_REPOSITORY:
        raise HandoffError(
            f"the running checkout is {identity}, not the birth factory {FACTORY_REPOSITORY} — "
            "only the factory packages a birth"
        )
    return revision


def _explicit_token(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and "\n" not in value


def manifest_coordinates(manifest: Mapping[str, object]) -> dict[str, dict[str, str]]:
    """The coordinates the binding restates, read from the manifest and nowhere else.

    A coordinate the manifest does not state is a refusal, never a default:
    the factory reads ProductKind, it does not supply one. Everything else about
    the manifest — schema identity, resolution, archetype — is the adapter's.
    """
    product = manifest.get("product")
    topology = manifest.get("source_topology")
    coordinates: dict[str, dict[str, str]] = {"product": {}, "topology": {}}
    for block, name, keys in (
        (product, "product", ("id", "kind")),
        (topology, "source_topology", ("ref", "digest")),
    ):
        for key in keys:
            value = block.get(key) if isinstance(block, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise HandoffError(
                    f"ProductManifest states no {name}.{key} — the factory reads it from the "
                    "resolved manifest and never infers it"
                )
            coordinates["product" if name == "product" else "topology"][key] = value
    digest = manifest.get("manifest_digest")
    if not isinstance(digest, str) or not digest.strip():
        raise HandoffError("ProductManifest states no manifest_digest")
    coordinates["manifest"] = {"digest": digest}
    return coordinates


# ─────────────────────────────────────────────────────────────────────────────
# Self-proof
# ─────────────────────────────────────────────────────────────────────────────


def prove_bundle(*, binding: Path, manifest: Path, birth_contract: Path, payload: Path):
    """The existing adapter's verdict on the bundle as written to disk."""
    try:
        result = birth_adapter.bind(
            birth_adapter.load_binding(binding),
            manifest=birth_adapter.load_artifact(manifest),
            birth_contract=birth_adapter.load_artifact(birth_contract),
            payload=birth_adapter.load_artifact(payload),
        )
    except birth_adapter.AdapterInputError as exc:
        raise HandoffError(f"bundle unreadable: {exc}") from exc
    if not result.admissible:
        reasons = "; ".join(f"{f.code}: {f.detail}" for f in result.failures)
        raise HandoffError(f"the product-birth adapter refused the bundle — {reasons}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Packaging
# ─────────────────────────────────────────────────────────────────────────────


def _write(path: Path, document: Mapping[str, object]) -> None:
    path.write_text(compiler.render_payload(dict(document)), encoding="utf-8")


def _refuse_output_inside(out_dir: Path, source: Path, factory_root: Path) -> None:
    """The handoff lives outside both authoritative trees, checked before any write."""
    reasons = {
        "source": "writing the bundle there would dirty the snapshot the birth contract "
        "attests as clean",
        "factory": "writing the bundle there would dirty the factory after its coordinate "
        "is captured, and could carry packaging artifacts into a newborn",
    }
    for label, tree in (("source", source), ("factory", factory_root)):
        if out_dir == tree or tree in out_dir.parents:
            raise HandoffError(
                f"--out-dir {out_dir} is inside the {label} checkout — {reasons[label]}"
            )


def _expose(staged: dict[str, Path], out_dir: Path, stage: Path) -> None:
    """Make a proven, staged bundle current: all three files, or none of them.

    An identical bundle already in place is left untouched, so a deterministic
    re-run is a no-op. Otherwise the current files are backed up (bytes and
    timestamps) before anything moves, and any failure part-way restores them,
    so out_dir never shows a mix of two bundles.
    """
    finals = {name: out_dir / name for name in staged}
    if all(
        final.is_file() and final.read_bytes() == staged[name].read_bytes()
        for name, final in finals.items()
    ):
        return
    backups: dict[str, Path] = {}
    for name, final in finals.items():
        if final.is_file():
            backups[name] = stage / f"previous-{name}"
            shutil.copy2(final, backups[name])
    exposed: list[str] = []
    try:
        for name, path in staged.items():
            path.replace(finals[name])
            exposed.append(name)
    except BaseException:
        for name in exposed:
            if name in backups:
                backups[name].replace(finals[name])
            else:
                finals[name].unlink(missing_ok=True)
        raise


def package(
    *,
    source: Path,
    evidence_path: Path,
    manifest_path: Path,
    manifest_ref: str,
    out_dir: Path,
    operation: str = "local_validation",
    source_repository: str | None = None,
    factory_root: Path = TEMPLATE_ROOT,
) -> dict[str, object]:
    """Package, prove, and return the PASS document. Nothing is left behind on refusal."""
    if not _explicit_token(manifest_ref):
        raise HandoffError(
            "the ProductManifest ref is required as an explicit single-line token — the "
            "factory never derives it from a product id, repository, topology or filename"
        )
    source, out_dir = source.resolve(), out_dir.resolve()
    factory_root, manifest_path = factory_root.resolve(), manifest_path.resolve()
    _refuse_output_inside(out_dir, source, factory_root)

    manifest = load_json(manifest_path, "ProductManifest")
    coordinates = manifest_coordinates(manifest)
    factory = factory_revision(factory_root)
    evidence = load_json(evidence_path, "birth evidence")
    repository, revision, tree_sha = validate_evidence(evidence, source)
    if source_repository:
        repository = source_repository

    try:
        payload_doc = compiler.compile_payload(
            source, template_src=factory_root, source_repository_override=repository
        )
    except (compiler.PayloadCompileError, prov.ProvenanceError) as exc:
        raise HandoffError(f"factory payload compiler failed: {exc}") from exc
    payload_source = payload_doc["source"]
    assert isinstance(payload_source, dict)
    if payload_source.get("revision") != revision or payload_source.get("tree_sha") != tree_sha:
        raise HandoffError("factory payload does not bind the verified PE source snapshot")

    payload_path = out_dir / PAYLOAD_NAME
    contract_path = out_dir / CONTRACT_NAME
    binding_path = out_dir / BINDING_NAME
    payload_bytes = compiler.render_payload(payload_doc).encode("utf-8")
    contract = {
        "schema": CONTRACT_SCHEMA,
        "operation": operation,
        "source": {
            "path": str(source),
            "repository": payload_source["repository"],
            "revision": revision,
            "tree_sha": tree_sha,
            "clean": True,
        },
        "lineage": {key: evidence[key] for key in (*LINEAGE_KEYS, "acceptance_evidence_refs")},
        "factory": {
            "path": str(factory_root),
            "revision": factory,
            "compiler": str(factory_root / COMPILER_REL),
            "birth_front_door": str(factory_root / FRONT_DOOR_REL),
        },
        "payload": {
            "ref": str(payload_path),
            "digest": birth_adapter.artifact_digest(payload_bytes),
            "schema": compiler.SCHEMA,
        },
    }
    errors = validate_contract_document(contract)
    if errors:
        raise HandoffError("birth contract schema failure: " + "; ".join(errors))
    contract_bytes = compiler.render_payload(contract).encode("utf-8")

    binding = {
        "schema": birth_adapter.SCHEMA,
        "product": coordinates["product"],
        "manifest": {"ref": manifest_ref, "digest": coordinates["manifest"]["digest"]},
        "topology": coordinates["topology"],
        "source": {
            "repository": payload_source["repository"],
            "revision": revision,
            "tree_sha": tree_sha,
        },
        "birth_contract": {
            "ref": str(contract_path),
            "digest": birth_adapter.artifact_digest(contract_bytes),
        },
        "payload": {
            "ref": str(payload_path),
            "digest": birth_adapter.artifact_digest(payload_bytes),
        },
        "factory": {"repository": FACTORY_REPOSITORY, "revision": factory},
    }
    binding_errors = birth_adapter.validate_binding_document(binding)
    if binding_errors:
        raise HandoffError("product-birth binding malformed: " + "; ".join(binding_errors))

    # Staged and proven beside the destination, then moved into place only on
    # PASS: a refusal leaves out_dir exactly as it was, including any bundle a
    # previous run left there. Proven from the bytes on disk, so the verdict is
    # about what is handed on; refs name the final paths, which the adapter
    # binds by digest, not by location.
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".package-birth-handoff-", dir=out_dir))
    try:
        staged = {name: stage / name for name in (PAYLOAD_NAME, CONTRACT_NAME, BINDING_NAME)}
        staged[PAYLOAD_NAME].write_bytes(payload_bytes)
        staged[CONTRACT_NAME].write_bytes(contract_bytes)
        _write(staged[BINDING_NAME], binding)
        result = prove_bundle(
            binding=staged[BINDING_NAME],
            manifest=manifest_path,
            birth_contract=staged[CONTRACT_NAME],
            payload=staged[PAYLOAD_NAME],
        )
        _expose(staged, out_dir, stage)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {
        "status": "PASS",
        "operation": operation,
        "payload": str(payload_path),
        "contract": str(contract_path),
        "binding": str(binding_path),
        "factory": {"repository": FACTORY_REPOSITORY, "revision": factory},
        "adapter": {"schema": birth_adapter.RESULT_SCHEMA, "admissible": result.admissible},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="package_birth_handoff.py",
        description="Package a verified source snapshot for an adapter-backed repository birth.",
    )
    parser.add_argument("--source", required=True, help="clean realized source checkout")
    parser.add_argument("--evidence", required=True, help=f"{EVIDENCE_SCHEMA} document")
    parser.add_argument("--manifest", required=True, help="resolved ProductManifest (JSON)")
    parser.add_argument(
        "--manifest-ref", required=True, help="the ProductManifest's semantic ref, as published"
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--operation", choices=OPERATIONS, default="local_validation")
    parser.add_argument("--source-repository", help="owner/name of the source, overriding evidence")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = package(
            source=Path(args.source).expanduser(),
            evidence_path=Path(args.evidence).expanduser(),
            manifest_path=Path(args.manifest).expanduser(),
            manifest_ref=args.manifest_ref,
            out_dir=Path(args.out_dir).expanduser(),
            operation=args.operation,
            source_repository=args.source_repository,
        )
    except (HandoffError, OSError) as exc:
        print(f"REPO_BIRTH_HANDOFF: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
