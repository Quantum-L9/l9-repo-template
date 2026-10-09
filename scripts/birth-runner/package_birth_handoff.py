#!/usr/bin/env python3
"""Package a verified source snapshot for a compiler-backed repository birth.

The factory owns every executable and schema that defines, produces, validates,
prepares, assembles, seals, publishes or attests a repository birth. This is the
packaging step: it turns a clean realized source checkout into exactly the
bundle the PREPARE gate (`_preflight_product_birth_adapter`) admits.

    birth-payload.json           l9.birth-payload/v1       the existing payload compiler's output
    product-manifest.json        l9.product-manifest/v1    the pinned semantic compiler's output
    product-birth-binding.json   l9.product-birth-binding/v2

It does not own product semantics. The ProductManifest is produced by the
pinned `l9-semantic-compiler-engine` (`product_resolution.py`) from the exact
topology, repository-spec, workflow-spec and authority-lock files inside the
snapshot, and the factory carries that output verbatim: nothing here derives a
manifest ref, a ProductKind or an archetype from a product id, a repository
name, a topology, a filename or a directory. The payload compiler compiles
bytes, the semantic compiler compiles semantics, the adapter decides, and this
module only carries proven coordinates between them.

The running repository is the factory. Its coordinate is its own clean, committed
HEAD, and only a checkout whose `origin` names Quantum-L9/l9-repo-template is the
factory; there is no `--factory` argument to point the packager somewhere else.
The engine is the factory's pin (`semantic-compiler.pin.json`): the checkout
handed in through `--semantic-compiler-src` is proven to be exactly that
revision before it runs.

    package_birth_handoff.py --source DIR --semantic-compiler-src DIR
                             --manifest-ref REF --out-dir DIR
                             [--topology P] [--repository-spec P] [--workflow-spec P]
                             [--authority-lock P] [--contract-catalog P (only when the
                             product declares a local catalog)]
                             [--source-repository OWNER/NAME]

Exit 0 and a PASS document when the existing adapter admits the bundle, 1
otherwise. A refused bundle leaves the output directory exactly as it was, and
the output directory may lie inside neither the source nor the factory checkout.
Dependency-free at runtime, like the rest of the birth engine.

v2 (BIRTH-ARCH-REVISION-001): the `l9.repo-birth-evidence/v1` lineage input and
the emitted `l9.repo-birth-contract/v1` are gone. IdeaOS, GAR, Plan, campaign
and Program Execution history are not inputs to a birth; the product's own
semantic resolution, reproduced by the pinned engine, is.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
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


# Reused, not restated: the payload compiler owns snapshot cleanliness,
# revision/tree resolution, source identity, payload mode, digests and
# rendering; product resolution owns the pinned engine; the adapter owns every
# realization-consistency check.
compiler = _load_sibling("compile_birth_payload")
birth_adapter = _load_sibling("l9_birth_adapter")
product_resolution = _load_sibling("product_resolution")
prov = compiler.prov

TEMPLATE_ROOT = Path(__file__).resolve().parents[2]
FACTORY_REPOSITORY = "Quantum-L9/l9-repo-template"
PAYLOAD_NAME = "birth-payload.json"
MANIFEST_NAME = "product-manifest.json"
BINDING_NAME = "product-birth-binding.json"
BUNDLE_NAMES = (PAYLOAD_NAME, MANIFEST_NAME, BINDING_NAME)

# The engine's own CLI defaults for the inputs every product has, as
# repository-relative paths inside the source. The optional contract catalog
# has no default here: it is named in the binding only when the caller
# supplies it, because a product whose RepositorySpec declares no local
# catalog ships no such file, and a binding naming one the payload does not
# carry is refused by the adapter. PREPARE resolves the engine's own default
# against the source root when the binding omits it.
DEFAULT_INPUTS: dict[str, str] = {
    "topology": "product-topology.yaml",
    "repository_spec": "repository-spec.yaml",
    "workflow_spec": "workflow-spec.yaml",
    "authority_lock": "semantics.lock.yaml",
}


class HandoffError(RuntimeError):
    """The bundle could not be packaged, or the adapter did not admit it."""


# ─────────────────────────────────────────────────────────────────────────────
# Inputs: the running factory, the clean snapshot, the pinned engine
# ─────────────────────────────────────────────────────────────────────────────


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


def normalize_inputs(overrides: Mapping[str, str | None] | None) -> dict[str, str]:
    """The engine inputs as the binding will name them: explicit, relative, closed.

    Required inputs default to the engine's conventions; the optional contract
    catalog is present only when supplied, never defaulted in.
    """
    inputs = dict(DEFAULT_INPUTS)
    for key, value in (overrides or {}).items():
        if key not in product_resolution.INPUT_KEYS:
            raise HandoffError(f"unknown compiler input {key!r}")
        if value is not None:
            inputs[key] = value
    for key, value in inputs.items():
        if not product_resolution.usable_input_path(value):
            raise HandoffError(f"compiler input {key} is not a repository-relative path: {value!r}")
    return inputs


def resolve_manifest(
    *, engine_root: Path, source: Path, inputs: Mapping[str, str], factory_root: Path
) -> dict[str, object]:
    """The pinned engine's resolved manifest for the snapshot, or a refusal."""
    try:
        pin = product_resolution.load_pin(factory_root)
        engine = product_resolution.prove_engine_checkout(engine_root, pin)
        reproduction = product_resolution.reproduce_manifest(
            engine_root=engine, pin=pin, source_root=source, inputs=inputs
        )
    except product_resolution.ProductResolutionError as exc:
        raise HandoffError(f"semantic compiler did not resolve the product: {exc}") from exc
    if not reproduction.resolved:
        shown = "; ".join(str(entry)[:80] for entry in reproduction.unresolved[:6])
        raise HandoffError(
            f"the pinned semantic compiler left the product unresolved (exit "
            f"{reproduction.exit_code}): {shown or 'no detail'} — birth does not package an "
            "unresolved manifest"
        )
    return reproduction.manifest


