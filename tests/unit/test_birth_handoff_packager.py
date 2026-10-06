"""The factory-owned repository-birth packager.

`package_birth_handoff.py` turns a verified source snapshot, its upstream
lineage evidence and an already-resolved ProductManifest into the three
artifacts an adapter-backed birth carries: the compiled `l9.birth-payload/v1`,
the `l9.repo-birth-contract/v1`, and the `l9.product-birth-binding/v1`. It owns
packaging only. The payload compiler compiles, the adapter decides, and the
ProductManifest is read, never written.

This suite is the migrated owner of the predecessor skill's `self_test.py`
(Cursor-Governance `skills/l9-repo-birth`), extended with the factory and
binding obligations that ownership move adds.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
CONTRACT_SCHEMA = BIRTH_RUNNER / "schemas" / "birth-contract.schema.json"
FACTORY_ORIGIN = "https://github.com/Quantum-L9/l9-repo-template.git"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


packager = _load("l9_birth_handoff_packager", BIRTH_RUNNER / "package_birth_handoff.py")
adapter = packager.birth_adapter
# The adapter suite owns the ProductManifest fixture; one reading of its shape.
adapter_fixtures = _load(
    "l9_birth_adapter_fixtures_for_packager", REPO / "tests" / "unit" / "test_l9_birth_adapter.py"
)
new_repo = _load("l9_birth_new_repo_for_packager", BIRTH_RUNNER / "new_repo.py")

GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *GIT_IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _commit_all(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


LINEAGE_FILES = {
    "idea_execute_receipt": (
        "lineage/idea-execute-receipt.json",
        '{"schema":"l9.idea-execute-receipt/v1"}\n',
    ),
    "gar_decision": (
        "lineage/gar-decision.json",
        '{"schema":"l9.gar.product-architecture-decision/v1"}\n',
    ),
    "plan": ("lineage/plan.json", '{"schema":"l9.plan-document/v1"}\n'),
    "campaign_source": ("lineage/campaign-source.yaml", "schema: l9.campaign-source/v2\n"),
    "pe_receipt": ("lineage/pe-receipt.json", '{"schema":"l9.program-execution-receipt/v1"}\n'),
}


class Fixture:
    """A clean source + lineage, a clean fixture factory, and a resolved manifest."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.source = root / "source"
        self.factory = root / "factory"
        self.out = root / "out"
        self._make_source()
        self._make_factory()
        self.manifest_doc = adapter_fixtures.make_manifest()
        self.manifest = root / "product-manifest.json"
        self.manifest.write_text(json.dumps(self.manifest_doc, indent=2) + "\n", encoding="utf-8")
        self.manifest_ref = "l9.product-manifest/ideaos@1"
        self.evidence_doc = self._evidence()
        self.evidence = root / "evidence.json"
        self.write_evidence(self.evidence_doc)

    def _make_source(self) -> None:
        (self.source / "src" / "ideaos").mkdir(parents=True)
        (self.source / "src" / "ideaos" / "__init__.py").write_text("", encoding="utf-8")
        (self.source / "README.md").write_text("# Fixture\n", encoding="utf-8")
        for rel, body in LINEAGE_FILES.values():
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (self.source / "receipts").mkdir()
        (self.source / "receipts" / "pec.json").write_text(
            '{"schema":"l9.pec-receipt/v1"}\n', encoding="utf-8"
        )
        _commit_all(self.source)
        self.revision = _git(self.source, "rev-parse", "HEAD")
        self.tree = _git(self.source, "rev-parse", "HEAD^{tree}")

    def _make_factory(self) -> None:
        """The factory surfaces the packager and compiler read, at one clean commit."""
        for rel in (
            "scripts/birth-runner/payload-ownership.yaml",
            "scripts/birth-runner/compile_birth_payload.py",
            "scripts/birth-runner/new_repo.py",
        ):
            target = self.factory / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, target)
        _commit_all(self.factory)
        _git(self.factory, "remote", "add", "origin", FACTORY_ORIGIN)
        self.factory_revision = _git(self.factory, "rev-parse", "HEAD")

    def _evidence(self) -> dict[str, object]:
        evidence: dict[str, object] = {
            "schema": "l9.repo-birth-evidence/v1",
            "source_repository": "Quantum-L9/IdeaOS",
            "source_revision": self.revision,
            "source_tree_sha": self.tree,
            "acceptance_evidence_refs": ["receipts/pec.json"],
        }
        for key, (rel, _body) in LINEAGE_FILES.items():
            evidence[key] = _digest(self.source / rel)
            evidence[f"{key}_path"] = rel
        return evidence

    def write_evidence(self, document: dict[str, object]) -> None:
        self.evidence.write_text(json.dumps(document), encoding="utf-8")

    def write_manifest(self, document: dict[str, object]) -> None:
        self.manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def package(self, **overrides: object) -> dict[str, object]:
        args: dict[str, object] = {
            "source": self.source,
            "evidence_path": self.evidence,
            "manifest_path": self.manifest,
            "manifest_ref": self.manifest_ref,
            "out_dir": self.out,
            "operation": "local_validation",
            "factory_root": self.factory,
        }
        args.update(overrides)
        return packager.package(**args)  # type: ignore[arg-type]


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def _read(path: object) -> dict[str, object]:
    return json.loads(Path(str(path)).read_text(encoding="utf-8"))


