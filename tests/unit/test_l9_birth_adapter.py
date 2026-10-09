"""The product-to-birth adapter boundary (l9.product-birth-binding/v2).

One question is under test: given a compiler-resolved ProductManifest, a
realized source snapshot bound by a compiled payload, a factory coordinate and
the compiler coordinate the manifest was resolved by, does the adapter admit
exactly the consistent realization and refuse — with a named, deterministic
reason — every inconsistent one, without ever inferring a ProductKind, reading
a source tree, running a compiler, or granting authority?

v2 (BIRTH-ARCH-REVISION-001): no birth contract, no lineage. A binding that
still carries either is malformed, not tolerated.

Everything here is pure: no git, no network, no filesystem beyond the files the
command-line tests write themselves. The adapter is a binding/validation
boundary, and a boundary that needed a repository to decide would be reading
the one thing it must not read.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
ADAPTER_MODULE = BIRTH_RUNNER / "l9_birth_adapter.py"
SCHEMA_FILE = BIRTH_RUNNER / "schemas" / "l9-product-birth-binding.schema.json"
SUPERSEDED = BIRTH_RUNNER / "schemas" / "superseded"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIRTH_RUNNER / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load("l9_birth_adapter_under_test", "l9_birth_adapter.py")
compiler = adapter.compiler

REVISION = "a" * 40
TREE = "b" * 40
FACTORY_REVISION = "c" * 40
ENGINE_REVISION = "d" * 40
SOURCE = {"repository": "Quantum-L9/IdeaOS", "revision": REVISION, "tree_sha": TREE}
FACTORY = {"repository": "Quantum-L9/l9-repo-template", "revision": FACTORY_REVISION}
TOPOLOGY = {"ref": "l9.product-topology/ideaos@1", "digest": "sha256:" + "1" * 64}
MANIFEST_DIGEST = "sha256:" + "2" * 64
COMPILER_VERSION = "0.9.3"
INPUTS = {
    "topology": "product-topology.yaml",
    "repository_spec": "repository-spec.yaml",
    "workflow_spec": "workflow-spec.yaml",
    "authority_lock": "semantics.lock.yaml",
    "contract_catalog": "contracts/compiler-core.yaml",
}
COMPILER = {
    "engine": "Quantum-L9/l9-semantic-compiler-engine",
    "revision": ENGINE_REVISION,
    "version": COMPILER_VERSION,
    "inputs": dict(INPUTS),
}
PAYLOAD_FILES = {
    "pyproject.toml": b'[project]\nname = "ideaos"\n',
    "src/ideaos/__init__.py": b"",
    **{rel: f"# {rel}\n".encode() for rel in INPUTS.values()},
}


def make_manifest(**overrides: object) -> dict[str, object]:
    """A resolved l9.product-manifest/v1 in the shape the upstream schema requires.

    Every required block is present; the ones this adapter does not read are
    empty objects, because their content is upstream semantics the adapter must
    stay blind to. `unresolved` is empty: the manifest passed its gate. The
    `compiler` block records the engine that resolved it, as the pinned engine
    writes it.
    """
    manifest: dict[str, object] = {
        "schema": adapter.MANIFEST_SCHEMA,
        "product": {
            "id": "l9.product/ideaos",
            "kind": "node",
            "archetype_ref": "l9.node-archetype/worker@1",
        },
        "source_topology": dict(TOPOLOGY),
        "authority": {
            "semantic_owner": "Quantum-L9/IdeaOS",
            "authority_revision": "l9-ideaos-product-closure@1",
        },
        "identity": {},
        "requirements": {},
        "capabilities": {},
        "architecture": {},
        "ports": {},
        "adapters": {},
        "relationships": {},
        "technology": {},
        "bindings": {},
        "providers": {},
        "admission": {},
        "lifecycle": {},
        "conformance": {},
        "compiler": {
            "profile_ref": "l9.compilation/product-build@1",
            "profile_digest": "sha256:" + "3" * 64,
            "compiler_version": COMPILER_VERSION,
        },
        "provenance": {},
        "unresolved": [],
        "manifest_digest": MANIFEST_DIGEST,
    }
    manifest.update(overrides)
    return manifest


def make_payload(files: dict[str, bytes] | None = None) -> dict[str, object]:
    """A compiled l9.birth-payload/v1 for the same snapshot, built by hand.

    `test_the_payload_fixture_is_a_real_payload` holds it to the factory's own
    validator, so a drift in that contract fails here rather than hiding.
    """
    files = PAYLOAD_FILES if files is None else files
    return {
        "schema": compiler.SCHEMA,
        "source": dict(SOURCE),
        "mode": "additive",
        "repository_shape": {"matched": ["src"]},
        "packages": {"python": ["ideaos"]},
        "files": [
            {"path": rel, "sha256": hashlib.sha256(body).hexdigest()}
            for rel, body in sorted(files.items())
        ],
        "manifest_sha256": compiler.prov.manifest_digest(files),
    }


def make_binding(
    manifest: dict[str, object], payload: adapter.Artifact, **overrides: object
) -> dict[str, object]:
    product = manifest["product"]
    assert isinstance(product, dict)
    binding: dict[str, object] = {
        "schema": adapter.SCHEMA,
        "product": {"id": product["id"], "kind": product["kind"]},
        "manifest": {"ref": "l9.product-manifest/ideaos@1", "digest": manifest["manifest_digest"]},
        "topology": dict(TOPOLOGY),
        "source": dict(SOURCE),
        "payload": {"ref": "/tmp/birth-handoff/birth-payload.json", "digest": payload.digest},
        "factory": dict(FACTORY),
        "compiler": json.loads(json.dumps(COMPILER)),
    }
    binding.update(overrides)
    return binding


class Case:
    """One consistent realization, every artifact digest-bound to the others."""

    def __init__(self) -> None:
        self.manifest_doc = make_manifest()
        self.manifest = adapter.Artifact.from_document(self.manifest_doc)
        self.payload = adapter.Artifact.from_document(make_payload())
        self.binding = make_binding(self.manifest_doc, self.payload)

    def bind(self, **kwargs: object) -> adapter.BindingResult:
        args: dict[str, object] = {"manifest": self.manifest, "payload": self.payload}
        args.update(kwargs)
        return adapter.bind(self.binding, **args)  # type: ignore[arg-type]

    def with_manifest(self, **overrides: object) -> adapter.BindingResult:
        return self.bind(manifest=adapter.Artifact.from_document(make_manifest(**overrides)))

    def with_binding(self, **overrides: object) -> adapter.BindingResult:
        self.binding = make_binding(self.manifest_doc, self.payload, **overrides)
        return self.bind()


def codes(result: adapter.BindingResult) -> list[str]:
    return [failure.code for failure in result.failures]


@pytest.fixture
def case() -> Case:
    return Case()


# ─────────────────────────────────────────────────────────────────────────────
# Accept
# ─────────────────────────────────────────────────────────────────────────────


class TestAConsistentRealizationIsAdmissible:
    def test_the_payload_fixture_is_a_real_payload(self, case: Case) -> None:
        """Anchor: the fixture satisfies the factory's own payload gate."""
        assert compiler.validate_payload_document(case.payload.document) == []

    def test_matching_coordinates_bind(self, case: Case) -> None:
        result = case.bind()
        assert result.failures == []
        assert result.admissible is True

    def test_the_validated_coordinates_are_exactly_the_bound_ones(self, case: Case) -> None:
        coordinates = case.bind().coordinates
        assert coordinates["product"] == {
            "id": "l9.product/ideaos",
            "kind": "node",
            "archetype_ref": "l9.node-archetype/worker@1",
        }
        assert coordinates["manifest"] == {
            "schema": adapter.MANIFEST_SCHEMA,
            "ref": "l9.product-manifest/ideaos@1",
            "digest": MANIFEST_DIGEST,
        }
        assert coordinates["topology"] == TOPOLOGY
        assert coordinates["source"] == SOURCE
        assert coordinates["payload"]["digest"] == case.payload.digest
        assert coordinates["factory"] == FACTORY
        assert coordinates["compiler"] == COMPILER
        assert "birth_contract" not in coordinates

    def test_the_result_is_evidence_not_authority(self, case: Case) -> None:
        document = case.bind().to_dict()
        assert document["schema"] == adapter.RESULT_SCHEMA
        assert document["authority_class"] == "evidence"
        assert set(document) == {
            "schema",
            "authority_class",
            "admissible",
            "coordinates",
            "failures",
        }

    def test_binding_is_deterministic(self, case: Case) -> None:
        """Two independently built, identical realizations bind to one result."""
        first = case.bind().to_dict()
        second = Case().bind().to_dict()
        assert first == second

    def test_the_contract_catalog_input_is_optional(self, case: Case) -> None:
        """A product with no local contract catalog names none; the engine's default applies."""
        inputs = {k: v for k, v in INPUTS.items() if k != "contract_catalog"}
        result = case.with_binding(compiler={**COMPILER, "inputs": inputs})
        assert result.admissible is True
        assert result.coordinates["compiler"]["inputs"] == inputs