# ─────────────────────────────────────────────────────────────────────────────
# Self-proof
# ─────────────────────────────────────────────────────────────────────────────


def prove_bundle(*, binding: Path, manifest: Path, payload: Path):
    """The existing adapter's verdict on the bundle as written to disk."""
    try:
        result = birth_adapter.bind(
            birth_adapter.load_binding(binding),
            manifest=birth_adapter.load_artifact(manifest),
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


def _refuse_output_inside(out_dir: Path, source: Path, factory_root: Path) -> None:
    """The handoff lives outside both authoritative trees, checked before any write."""
    reasons = {
        "source": "writing the bundle there would dirty the snapshot the payload attests as clean",
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
    semantic_compiler_src: Path,
    manifest_ref: str,
    out_dir: Path,
    inputs: Mapping[str, str | None] | None = None,
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
    factory_root = factory_root.resolve()
    _refuse_output_inside(out_dir, source, factory_root)
    engine_inputs = normalize_inputs(inputs)

    factory = factory_revision(factory_root)
    try:
        payload_doc = compiler.compile_payload(
            source, template_src=factory_root, source_repository_override=source_repository
        )
    except (compiler.PayloadCompileError, prov.ProvenanceError) as exc:
        raise HandoffError(f"factory payload compiler failed: {exc}") from exc
    payload_source = payload_doc["source"]
    assert isinstance(payload_source, dict)

    manifest = resolve_manifest(
        engine_root=semantic_compiler_src.resolve(),
        source=source,
        inputs=engine_inputs,
        factory_root=factory_root,
    )
    coordinates = manifest_coordinates(manifest)
    pin = product_resolution.load_pin(factory_root)

    payload_path = out_dir / PAYLOAD_NAME
    manifest_path = out_dir / MANIFEST_NAME
    binding_path = out_dir / BINDING_NAME
    payload_bytes = compiler.render_payload(payload_doc).encode("utf-8")
    manifest_bytes = compiler.render_payload(manifest).encode("utf-8")

    binding = {
        "schema": birth_adapter.SCHEMA,
        "product": coordinates["product"],
        "manifest": {"ref": manifest_ref, "digest": coordinates["manifest"]["digest"]},
        "topology": coordinates["topology"],
        "source": {
            "repository": payload_source["repository"],
            "revision": payload_source["revision"],
            "tree_sha": payload_source["tree_sha"],
        },
        "payload": {
            "ref": str(payload_path),
            "digest": birth_adapter.artifact_digest(payload_bytes),
        },
        "factory": {"repository": FACTORY_REPOSITORY, "revision": factory},
        "compiler": {**pin.coordinate, "inputs": engine_inputs},
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
        staged = {name: stage / name for name in BUNDLE_NAMES}
        staged[PAYLOAD_NAME].write_bytes(payload_bytes)
        staged[MANIFEST_NAME].write_bytes(manifest_bytes)
        staged[BINDING_NAME].write_text(compiler.render_payload(binding), encoding="utf-8")
        result = prove_bundle(
            binding=staged[BINDING_NAME],
            manifest=staged[MANIFEST_NAME],
            payload=staged[PAYLOAD_NAME],
        )
        _expose(staged, out_dir, stage)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {
        "status": "PASS",
        "payload": str(payload_path),
        "manifest": str(manifest_path),
        "binding": str(binding_path),
        "factory": {"repository": FACTORY_REPOSITORY, "revision": factory},
        "compiler": pin.coordinate,
        "adapter": {"schema": birth_adapter.RESULT_SCHEMA, "admissible": result.admissible},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="package_birth_handoff.py",
        description="Package a verified source snapshot for a compiler-backed repository birth.",
    )
    parser.add_argument("--source", required=True, help="clean realized source checkout")
    parser.add_argument(
        "--semantic-compiler-src",
        required=True,
        help="clean checkout of the pinned l9-semantic-compiler-engine (semantic-compiler.pin.json)",
    )
    parser.add_argument(
        "--manifest-ref", required=True, help="the ProductManifest's semantic ref, as published"
    )
    parser.add_argument("--out-dir", required=True)
    for key in product_resolution.INPUT_KEYS:
        default = DEFAULT_INPUTS.get(key)
        parser.add_argument(
            f"--{key.replace('_', '-')}",
            default=None,
            help=(
                f"engine input, relative to the source (default: {default})"
                if default
                else "engine input, relative to the source; named in the binding only when given"
            ),
        )
    parser.add_argument("--source-repository", help="owner/name of the source, overriding origin")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = package(
            source=Path(args.source).expanduser(),
            semantic_compiler_src=Path(args.semantic_compiler_src).expanduser(),
            manifest_ref=args.manifest_ref,
            out_dir=Path(args.out_dir).expanduser(),
            inputs={key: getattr(args, key) for key in product_resolution.INPUT_KEYS},
            source_repository=args.source_repository,
        )
    except (HandoffError, OSError) as exc:
        print(f"REPO_BIRTH_HANDOFF: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