def _outputs(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


# ─────────────────────────────────────────────────────────────────────────────
# A complete, consistent package
# ─────────────────────────────────────────────────────────────────────────────


class TestACompletePackage:
    def test_it_is_adapter_admissible(self, fx: Fixture) -> None:
        result = fx.package()
        assert result["status"] == "PASS"
        assert _outputs(fx.out) == [
            "birth-contract.json",
            "birth-payload.json",
            "product-birth-binding.json",
        ]
        verdict = adapter.bind(
            adapter.load_binding(Path(str(result["binding"]))),
            manifest=adapter.load_artifact(fx.manifest),
            birth_contract=adapter.load_artifact(Path(str(result["contract"]))),
            payload=adapter.load_artifact(Path(str(result["payload"]))),
        )
        assert verdict.admissible, verdict.failures

    def test_the_binding_carries_only_proven_coordinates(self, fx: Fixture) -> None:
        result = fx.package()
        binding = _read(result["binding"])
        product = fx.manifest_doc["product"]
        assert isinstance(product, dict)
        assert binding["product"] == {"id": product["id"], "kind": product["kind"]}
        assert binding["manifest"] == {
            "ref": fx.manifest_ref,
            "digest": fx.manifest_doc["manifest_digest"],
        }
        assert binding["topology"] == fx.manifest_doc["source_topology"]
        assert binding["source"] == {
            "repository": "Quantum-L9/IdeaOS",
            "revision": fx.revision,
            "tree_sha": fx.tree,
        }
        assert binding["birth_contract"] == {
            "ref": str(result["contract"]),
            "digest": _digest(Path(str(result["contract"]))),
        }
        assert binding["payload"] == {
            "ref": str(result["payload"]),
            "digest": _digest(Path(str(result["payload"]))),
        }
        assert binding["factory"] == {
            "repository": "Quantum-L9/l9-repo-template",
            "revision": fx.factory_revision,
        }

    def test_the_contract_binds_the_running_factory_and_the_emitted_payload(
        self, fx: Fixture
    ) -> None:
        result = fx.package()
        contract = _read(result["contract"])
        assert (
            list(
                Draft202012Validator(json.loads(CONTRACT_SCHEMA.read_text())).iter_errors(contract)
            )
            == []
        )
        assert contract["operation"] == "local_validation"
        assert contract["source"] == {
            "path": str(fx.source.resolve()),
            "repository": "Quantum-L9/IdeaOS",
            "revision": fx.revision,
            "tree_sha": fx.tree,
            "clean": True,
        }
        factory = contract["factory"]
        assert isinstance(factory, dict)
        assert factory["revision"] == fx.factory_revision
        assert factory["compiler"].endswith("scripts/birth-runner/compile_birth_payload.py")
        assert factory["birth_front_door"].endswith("scripts/birth-runner/new_repo.py")
        assert contract["payload"] == {
            "ref": str(result["payload"]),
            "digest": _digest(Path(str(result["payload"]))),
            "schema": "l9.birth-payload/v1",
        }
        lineage = contract["lineage"]
        assert isinstance(lineage, dict)
        assert lineage["acceptance_evidence_refs"] == ["receipts/pec.json"]
        for key in LINEAGE_FILES:
            assert lineage[key] == fx.evidence_doc[key]

    def test_the_payload_is_the_existing_compilers_output(self, fx: Fixture) -> None:
        result = fx.package()
        expected = packager.compiler.render_payload(
            packager.compiler.compile_payload(
                fx.source,
                template_src=fx.factory,
                source_repository_override="Quantum-L9/IdeaOS",
            )
        )
        assert Path(str(result["payload"])).read_text(encoding="utf-8") == expected

    def test_emission_is_deterministic(self, fx: Fixture) -> None:
        first = fx.package()
        before = {name: (fx.out / name).read_bytes() for name in _outputs(fx.out)}
        second = fx.package()
        assert first == second
        assert {name: (fx.out / name).read_bytes() for name in _outputs(fx.out)} == before

    def test_remote_birth_is_carried_as_the_operation(self, fx: Fixture) -> None:
        result = fx.package(operation="remote_birth")
        assert _read(result["contract"])["operation"] == "remote_birth"

    def test_the_source_repository_override_is_honored(self, fx: Fixture) -> None:
        result = fx.package(source_repository="Quantum-L9/IdeaOS-renamed")
        assert _read(result["contract"])["source"]["repository"] == "Quantum-L9/IdeaOS-renamed"
        assert _read(result["binding"])["source"]["repository"] == "Quantum-L9/IdeaOS-renamed"


# ─────────────────────────────────────────────────────────────────────────────
# ProductManifest: consumed, never produced; its ref is explicit
# ─────────────────────────────────────────────────────────────────────────────


class TestTheProductManifestIsConsumedNeverProduced:
    def test_its_bytes_are_never_written(self, fx: Fixture) -> None:
        before = fx.manifest.read_bytes()
        fx.package()
        assert fx.manifest.read_bytes() == before
        assert "product-manifest.json" not in _outputs(fx.out)

    @pytest.mark.parametrize("ref", ["", "   ", " padded", "two\nlines"])
    def test_a_missing_or_unusable_ref_is_refused_not_inferred(self, fx: Fixture, ref: str) -> None:
        with pytest.raises(packager.HandoffError, match="ProductManifest ref"):
            fx.package(manifest_ref=ref)
        assert _outputs(fx.out) == []

    def test_the_ref_is_carried_verbatim(self, fx: Fixture) -> None:
        """Not derived from product id, repository, topology, filename or kind."""
        result = fx.package(manifest_ref="l9.product-manifest/anything-the-owner-says@7")
        assert _read(result["binding"])["manifest"]["ref"] == (
            "l9.product-manifest/anything-the-owner-says@7"
        )

    def test_the_cli_requires_the_ref(self, fx: Fixture) -> None:
        with pytest.raises(SystemExit) as exc:
            packager.parse_args(
                [
                    "--source",
                    str(fx.source),
                    "--evidence",
                    str(fx.evidence),
                    "--manifest",
                    str(fx.manifest),
                    "--out-dir",
                    str(fx.out),
                ]
            )
        assert exc.value.code == 2

    def test_the_cli_takes_no_factory_argument(self) -> None:
        with pytest.raises(SystemExit):
            packager.parse_args(["--factory", "/elsewhere"])

    @pytest.mark.parametrize("kind", ["node", "library"])
    def test_product_kind_is_read_from_the_manifest(self, fx: Fixture, kind: str) -> None:
        product = {"id": "l9.product/ideaos", "kind": kind, "archetype_ref": "l9.archetype/x@1"}
        fx.write_manifest(adapter_fixtures.make_manifest(product=product))
        result = fx.package()
        assert _read(result["binding"])["product"]["kind"] == kind

    @pytest.mark.parametrize("drop", ["id", "kind"])
    def test_a_manifest_without_product_coordinates_is_refused_not_filled_in(
        self, fx: Fixture, drop: str
    ) -> None:
        product = {"id": "l9.product/ideaos", "kind": "node", "archetype_ref": "l9.archetype/x@1"}
        del product[drop]
        fx.write_manifest(adapter_fixtures.make_manifest(product=product))
        with pytest.raises(packager.HandoffError, match=f"product.{drop}"):
            fx.package()
        assert _outputs(fx.out) == []

    def test_an_unresolved_manifest_is_refused_by_the_existing_adapter(self, fx: Fixture) -> None:
        fx.write_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
        with pytest.raises(packager.HandoffError, match="MANIFEST_UNRESOLVED"):
            fx.package()
        assert _outputs(fx.out) == [], "a refused bundle leaves nothing behind"


# ─────────────────────────────────────────────────────────────────────────────
# Lineage and source (the predecessor self_test's obligations)
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceAndLineage:
    def test_a_dirty_source_is_refused(self, fx: Fixture) -> None:
        (fx.source / "dirty.txt").write_text("drift\n", encoding="utf-8")
        with pytest.raises(packager.HandoffError, match="dirty"):
            fx.package()
        assert _outputs(fx.out) == []

    @pytest.mark.parametrize("key", ["source_revision", "source_tree_sha"])
    def test_a_revision_or_tree_mismatch_is_refused(self, fx: Fixture, key: str) -> None:
        fx.write_evidence({**fx.evidence_doc, key: "e" * 40})
        with pytest.raises(packager.HandoffError, match="does not match the current clean source"):
            fx.package()

    @pytest.mark.parametrize("key", sorted(LINEAGE_FILES))
    def test_a_broken_lineage_digest_is_refused(self, fx: Fixture, key: str) -> None:
        fx.write_evidence({**fx.evidence_doc, key: "sha256:" + "b" * 64})
        with pytest.raises(packager.HandoffError, match="does not match hashed"):
            fx.package()

    def test_a_missing_lineage_path_is_refused(self, fx: Fixture) -> None:
        evidence = dict(fx.evidence_doc)
        del evidence["plan_path"]
        fx.write_evidence(evidence)
        with pytest.raises(packager.HandoffError, match="plan_path"):
            fx.package()

    def test_missing_acceptance_evidence_is_refused(self, fx: Fixture) -> None:
        fx.write_evidence({**fx.evidence_doc, "acceptance_evidence_refs": ["receipts/absent.json"]})
        with pytest.raises(packager.HandoffError, match="lineage artifact missing"):
            fx.package()

    def test_empty_acceptance_evidence_is_refused(self, fx: Fixture) -> None:
        fx.write_evidence({**fx.evidence_doc, "acceptance_evidence_refs": []})
        with pytest.raises(packager.HandoffError, match="acceptance_evidence_refs"):
            fx.package()

    def test_a_pe_receipt_without_schema_identity_is_refused(self, fx: Fixture) -> None:
        receipt = fx.source / "lineage" / "pe-receipt.json"
        receipt.write_text('{"status":"pass"}\n', encoding="utf-8")
        _git(fx.source, "add", "-A")
        _git(fx.source, "commit", "-q", "-m", "receipt without schema")
        evidence = {
            **fx.evidence_doc,
            "pe_receipt": _digest(receipt),
            "source_revision": _git(fx.source, "rev-parse", "HEAD"),
            "source_tree_sha": _git(fx.source, "rev-parse", "HEAD^{tree}"),
        }
        fx.write_evidence(evidence)
        with pytest.raises(packager.HandoffError, match="pe_receipt artifact must declare schema"):
            fx.package()

    def test_the_wrong_evidence_schema_is_refused(self, fx: Fixture) -> None:
        fx.write_evidence({**fx.evidence_doc, "schema": "l9.repo-birth-evidence/v2"})
        with pytest.raises(packager.HandoffError, match="l9.repo-birth-evidence/v1"):
            fx.package()


# ─────────────────────────────────────────────────────────────────────────────
# The running repository is the factory
# ─────────────────────────────────────────────────────────────────────────────


class TestTheRunningFactory:
    def test_a_dirty_factory_is_refused(self, fx: Fixture) -> None:
        (fx.factory / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
        with pytest.raises(packager.HandoffError, match="factory"):
            fx.package()
        assert _outputs(fx.out) == []

    def test_a_checkout_of_another_repository_is_not_the_factory(self, fx: Fixture) -> None:
        _git(fx.factory, "remote", "set-url", "origin", "https://github.com/Quantum-L9/other.git")
        with pytest.raises(packager.HandoffError, match="Quantum-L9/l9-repo-template"):
            fx.package()

    def test_the_default_factory_is_this_repository(self) -> None:
        assert packager.TEMPLATE_ROOT == REPO
        assert packager.FACTORY_REPOSITORY == "Quantum-L9/l9-repo-template"


# ─────────────────────────────────────────────────────────────────────────────
# The birth contract: locked shape, dependency-light validator
# ─────────────────────────────────────────────────────────────────────────────


def _valid_contract(fx: Fixture) -> dict[str, object]:
    return _read(fx.package()["contract"])


def _mutations() -> list[tuple[str, object]]:
    return [
        ("schema", "l9.repo-birth-contract/v2"),
        ("operation", "publish"),
        ("source.clean", False),
        ("source.clean", 1),
        ("source.revision", "abc"),
        ("source.repository", "no-slash"),
        ("source.path", ""),
        ("lineage.plan", "sha1:abc"),
        ("lineage.acceptance_evidence_refs", []),
        ("lineage.acceptance_evidence_refs", [""]),
        ("factory.revision", "A" * 40),
        ("factory.compiler", 7),
        ("payload.schema", "l9.birth-payload/v2"),
        ("payload.digest", "sha256:XYZ"),
        ("extra", "field"),
        ("source.extra", "field"),
        ("lineage", None),
    ]


def _mutate(document: dict[str, object], dotted: str, value: object) -> dict[str, object]:
    out = json.loads(json.dumps(document))
    parts = dotted.split(".")
    target = out
    for part in parts[:-1]:
        target = target[part]
    if value is None:
        del target[parts[-1]]
    else:
        target[parts[-1]] = value
    return out


class TestTheBirthContract:
    def test_the_schema_is_the_locked_contract(self) -> None:
        schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
        assert schema["$id"] == "l9.repo-birth-contract/v1"
        assert schema["additionalProperties"] is False
        assert schema["required"] == [
            "schema",
            "operation",
            "source",
            "lineage",
            "factory",
            "payload",
        ]

    def test_a_valid_contract_passes_both_validators(self, fx: Fixture) -> None:
        document = _valid_contract(fx)
        assert packager.validate_contract_document(document) == []
        schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(document)) == []

    @pytest.mark.parametrize(("dotted", "value"), _mutations())
    def test_the_light_validator_agrees_with_the_schema(
        self, fx: Fixture, dotted: str, value: object
    ) -> None:
        """Held to the moved JSON Schema: every malformed shape is refused by both."""
        document = _mutate(_valid_contract(fx), dotted, value)
        schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(document)), "fixture is not malformed"
        assert packager.validate_contract_document(document), f"{dotted}={value!r} was accepted"

    def test_a_malformed_contract_is_never_emitted(self, fx: Fixture) -> None:
        with pytest.raises(packager.HandoffError, match="birth contract"):
            fx.package(operation="publish")
        assert _outputs(fx.out) == []

    def test_the_validator_refuses_a_schema_keyword_it_cannot_interpret(self) -> None:
        with pytest.raises(packager.HandoffError, match="unsupported"):
            packager.validate_against({"type": "string", "format": "uri"}, "x", "doc")

    def test_a_schema_pattern_never_becomes_a_runtime_regex(self) -> None:
        """Closed pattern set: an unknown pattern refuses instead of being compiled."""
        with pytest.raises(packager.HandoffError, match="unsupported pattern"):
            packager.validate_against({"type": "string", "pattern": "^(a+)+$"}, "aaa", "doc")

    def test_the_closed_pattern_set_is_exactly_the_schemas(self) -> None:
        found: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("pattern"), str):
                    found.add(node["pattern"])
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8")))
        assert found == set(packager._KNOWN_PATTERNS)