# ─────────────────────────────────────────────────────────────────────────────
# Reject — the manifest
# ─────────────────────────────────────────────────────────────────────────────


class TestTheManifestMustBeAdmittedAndResolved:
    def test_a_wrong_schema_identity_is_the_only_finding(self, case: Case) -> None:
        """Every other rule describes v1; reporting them against a different
        contract would describe something the document never claimed."""
        result = case.with_manifest(schema="l9.product-manifest/v2")
        assert result.admissible is False
        manifest_codes = [
            c
            for c in codes(result)
            if c.startswith("MANIFEST") or c.startswith("PRODUCT") or c.startswith("COMPILER")
        ]
        assert manifest_codes == ["MANIFEST_SCHEMA_IDENTITY"]

    @pytest.mark.parametrize("schema", [None, "", "l9.product-topology/v1", "l9.birth-payload/v1"])
    def test_other_documents_are_not_manifests(self, case: Case, schema: object) -> None:
        assert "MANIFEST_SCHEMA_IDENTITY" in codes(case.with_manifest(schema=schema))

    @pytest.mark.parametrize(
        "unresolved",
        [
            [{"ref": "l9.capability/search@1", "reason": "provider binding missing"}],
            ["l9.port/inbound-http@1"],
            [{"ref": "x", "material": False}],
            ["resolved_manifest_gate:capability_closure_resolved"],
        ],
    )
    def test_any_unresolved_entry_fails_closed(self, case: Case, unresolved: list) -> None:
        """Upstream defines no per-entry severity this boundary may read, so an
        entry that calls itself non-material is still an unresolved entry."""
        result = case.with_manifest(unresolved=unresolved)
        assert result.admissible is False
        assert "MANIFEST_UNRESOLVED" in codes(result)

    def test_unresolved_must_be_a_list(self, case: Case) -> None:
        assert "MANIFEST_INCOMPLETE" in codes(case.with_manifest(unresolved={"count": 0}))

    # `schema` is the schema-identity case above, not a completeness one.
    @pytest.mark.parametrize(
        "missing", [k for k in adapter.MANIFEST_REQUIRED_KEYS if k != "schema"]
    )
    def test_a_manifest_missing_a_required_block_is_not_resolved_enough(
        self, case: Case, missing: str
    ) -> None:
        manifest = make_manifest()
        del manifest[missing]
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert result.admissible is False
        assert "MANIFEST_INCOMPLETE" in codes(result)

    @pytest.mark.parametrize(
        "block",
        [
            {"product": {"id": "l9.product/ideaos", "kind": "node"}},
            {"source_topology": {"ref": TOPOLOGY["ref"]}},
            {"compiler": {"profile_ref": "l9.compilation/product-build@1"}},
            {"compiler": {"profile_ref": "x", "profile_digest": "y"}},
            {"compiler": "l9.compilation/product-build@1"},
            {"authority": {"semantic_owner": "Quantum-L9/IdeaOS"}},
            {"manifest_digest": ""},
            {"manifest_digest": None},
        ],
    )
    def test_required_coordinate_fields_are_named_when_absent(
        self, case: Case, block: dict
    ) -> None:
        assert "MANIFEST_INCOMPLETE" in codes(case.with_manifest(**block))

    def test_a_manifest_digest_the_binding_does_not_name_is_a_mismatch(self, case: Case) -> None:
        result = case.with_manifest(manifest_digest="sha256:" + "9" * 64)
        assert result.admissible is False
        assert "MANIFEST_DIGEST_MISMATCH" in codes(result)

    def test_the_manifest_digest_is_compared_never_recomputed(self, case: Case) -> None:
        """Semantic canonicalization is the compiler's. A manifest whose bytes
        change while its declared digest does not still binds here — the adapter
        has no standing to say the compiler's digest is wrong. PREPARE, which
        re-runs the compiler, is where that forgery is caught."""
        manifest = make_manifest(provenance={"authority_ref": "l9.authority/ideaos-owner"})
        assert case.bind(manifest=adapter.Artifact.from_document(manifest)).admissible is True