# ─────────────────────────────────────────────────────────────────────────────
# Self-proof: the existing adapter decides, and refuses every inconsistency
# ─────────────────────────────────────────────────────────────────────────────


def _edit_json(path: Path, dotted: str, value: object) -> None:
    path.write_text(
        packager.compiler.render_payload(_mutate(_read(path), dotted, value)), encoding="utf-8"
    )


class TestTheSelfProof:
    def _prove(self, fx: Fixture, result: dict[str, object]) -> object:
        return packager.prove_bundle(
            binding=Path(str(result["binding"])),
            manifest=fx.manifest,
            birth_contract=Path(str(result["contract"])),
            payload=Path(str(result["payload"])),
        )

    def test_the_emitted_bundle_proves(self, fx: Fixture) -> None:
        assert self._prove(fx, fx.package()).admissible

    @pytest.mark.parametrize(
        ("dotted", "value", "code"),
        [
            ("manifest.digest", "sha256:" + "9" * 64, "MANIFEST_DIGEST_MISMATCH"),
            ("topology.digest", "sha256:" + "8" * 64, "TOPOLOGY_COORDINATE_MISMATCH"),
            ("source.revision", "f" * 40, "BIRTH_CONTRACT_SOURCE_MISMATCH"),
            ("payload.digest", "sha256:" + "7" * 64, "PAYLOAD_DIGEST_MISMATCH"),
            ("birth_contract.digest", "sha256:" + "6" * 64, "BIRTH_CONTRACT_DIGEST_MISMATCH"),
            ("factory.revision", "5" * 40, "FACTORY_COORDINATE_MISMATCH"),
        ],
    )
    def test_a_mismatched_binding_is_refused(
        self, fx: Fixture, dotted: str, value: str, code: str
    ) -> None:
        result = fx.package()
        _edit_json(Path(str(result["binding"])), dotted, value)
        with pytest.raises(packager.HandoffError, match=code):
            self._prove(fx, result)

    def test_a_changed_payload_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        _edit_json(Path(str(result["payload"])), "mode", "authoritative")
        with pytest.raises(packager.HandoffError, match="PAYLOAD_DIGEST_MISMATCH"):
            self._prove(fx, result)

    def test_a_changed_birth_contract_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        _edit_json(Path(str(result["contract"])), "operation", "remote_birth")
        with pytest.raises(packager.HandoffError, match="BIRTH_CONTRACT_DIGEST_MISMATCH"):
            self._prove(fx, result)