class TestAuthorityIsExplicitOrNothing:
    @pytest.mark.parametrize("key", adapter.MANIFEST_AUTHORITY_KEYS)
    @pytest.mark.parametrize("value", [None, "", "  ", "unknown", "Unknown", 7])
    def test_an_unknown_authority_is_inadmissible(
        self, case: Case, key: str, value: object
    ) -> None:
        manifest = make_manifest()
        authority = manifest["authority"]
        assert isinstance(authority, dict)
        authority[key] = value
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert result.admissible is False
        assert "MANIFEST_AUTHORITY_UNKNOWN" in codes(result)
        assert result.coordinates == {}


class TestProductKindIsExplicitUpstreamOrNothing:
    @pytest.mark.parametrize(
        "kind", [None, "", "   ", "unknown", "Unknown", "UNKNOWN", 7, {"unknown": "pending"}]
    )
    def test_a_manifest_without_an_explicit_kind_is_inadmissible(
        self, case: Case, kind: object
    ) -> None:
        manifest = make_manifest()
        product = manifest["product"]
        assert isinstance(product, dict)
        product["kind"] = kind
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert result.admissible is False
        assert "PRODUCT_KIND_NOT_EXPLICIT" in codes(result)
        assert result.coordinates == {}

    def test_a_missing_kind_key_is_inadmissible(self, case: Case) -> None:
        manifest = make_manifest()
        product = manifest["product"]
        assert isinstance(product, dict)
        del product["kind"]
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert "PRODUCT_KIND_NOT_EXPLICIT" in codes(result)

    def test_the_binding_cannot_supply_the_kind_the_manifest_lacks(self, case: Case) -> None:
        """The substitution this boundary exists to refuse: a caller that knows
        the kind hands it in, hoping the adapter fills the gap. It does not."""
        manifest = make_manifest()
        product = manifest["product"]
        assert isinstance(product, dict)
        product["kind"] = "unknown"
        assert case.binding["product"]["kind"] == "node"
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert result.admissible is False
        assert "PRODUCT_KIND_NOT_EXPLICIT" in codes(result)
        assert "PRODUCT_COORDINATE_MISMATCH" not in codes(result)

    @pytest.mark.parametrize(
        "extra",
        [
            {"repository_shape": {"matched": ["pyproject.toml", "src", "tests"]}},
            {"kind_hint": "node"},
            {"inferred_kind": "dependency"},
            {"product": {"id": "l9.product/ideaos", "kind": "node", "shape": "node"}},
            {"birth_contract": {"ref": "x", "digest": "sha256:" + "0" * 64}},
            {"lineage": {"pe_receipt": "sha256:" + "0" * 64}},
        ],
    )
    def test_repository_shape_and_lineage_are_not_inputs(self, case: Case, extra: dict) -> None:
        """A binding carrying shape evidence, a kind hint, a birth contract or
        lineage is malformed, not tolerated: the adapter never reads shape,
        never derives kind, and v2 has no contract to bind."""
        result = case.with_binding(**extra)
        assert result.admissible is False
        assert codes(result) == ["BINDING_MALFORMED"]

    def test_an_unknown_archetype_is_inadmissible(self, case: Case) -> None:
        manifest = make_manifest()
        product = manifest["product"]
        assert isinstance(product, dict)
        product["archetype_ref"] = "unknown"
        assert "PRODUCT_ARCHETYPE_NOT_EXPLICIT" in codes(
            case.bind(manifest=adapter.Artifact.from_document(manifest))
        )

    def test_the_adapter_never_reads_a_source_tree_runs_a_compiler_or_infers_shape(self) -> None:
        """Static: the module neither spawns processes nor calls the ownership-
        contract shape readers the compiler exposes, and it never loads the
        product-resolution module that runs the engine. Loading the payload
        compiler for its validator is reuse; calling its shape logic would be
        inference; running the engine would make the adapter the gate it only
        informs."""
        source = ADAPTER_MODULE.read_text(encoding="utf-8")
        for forbidden in (
            "subprocess",
            "matched_shape",
            "is_repository_payload",
            "payload_ownership",
            "ownership_contract",
            "ls-files",
            "source_files(",
            "assert_immutable_snapshot",
            '_load_sibling("product_resolution")',
            "reproduce_manifest",
        ):
            assert forbidden not in source, forbidden
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert "subprocess" not in imported
        assert "os" not in imported

    def test_binding_touches_no_filesystem(
        self, case: Case, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*args: object, **kwargs: object) -> object:
            raise AssertionError("bind() opened a file")

        monkeypatch.setattr(Path, "read_bytes", refuse)
        monkeypatch.setattr(Path, "read_text", refuse)
        monkeypatch.setattr(Path, "exists", refuse)
        monkeypatch.setattr(Path, "is_dir", refuse)
        assert case.bind().admissible is True


class TestProductCoordinatesMustAgree:
    def test_a_binding_naming_a_different_product_is_a_mismatch(self, case: Case) -> None:
        result = case.with_binding(product={"id": "l9.product/other", "kind": "node"})
        assert "PRODUCT_COORDINATE_MISMATCH" in codes(result)

    def test_a_binding_naming_a_different_kind_is_a_mismatch(self, case: Case) -> None:
        result = case.with_binding(product={"id": "l9.product/ideaos", "kind": "dependency"})
        assert result.admissible is False
        assert "PRODUCT_COORDINATE_MISMATCH" in codes(result)

    @pytest.mark.parametrize("key", ["ref", "digest"])
    def test_a_topology_coordinate_the_manifest_did_not_come_from(
        self, case: Case, key: str
    ) -> None:
        topology = dict(TOPOLOGY, **{key: "other"})
        result = case.with_binding(topology=topology)
        assert result.admissible is False
        assert "TOPOLOGY_COORDINATE_MISMATCH" in codes(result)


# ─────────────────────────────────────────────────────────────────────────────
# Reject — the compiler coordinate
# ─────────────────────────────────────────────────────────────────────────────


class TestTheCompilerCoordinateMustAgree:
    def test_a_binding_naming_another_compiler_version_is_a_mismatch(self, case: Case) -> None:
        result = case.with_binding(compiler={**COMPILER, "version": "0.9.2"})
        assert result.admissible is False
        assert "COMPILER_COORDINATE_MISMATCH" in codes(result)

    def test_a_manifest_resolved_by_another_compiler_is_a_mismatch(self, case: Case) -> None:
        compiler_block = {
            "profile_ref": "l9.compilation/product-build@1",
            "profile_digest": "sha256:" + "3" * 64,
            "compiler_version": "1.0.0",
        }
        result = case.with_manifest(compiler=compiler_block)
        assert result.admissible is False
        assert "COMPILER_COORDINATE_MISMATCH" in codes(result)

    @pytest.mark.parametrize("key", sorted(INPUTS))
    def test_a_compiler_input_the_payload_does_not_authorize_is_refused(
        self, case: Case, key: str
    ) -> None:
        """The manifest is reproduced from these files; a file outside the
        compiled payload is outside the snapshot the birth consumes."""
        inputs = {**INPUTS, key: f"elsewhere/{Path(INPUTS[key]).name}"}
        result = case.with_binding(compiler={**COMPILER, "inputs": inputs})
        assert result.admissible is False
        assert "COMPILER_INPUT_NOT_IN_PAYLOAD" in codes(result)

    @pytest.mark.parametrize(
        "inputs",
        [
            {k: v for k, v in INPUTS.items() if k != "topology"},
            {**INPUTS, "extra": "x.yaml"},
            {**INPUTS, "topology": "/etc/product-topology.yaml"},
            {**INPUTS, "topology": "../product-topology.yaml"},
            {**INPUTS, "topology": "./product-topology.yaml"},
            {**INPUTS, "topology": ""},
            {**INPUTS, "authority_lock": "a\\b.yaml"},
            "product-topology.yaml",
        ],
    )
    def test_malformed_inputs_are_a_malformed_binding(self, case: Case, inputs: object) -> None:
        result = case.with_binding(compiler={**COMPILER, "inputs": inputs})
        assert codes(result) == ["BINDING_MALFORMED"]

    @pytest.mark.parametrize(
        "mutation",
        [
            {"engine": "not-a-slug"},
            {"revision": "main"},
            {"revision": ENGINE_REVISION[:12]},
            {"version": ""},
            {"version": " 0.9.3"},
        ],
    )
    def test_a_malformed_engine_coordinate_is_a_malformed_binding(
        self, case: Case, mutation: dict
    ) -> None:
        result = case.with_binding(compiler={**COMPILER, **mutation})
        assert codes(result) == ["BINDING_MALFORMED"]

    def test_the_compiler_block_may_not_be_defaulted(self, case: Case) -> None:
        del case.binding["compiler"]
        result = case.bind()
        assert codes(result) == ["BINDING_MALFORMED"]
        assert "compiler" in result.failures[0].detail