# ─────────────────────────────────────────────────────────────────────────────
# The packaged bundle meets the PREPARE gate (PR #50 unchanged)
# ─────────────────────────────────────────────────────────────────────────────


class TestThePrepareGateStillDecides:
    def _cfg(self, fx: Fixture, result: dict[str, object]) -> object:
        return new_repo.BirthConfig(
            org="Quantum-L9",
            repo="ideaos",
            pkg="ideaos",
            desc="IdeaOS",
            work_dir=fx.root / "work",
            payload=fx.source,
            payload_contract=Path(str(result["payload"])),
            template_src=fx.factory,
            org_profile_src=None,
            repo_class="non_constellation_python",
            remote=False,
            private=False,
            keep=False,
            receipt_path=None,
            bootstrap_timeout=1,
            product_birth_binding=Path(str(result["binding"])),
            product_manifest=fx.manifest,
            repo_birth_contract=Path(str(result["contract"])),
        )

    def _receipt(self, cfg: object, template_sha: str) -> object:
        receipt = new_repo.BirthReceipt(template_sha=template_sha)
        # As `_preflight_payload_contract` leaves it once the payload reproduced.
        receipt.payload_contract = str(cfg.payload_contract)  # type: ignore[attr-defined]
        return receipt

    def test_a_package_from_the_running_factory_is_admitted(self, fx: Fixture) -> None:
        result = fx.package()
        cfg = self._cfg(fx, result)
        receipt = self._receipt(cfg, fx.factory_revision)
        new_repo._stages._preflight_product_birth_adapter(cfg, receipt)
        assert receipt.stages[-1].key == "preflight.adapter"
        assert receipt.stages[-1].status == "PASS"

    def test_a_package_from_another_factory_revision_is_still_refused(self, fx: Fixture) -> None:
        result = fx.package()
        cfg = self._cfg(fx, result)
        receipt = self._receipt(cfg, "0" * 40)
        with pytest.raises(new_repo.BirthError, match="running factory revision"):
            new_repo._stages._preflight_product_birth_adapter(cfg, receipt)