class TestTheFactoryCoordinateIsExplicit:
    def test_a_binding_without_a_factory_is_malformed(self, case: Case) -> None:
        del case.binding["factory"]
        result = case.bind()
        assert result.admissible is False
        assert codes(result) == ["BINDING_MALFORMED"]
        assert "factory" in result.failures[0].detail

    def test_the_binding_may_not_default_the_factory(self, case: Case) -> None:
        result = case.with_binding(factory={"repository": "Quantum-L9/l9-repo-template"})
        assert codes(result) == ["BINDING_MALFORMED"]


# ─────────────────────────────────────────────────────────────────────────────
# Reject — the realized source
# ─────────────────────────────────────────────────────────────────────────────


class TestTheSourceDigestMustReproduce:
    def test_a_payload_whose_bytes_moved_is_a_digest_mismatch(self, case: Case) -> None:
        moved = dict(case.payload.document, mode="authoritative")
        result = case.bind(payload=adapter.Artifact.from_document(moved))
        assert result.admissible is False
        assert "PAYLOAD_DIGEST_MISMATCH" in codes(result)

    def test_a_payload_from_a_different_snapshot(self, case: Case) -> None:
        other = dict(case.payload.document, source=dict(SOURCE, tree_sha="e" * 40))
        artifact = adapter.Artifact.from_document(other)
        case.binding = make_binding(case.manifest_doc, artifact)
        result = case.bind(payload=artifact)
        assert result.admissible is False
        assert "PAYLOAD_SOURCE_MISMATCH" in codes(result)

    def test_a_malformed_payload_is_held_to_the_factory_gate(self, case: Case) -> None:
        broken = adapter.Artifact.from_document({"schema": compiler.SCHEMA})
        case.binding = make_binding(case.manifest_doc, broken)
        result = case.bind(payload=broken)
        assert result.admissible is False
        assert "PAYLOAD_MALFORMED" in codes(result)

    @pytest.mark.parametrize("key", ["repository", "revision", "tree_sha"])
    def test_a_binding_source_the_payload_does_not_bind(self, case: Case, key: str) -> None:
        other = {"repository": "Quantum-L9/Other", "revision": "d" * 40, "tree_sha": "e" * 40}[key]
        result = case.with_binding(source=dict(SOURCE, **{key: other}))
        assert result.admissible is False
        assert "PAYLOAD_SOURCE_MISMATCH" in codes(result)

    def test_the_payload_artifact_is_required_evidence(self, case: Case) -> None:
        """v2 has no birth contract to bind the payload by digest in its stead."""
        with pytest.raises(TypeError):
            adapter.bind(case.binding, manifest=case.manifest)  # type: ignore[call-arg]


# ─────────────────────────────────────────────────────────────────────────────
# Reject — the binding itself
# ─────────────────────────────────────────────────────────────────────────────


class TestMalformedBindings:
    @pytest.mark.parametrize("document", [None, [], "binding", 3])
    def test_a_non_object_is_named(self, document: object) -> None:
        assert adapter.validate_binding_document(document) == ["binding is not a JSON object"]

    @pytest.mark.parametrize(
        "schema", ["l9.product-birth-binding/v1", "l9.product-birth-binding/v3", None]
    )
    def test_an_unrecognized_schema_reports_only_that(self, case: Case, schema: object) -> None:
        """v1 included: there is no compatibility path through the retired contract."""
        errors = adapter.validate_binding_document(dict(case.binding, schema=schema))
        assert len(errors) == 1
        assert "unrecognized binding schema" in errors[0]

    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ({"source": dict(SOURCE, revision="short")}, "source.revision"),
            ({"source": dict(SOURCE, repository="IdeaOS")}, "source.repository"),
            (
                {"source": {"repository": "Quantum-L9/IdeaOS", "revision": REVISION}},
                "missing tree_sha",
            ),
            ({"factory": dict(FACTORY, revision="main")}, "factory.revision"),
            ({"payload": {"ref": "x", "digest": "sha256:nope"}}, "payload.digest"),
            ({"manifest": {"ref": "", "digest": MANIFEST_DIGEST}}, "manifest.ref"),
            ({"topology": {"ref": TOPOLOGY["ref"]}}, "missing digest"),
            ({"product": {"id": "l9.product/ideaos", "kind": ""}}, "product.kind"),
            ({"product": {"id": "l9.product/ideaos", "kind": " node"}}, "product.kind"),
            ({"product": {"id": "", "kind": "node"}}, "product.id"),
            ({"manifest": "l9.product-manifest/ideaos@1"}, "manifest is not an object"),
            ({"compiler": {**COMPILER, "inputs": {}}}, "compiler.inputs is missing"),
            ({"compiler": {"engine": COMPILER["engine"]}}, "compiler is missing"),
        ],
    )
    def test_malformed_fields_are_named(self, case: Case, mutation: dict, expected: str) -> None:
        errors = adapter.validate_binding_document(dict(case.binding, **mutation))
        assert any(expected in err for err in errors), errors

    def test_every_error_is_reported_not_just_the_first(self, case: Case) -> None:
        broken = dict(case.binding, source={"repository": "bad"}, factory={}, compiler={})
        assert len(adapter.validate_binding_document(broken)) >= 4

    def test_a_malformed_binding_never_reaches_the_artifacts(self, case: Case) -> None:
        """BINDING_MALFORMED stands alone: coordinates checked against a
        document that failed its own contract would be noise."""
        case.binding["source"] = {"repository": "bad"}
        result = case.bind()
        assert result.admissible is False
        assert codes(result) == ["BINDING_MALFORMED"]
        assert result.coordinates == {}


class TestTheContractSurfaceIsClosed:
    """What a consumer may route on is enumerable, and what is written to disk
    is written the one way the factory already writes it."""

    def test_the_rendering_is_the_factory_rendering(self) -> None:
        """One rendering, one digest: the adapter must not own a second way to
        turn a document into the bytes a digest covers."""
        assert adapter.render_document is compiler.render_payload

    def test_an_admissible_rendering_lists_every_coordinate(self, case: Case) -> None:
        text = case.bind().render()
        for key in adapter.COORDINATE_KEYS:
            assert f"  {key:<16} " in text, key
        assert set(adapter.COORDINATE_KEYS) == set(case.bind().coordinates)
        assert "ADMISSIBLE" in text

    def test_no_birth_contract_code_survives(self) -> None:
        """The retired contract has no failure code left to route on."""
        assert not [code for code in adapter.FAILURE_CODES if "CONTRACT" in code]

    def test_every_emitted_failure_code_is_published(self, case: Case) -> None:
        """Every reject path in the matrix above, driven once more, may only
        emit codes FAILURE_CODES declares — an undeclared code is a contract
        change nobody announced."""
        manifest = make_manifest(unresolved=[{"ref": "x"}], manifest_digest="sha256:" + "9" * 64)
        product = manifest["product"]
        assert isinstance(product, dict)
        product["kind"] = "unknown"
        product["archetype_ref"] = ""
        authority = manifest["authority"]
        assert isinstance(authority, dict)
        authority["authority_revision"] = "unknown"
        drifted = adapter.Artifact.from_document(dict(case.payload.document, mode="authoritative"))
        case.binding = make_binding(
            case.manifest_doc,
            case.payload,
            topology={"ref": "other", "digest": "other"},
            product={"id": "l9.product/other", "kind": "node"},
            source=dict(SOURCE, revision="d" * 40),
            compiler={**COMPILER, "version": "0.0.1", "inputs": {**INPUTS, "topology": "x.yaml"}},
        )
        result = case.bind(manifest=adapter.Artifact.from_document(manifest), payload=drifted)
        emitted = set(codes(result))
        assert emitted <= adapter.FAILURE_CODES, emitted - adapter.FAILURE_CODES
        assert len(emitted) >= 9

    def test_every_published_failure_code_is_reachable(self) -> None:
        """The inverse: a code nothing can emit is a promise nobody keeps."""
        source = ADAPTER_MODULE.read_text(encoding="utf-8")
        checks = source.split("# The checks", 1)[1]
        for code in adapter.FAILURE_CODES:
            assert f'"{code}"' in checks, code


class TestEveryFailureIsReported:
    def test_independent_failures_accumulate(self, case: Case) -> None:
        manifest = make_manifest(unresolved=[{"ref": "x"}], manifest_digest="sha256:" + "9" * 64)
        product = manifest["product"]
        assert isinstance(product, dict)
        product["kind"] = ""
        case.binding = make_binding(
            case.manifest_doc, case.payload, compiler={**COMPILER, "version": "x"}
        )
        result = case.bind(manifest=adapter.Artifact.from_document(manifest))
        assert {
            "MANIFEST_UNRESOLVED",
            "MANIFEST_DIGEST_MISMATCH",
            "PRODUCT_KIND_NOT_EXPLICIT",
            "COMPILER_COORDINATE_MISMATCH",
        } <= set(codes(result))
        assert result.coordinates == {}

    def test_an_inadmissible_result_carries_no_coordinates(self, case: Case) -> None:
        """A partially validated coordinate set reads like a validated one."""
        result = case.with_manifest(unresolved=[{"ref": "x"}])
        assert result.to_dict()["coordinates"] == {}
        assert "INADMISSIBLE" in result.render()