def test_the_cli_reports_a_refusal_and_exits_nonzero(
    fx: Fixture, capsys: pytest.CaptureFixture[str]
) -> None:
    code = packager.main(
        [
            "--source",
            str(fx.source),
            "--evidence",
            str(fx.root / "absent-evidence.json"),
            "--manifest",
            str(fx.manifest),
            "--manifest-ref",
            fx.manifest_ref,
            "--out-dir",
            str(fx.out),
        ]
    )
    assert code == 1
    assert "REPO_BIRTH_HANDOFF: FAIL" in capsys.readouterr().err
    assert _outputs(fx.out) == []


def _state(out: Path) -> dict[str, tuple[bytes, int]]:
    """Every entry in the output directory, hidden ones included, with bytes and mtime."""
    if not out.exists():
        return {}
    return {
        p.name: (p.read_bytes() if p.is_file() else b"<dir>", p.stat().st_mtime_ns)
        for p in sorted(out.iterdir())
    }


BUNDLE = ["birth-contract.json", "birth-payload.json", "product-birth-binding.json"]


class TestTransactionalEmission:
    """F-051-001: a failed invocation never destroys, replaces or half-updates a proven bundle."""

    def test_a_first_emission_exposes_exactly_the_proven_bundle(self, fx: Fixture) -> None:
        fx.package()
        assert _outputs(fx.out) == BUNDLE

    def test_a_deterministic_rerun_is_a_no_op(self, fx: Fixture) -> None:
        fx.package()
        before = _state(fx.out)
        fx.package()
        assert _state(fx.out) == before, "an identical proven bundle is left untouched"

    def test_an_adapter_refusal_preserves_the_prior_bundle_exactly(self, fx: Fixture) -> None:
        fx.package()
        before = _state(fx.out)
        fx.write_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
        with pytest.raises(packager.HandoffError, match="MANIFEST_UNRESOLVED"):
            fx.package()
        assert _state(fx.out) == before

    @pytest.mark.parametrize("refusal", ["manifest_ref", "dirty_source", "evidence"])
    def test_an_early_refusal_cannot_make_a_stale_bundle_look_new(
        self, fx: Fixture, refusal: str
    ) -> None:
        fx.package()
        before = _state(fx.out)
        overrides: dict[str, object] = {}
        if refusal == "manifest_ref":
            overrides["manifest_ref"] = ""
        elif refusal == "dirty_source":
            (fx.source / "dirty.txt").write_text("drift\n", encoding="utf-8")
        else:
            fx.write_evidence({**fx.evidence_doc, "plan": "sha256:" + "b" * 64})
        with pytest.raises(packager.HandoffError):
            fx.package(**overrides)
        assert _state(fx.out) == before

    def test_a_failure_while_exposing_never_leaves_a_mixed_bundle(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The second file's exposure fails after the first moved: everything rolls back."""
        fx.package()
        before = _state(fx.out)
        fx.write_evidence(fx.evidence_doc)
        real_replace = Path.replace

        def failing_replace(self: Path, target: object) -> Path:
            if Path(str(target)).name == "birth-contract.json" and self.parent != fx.out:
                raise OSError("simulated failure exposing the birth contract")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", failing_replace)
        fx.write_manifest(
            adapter_fixtures.make_manifest(
                product={"id": "l9.product/ideaos", "kind": "library", "archetype_ref": "a@1"}
            )
        )
        with pytest.raises(OSError, match="simulated failure"):
            fx.package()
        assert _state(fx.out) == before

    def test_a_failure_while_exposing_into_an_empty_directory_leaves_it_empty(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_replace = Path.replace

        def failing_replace(self: Path, target: object) -> Path:
            if Path(str(target)).name == "product-birth-binding.json":
                raise OSError("simulated failure exposing the binding")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", failing_replace)
        with pytest.raises(OSError, match="simulated failure"):
            fx.package()
        assert _outputs(fx.out) == []

    def test_unrelated_files_in_the_output_directory_survive_a_refusal(self, fx: Fixture) -> None:
        fx.out.mkdir()
        (fx.out / "notes.txt").write_text("keep me\n", encoding="utf-8")
        before = _state(fx.out)
        fx.write_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
        with pytest.raises(packager.HandoffError):
            fx.package()
        assert _state(fx.out) == before


class TestOutputIsolation:
    """F-051-002: the handoff lives outside both authoritative trees."""

    @pytest.mark.parametrize(
        ("tree", "inside"),
        [
            ("source", "."),
            ("source", "handoff"),
            ("source", "lineage/out"),
            ("factory", "."),
            ("factory", "handoff"),
            ("factory", "scripts/birth-runner/out"),
        ],
    )
    def test_an_output_directory_in_either_tree_is_refused(
        self, fx: Fixture, tree: str, inside: str
    ) -> None:
        root = fx.source if tree == "source" else fx.factory
        target = root / inside
        existed = target.exists()
        with pytest.raises(packager.HandoffError, match=f"inside the {tree} checkout"):
            fx.package(out_dir=target)
        assert _git(fx.source, "status", "--porcelain") == ""
        assert _git(fx.factory, "status", "--porcelain") == ""
        assert target.exists() == existed


class TestLineageStaysInTheSnapshot:
    """S6549: lineage and acceptance paths resolve inside the source checkout or are refused."""

    def _commit(self, fx: Fixture, *paths: str) -> None:
        _git(fx.source, "add", "--", *paths)
        _git(fx.source, "commit", "-q", "-m", "lineage fixture")
        fx.write_evidence(
            {
                **fx.evidence_doc,
                "source_revision": _git(fx.source, "rev-parse", "HEAD"),
                "source_tree_sha": _git(fx.source, "rev-parse", "HEAD^{tree}"),
            }
        )

    def test_an_absolute_path_inside_the_source_still_resolves(self, fx: Fixture) -> None:
        absolute = str((fx.source / "receipts" / "pec.json").resolve())
        fx.write_evidence({**fx.evidence_doc, "acceptance_evidence_refs": [absolute]})
        assert fx.package()["status"] == "PASS"

    def test_an_absolute_path_outside_the_source_is_refused(self, fx: Fixture) -> None:
        outside = fx.root / "elsewhere.json"
        outside.write_text("{}\n", encoding="utf-8")
        fx.write_evidence({**fx.evidence_doc, "acceptance_evidence_refs": [str(outside)]})
        with pytest.raises(packager.HandoffError, match="outside the source checkout"):
            fx.package()

    def test_a_traversal_out_of_the_source_is_refused(self, fx: Fixture) -> None:
        (fx.root / "elsewhere.json").write_text("{}\n", encoding="utf-8")
        fx.write_evidence({**fx.evidence_doc, "acceptance_evidence_refs": ["../elsewhere.json"]})
        with pytest.raises(packager.HandoffError, match="outside the source checkout"):
            fx.package()

    def test_a_lineage_path_outside_the_source_is_refused(self, fx: Fixture) -> None:
        outside = fx.root / "plan.json"
        outside.write_text('{"schema":"l9.plan-document/v1"}\n', encoding="utf-8")
        fx.write_evidence({**fx.evidence_doc, "plan": _digest(outside), "plan_path": str(outside)})
        with pytest.raises(packager.HandoffError, match="outside the source checkout"):
            fx.package()

    def test_a_symlink_escaping_the_source_is_refused(self, fx: Fixture) -> None:
        (fx.root / "elsewhere.json").write_text("{}\n", encoding="utf-8")
        (fx.source / "receipts" / "escape.json").symlink_to(fx.root / "elsewhere.json")
        self._commit(fx, "receipts/escape.json")
        fx.write_evidence(
            {**_read(fx.evidence), "acceptance_evidence_refs": ["receipts/escape.json"]}
        )
        with pytest.raises(packager.HandoffError, match="escapes the source root"):
            fx.package()

    def test_an_ignored_uncommitted_lineage_file_is_refused(self, fx: Fixture) -> None:
        """Present on disk but not in the commit: not part of the verified snapshot."""
        (fx.source / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        self._commit(fx, ".gitignore")
        (fx.source / "scratch").mkdir()
        (fx.source / "scratch" / "pec.json").write_text("{}\n", encoding="utf-8")
        fx.write_evidence({**_read(fx.evidence), "acceptance_evidence_refs": ["scratch/pec.json"]})
        with pytest.raises(packager.HandoffError, match="not a tracked file"):
            fx.package()