# ─────────────────────────────────────────────────────────────────────────────
# The published schema agrees with the gate; v1 is history, not a path
# ─────────────────────────────────────────────────────────────────────────────


class TestThePublishedSchemaAgreesWithTheGate:
    @staticmethod
    def _validator():
        jsonschema = pytest.importorskip("jsonschema")
        return jsonschema.Draft202012Validator(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))

    def test_the_schema_file_is_a_valid_schema(self) -> None:
        jsonschema = pytest.importorskip("jsonschema")
        jsonschema.Draft202012Validator.check_schema(
            json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        )

    def test_the_schema_file_is_where_the_module_says(self) -> None:
        assert SCHEMA_FILE == REPO / adapter.SCHEMA_PATH
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        assert schema["title"] == adapter.SCHEMA
        assert schema["properties"]["schema"]["const"] == adapter.SCHEMA
        assert "birth_contract" not in schema["properties"]
        assert set(schema["required"]) == {"schema", *adapter.BINDING_SECTIONS}

    def test_a_consistent_binding_satisfies_the_published_schema(self, case: Case) -> None:
        assert list(self._validator().iter_errors(case.binding)) == []
        assert adapter.validate_binding_document(case.binding) == []

    @pytest.mark.parametrize(
        "mutation",
        [
            {"schema": "l9.product-birth-binding/v1"},
            {"schema": "l9.product-birth-binding/v3"},
            {"schema": None},
            {"repository_shape": {"matched": ["src"]}},
            {"kind_hint": "node"},
            {"birth_contract": {"ref": "x", "digest": "sha256:" + "0" * 64}},
            {"product": {"id": "l9.product/ideaos"}},
            {"product": {"id": "l9.product/ideaos", "kind": ""}},
            {"product": {"id": "l9.product/ideaos", "kind": "node", "shape": "x"}},
            {"manifest": {"ref": "x"}},
            {"manifest": {"ref": "x", "digest": " "}},
            {"manifest": {"ref": " l9.product-manifest/ideaos@1", "digest": MANIFEST_DIGEST}},
            {"product": {"id": "l9.product/ideaos", "kind": "node "}},
            {"topology": {"ref": "a\nb", "digest": "y"}},
            {"topology": {"ref": "x", "digest": "y", "extra": 1}},
            {"source": {"repository": "IdeaOS", "revision": REVISION, "tree_sha": TREE}},
            {"source": {"repository": "Q/I", "revision": "short", "tree_sha": TREE}},
            {"source": {"repository": "Q/I", "revision": REVISION}},
            {"source": dict(SOURCE, path="/srv/x")},
            {"payload": {"ref": "", "digest": "sha256:" + "0" * 64}},
            {"payload": {"ref": "x", "digest": "0" * 64}},
            {"factory": {"repository": "Quantum-L9/l9-repo-template"}},
            {"factory": {"repository": "Quantum-L9/l9-repo-template", "revision": "main"}},
            {"factory": dict(FACTORY, path="/srv/factory")},
            {"compiler": {**COMPILER, "revision": "main"}},
            {"compiler": {**COMPILER, "engine": "engine"}},
            {"compiler": {**COMPILER, "version": ""}},
            {"compiler": {**COMPILER, "inputs": {**INPUTS, "topology": "/abs.yaml"}}},
            {"compiler": {**COMPILER, "inputs": {**INPUTS, "topology": "../x.yaml"}}},
            {"compiler": {**COMPILER, "inputs": {**INPUTS, "topology": "./x.yaml"}}},
            {"compiler": {**COMPILER, "inputs": {**INPUTS, "extra": "x.yaml"}}},
            {
                "compiler": {
                    **COMPILER,
                    "inputs": {k: v for k, v in INPUTS.items() if k != "authority_lock"},
                }
            },
            {"compiler": {k: v for k, v in COMPILER.items() if k != "inputs"}},
        ],
    )
    def test_both_readers_reject_the_same_documents(self, case: Case, mutation: dict) -> None:
        """A rule stated by only one of the two readers is a rule that can drift."""
        broken = dict(case.binding, **mutation)
        assert adapter.validate_binding_document(broken), "the gate accepted it"
        assert list(self._validator().iter_errors(broken)), "the published schema accepted it"

    @pytest.mark.parametrize(
        "mutation",
        [
            {"manifest": {"ref": "l9.product-manifest/ideaos@1", "digest": "blake3:abc"}},
            {"topology": {"ref": "ideaos", "digest": "v1"}},
            {"product": {"id": "ideaos", "kind": "dependency"}},
            {
                "compiler": {
                    **COMPILER,
                    "inputs": {k: v for k, v in INPUTS.items() if k != "contract_catalog"},
                }
            },
            {
                "compiler": {
                    **COMPILER,
                    "inputs": {**INPUTS, "topology": "nested/dir/topology.yaml"},
                }
            },
        ],
    )
    def test_both_readers_accept_the_same_documents(self, case: Case, mutation: dict) -> None:
        """Semantic refs and digests are upstream syntax: both readers accept
        any non-empty token rather than guessing a format."""
        allowed = dict(case.binding, **mutation)
        assert adapter.validate_binding_document(allowed) == []
        assert list(self._validator().iter_errors(allowed)) == []


class TestV1IsHistoryNotAPath:
    def test_the_superseded_schemas_are_kept_as_evidence(self) -> None:
        v1 = json.loads((SUPERSEDED / "l9-product-birth-binding.v1.schema.json").read_text())
        contract = json.loads((SUPERSEDED / "birth-contract.v1.schema.json").read_text())
        assert v1["title"] == "l9.product-birth-binding/v1"
        assert "birth_contract" in v1["properties"]
        assert contract["$id"] == "l9.repo-birth-contract/v1"
        assert "lineage" in contract["properties"]
        assert (SUPERSEDED / "README.md").is_file()

    def test_no_live_birth_module_reads_the_superseded_schemas(self) -> None:
        """Prose may name the history; no string a module could open or compare does."""
        for module in sorted(BIRTH_RUNNER.glob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            docstrings = {
                node.body[0].value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value not in docstrings
            }
            for token in (
                "superseded",
                "birth-contract",
                "repo-birth-contract",
                "repo-birth-evidence",
            ):
                assert not [s for s in literals if token in s], f"{module.name}: {token!r}"

    def test_a_v1_binding_is_refused_as_a_whole(self, case: Case) -> None:
        v1 = dict(case.binding, schema="l9.product-birth-binding/v1")
        del v1["compiler"]
        v1["birth_contract"] = {"ref": "x", "digest": "sha256:" + "0" * 64}
        result = adapter.bind(v1, manifest=case.manifest, payload=case.payload)
        assert result.admissible is False
        assert codes(result) == ["BINDING_MALFORMED"]
        assert "unrecognized binding schema" in result.failures[0].detail


# ─────────────────────────────────────────────────────────────────────────────
# Command line
# ─────────────────────────────────────────────────────────────────────────────


class TestCommandLine:
    @staticmethod
    def _write(tmp_path: Path, case: Case) -> dict[str, Path]:
        paths = {
            "binding": tmp_path / "binding.json",
            "manifest": tmp_path / "manifest.json",
            "payload": tmp_path / "birth-payload.json",
        }
        paths["binding"].write_text(adapter.render_document(case.binding), encoding="utf-8")
        paths["manifest"].write_text(adapter.render_document(case.manifest_doc), encoding="utf-8")
        paths["payload"].write_text(
            adapter.render_document(case.payload.document), encoding="utf-8"
        )
        return paths

    def _argv(self, paths: dict[str, Path], *extra: str) -> list[str]:
        return [
            "--binding",
            str(paths["binding"]),
            "--manifest",
            str(paths["manifest"]),
            "--payload",
            str(paths["payload"]),
            *extra,
        ]

    def test_an_admissible_binding_exits_zero(self, tmp_path: Path, case: Case) -> None:
        """The on-disk rendering hashes to the digests the fixtures computed in
        memory — one rendering, one digest, on both sides of the boundary."""
        assert adapter.main(self._argv(self._write(tmp_path, case))) == 0

    def test_json_output_is_the_result_document(
        self, tmp_path: Path, case: Case, capsys: pytest.CaptureFixture[str]
    ) -> None:
        adapter.main(self._argv(self._write(tmp_path, case), "--json"))
        document = json.loads(capsys.readouterr().out)
        assert document["schema"] == adapter.RESULT_SCHEMA
        assert document["admissible"] is True
        assert document["coordinates"]["factory"] == FACTORY
        assert document["coordinates"]["compiler"] == COMPILER

    def test_an_inadmissible_binding_exits_one(self, tmp_path: Path, case: Case) -> None:
        paths = self._write(tmp_path, case)
        paths["manifest"].write_text(
            adapter.render_document(make_manifest(unresolved=[{"ref": "x"}])), encoding="utf-8"
        )
        assert adapter.main(self._argv(paths)) == 1

    def test_the_payload_is_required_on_the_command_line(self, tmp_path: Path, case: Case) -> None:
        paths = self._write(tmp_path, case)
        with pytest.raises(SystemExit) as exc:
            adapter.main(self._argv(paths)[:-2])
        assert exc.value.code == 2

    def test_a_birth_contract_flag_is_gone(self, tmp_path: Path, case: Case) -> None:
        paths = self._write(tmp_path, case)
        with pytest.raises(SystemExit):
            adapter.main(self._argv(paths, "--birth-contract", str(paths["binding"])))

    def test_an_unreadable_artifact_exits_two(self, tmp_path: Path, case: Case) -> None:
        paths = self._write(tmp_path, case)
        paths["payload"].write_text("not json\n", encoding="utf-8")
        assert adapter.main(self._argv(paths)) == 2

    def test_a_missing_artifact_exits_two(self, tmp_path: Path, case: Case) -> None:
        paths = self._write(tmp_path, case)
        paths["manifest"].unlink()
        assert adapter.main(self._argv(paths)) == 2

    def test_a_malformed_binding_file_is_inadmissible_not_unreadable(
        self, tmp_path: Path, case: Case
    ) -> None:
        paths = self._write(tmp_path, case)
        paths["binding"].write_text('{"schema": "l9.product-birth-binding/v9"}\n', encoding="utf-8")
        assert adapter.main(self._argv(paths)) == 1
