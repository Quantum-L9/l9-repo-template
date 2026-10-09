"""Compiler-backed birth against the real pinned semantic compiler (BIRTH-ARCH-REVISION-001).

The acceptance property of the revision: a valid Node product with ZERO
Program Execution history — no IdeaOS receipt, no GAR decision, no Plan, no
campaign source, no PE receipt, no acceptance evidence — completes the
factory's local PREPARE gate, and every forgery the previous lineage contract
was supposed to catch is still refused: a tampered manifest, a stale topology,
an altered payload, the wrong factory identity, an unresolved semantic input, a
forged source coordinate, an engine that is not the pinned one.

Nothing here substitutes a dummy. The ProductManifest is produced by the actual
`Quantum-L9/l9-semantic-compiler-engine` at the revision
`scripts/birth-runner/semantic-compiler.pin.json` names, from a product whose
topology, repository-spec, workflow-spec and authority lock are the engine's own
seed contracts reshaped into a generic Node exactly as the engine's own
`tests/test_product.py` reshapes them (`_node_fixture` / `_target_fixture`).

Skip condition — real, narrow, documented, externally unavoidable: the engine
is a private repository that the factory does not vendor (the birth workflow
fetches it at the pin with read-only source authority; `uv sync --no-build`
cannot carry it as a dependency). Locate a clean checkout at the pinned
revision with `L9_SEMANTIC_COMPILER_SRC=<dir>`; by default the sibling
directory `../l9-semantic-compiler-engine` is tried. Set
`L9_REQUIRE_SEMANTIC_COMPILER=1` to turn an absent or unproven checkout into a
failure instead of a skip, which is what a runner that provisions the engine
should do. Everything the engine is NOT needed for — the adapter matrix, the
packager's refusals, the PREPARE gate order — is covered by the unit suites
without any skip.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
FACTORY_ORIGIN = "https://github.com/Quantum-L9/l9-repo-template.git"
GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


packager = _load("l9_birth_packager_compiler_it", BIRTH_RUNNER / "package_birth_handoff.py")
resolution = packager.product_resolution
adapter = packager.birth_adapter
new_repo = _load("l9_birth_new_repo_compiler_it", BIRTH_RUNNER / "new_repo.py")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *GIT_IDENTITY, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _commit_all(root: Path, message: str = "fixture") -> None:
    if not (root / ".git").is_dir():
        _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


# ─────────────────────────────────────────────────────────────────────────────
# The pinned engine: located, then proven, never assumed
# ─────────────────────────────────────────────────────────────────────────────


def _engine_root() -> Path:
    pin = resolution.load_pin(REPO)
    configured = os.environ.get("L9_SEMANTIC_COMPILER_SRC")
    candidate = (
        Path(configured).expanduser() if configured else REPO.parent / pin.repository.split("/")[1]
    )
    try:
        return resolution.prove_engine_checkout(candidate, pin)
    except resolution.ProductResolutionError as exc:
        reason = (
            f"pinned semantic compiler {pin.repository}@{pin.revision[:12]} is not available as "
            f"a clean checkout at {candidate} ({exc}); set L9_SEMANTIC_COMPILER_SRC"
        )
        if os.environ.get("L9_REQUIRE_SEMANTIC_COMPILER") == "1":
            raise pytest.fail.Exception(reason) from exc
        raise pytest.skip.Exception(reason) from exc


@pytest.fixture(scope="module")
def engine() -> Path:
    return _engine_root()


# ─────────────────────────────────────────────────────────────────────────────
# A valid Node product with zero PE history
# ─────────────────────────────────────────────────────────────────────────────

SEEDS = (
    "product-topology.yaml",
    "repository-spec.yaml",
    "workflow-spec.yaml",
    "semantics.lock.yaml",
)
CATALOGS = (
    "product_topology.schema.yaml",
    "product_kinds.yaml",
    "node_archetypes.yaml",
    "dependency_archetypes.yaml",
    "authority_model.yaml",
)
ASSURANCE_PROFILE = "authority/admitted/l9-assurance/semantic-compiler-core.profile.yaml"
CONTRACT_CATALOG = "contracts/compiler-core.yaml"
TARGET_IDS = ("urn:l9:fixture:ThingRequest:1.0", "urn:l9:fixture:ThingResult:1.0")
ARCHETYPE = "l9.node-archetype/worker@1"
PRODUCT_ID = "l9.fixture/generic-node"
PKG = "fixture_node"
LINEAGE_TOKENS = (
    "idea_execute",
    "gar_decision",
    "pe_receipt",
    "campaign_source",
    "lineage",
    "birth_contract",
)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _node_obligations(admitted: Path) -> tuple[dict, list[str], list[str]]:
    """Test material assembled from the admitted canonical catalogs (engine suite shape)."""
    kind = _yaml(admitted / "product_kinds.yaml")["kinds"]["node"]
    archetypes = {a["id"]: a for a in _yaml(admitted / "node_archetypes.yaml")["archetypes"]}
    patterns, classes, pending = set(kind["required_patterns"]), set(), [ARCHETYPE]
    while pending:
        archetype = archetypes[pending.pop()]
        patterns.update(archetype.get("requires", {}).get("architecture_patterns", []))
        classes.update(archetype.get("requires", {}).get("conformance_classes", []))
        pending.extend(archetype.get("extends", []))
    return kind, sorted(patterns), sorted(classes)


def _rebind_topology_digest(source: Path) -> None:
    repo = _yaml(source / "repository-spec.yaml")
    repo["product_binding"]["topology"]["digest"] = (
        "sha256:" + hashlib.sha256((source / "product-topology.yaml").read_bytes()).hexdigest()
    )
    _write_yaml(source / "repository-spec.yaml", repo)


def build_node_product(source: Path, engine_root: Path) -> None:
    """A generic, fully resolved Node product: the engine's seeds reshaped as its suite does.

    Carries no lineage of any kind. The only history it has is the one commit
    this function makes.
    """
    for rel in (*SEEDS, CONTRACT_CATALOG, ASSURANCE_PROFILE):
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(engine_root / rel, target)
    admitted = source / "authority" / "admitted" / ".github"
    admitted.mkdir(parents=True)
    for name in CATALOGS:
        shutil.copyfile(engine_root / "authority" / "admitted" / ".github" / name, admitted / name)
    (source / "src" / PKG).mkdir(parents=True)
    (source / "src" / PKG / "__init__.py").write_text('"""Fixture node."""\n', encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "README.md").write_text("# fixture tests\n", encoding="utf-8")
    (source / "README.md").write_text("# Fixture node\n", encoding="utf-8")
    schemas = source / "contracts" / "schemas"
    schemas.mkdir(parents=True)
    for identity in TARGET_IDS:
        document = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": identity,
            "type": "object",
        }
        (schemas / (identity.split(":")[3] + ".schema.json")).write_text(
            json.dumps(document, sort_keys=True), encoding="utf-8"
        )

    kind, patterns, classes = _node_obligations(admitted)
    topology = _yaml(source / "product-topology.yaml")
    topology["product"].update(id=PRODUCT_ID, kind="node", archetype_ref=ARCHETYPE)
    topology["identity"]["dimensions"] = {
        dimension.removesuffix("_identity"): {"identity_ref": f"l9.fixture/{dimension}"}
        for dimension in kind["identity_dimensions"]
    }
    topology["consumption"]["model"] = kind["consumption_model"]
    topology["consumption"]["forbidden_consumption_modes"] = [
        mode
        for mode in topology["consumption"]["forbidden_consumption_modes"]
        if mode != f"{kind['consumption_model']}_as_canonical_consumption"
    ]
    topology["deployment"].update(
        model=kind["deployment_model"],
        deployment_unit="fixture_runtime",
        runtime_boundary="fixture_node_process",
        scaling_boundary="node_owned",
        failure_boundary="node_owned",
        upgrade_boundary="fixture_release_binding",
        deployment_constraints=["fixture node owns its runtime lifecycle"],
    )
    topology["runtime"] = {
        "participation_model": "fixture_node_runtime",
        "process_model": "fixture_node_process",
        "concurrency_model": "fixture_node_owned",
        "resource_model": "fixture_node_owned",
    }
    topology["communication"]["constellation_boundary_required"] = True
    topology["architecture"]["required_pattern_refs"] = patterns
    topology["conformance"] = {
        "profile_refs": [],
        "required_classes": classes,
        "final_conformance_required": True,
    }
    topology["state"] = {
        "owns_authoritative_state": True,
        "state_semantic_refs": ["l9.fixture.state/revisioned@1"],
        "cache_authority": "none",
    }
    topology["capabilities"]["provides"][0]["contract_refs"] = list(TARGET_IDS)
    topology["ports"] = {"inbound": [], "outbound": []}
    topology["adapters"] = {"inbound": [], "outbound": []}
    topology["providers"]["allowed"] = [
        {"provider": "fixture-provider", "semantic_authority": "none"}
    ]
    _write_yaml(source / "product-topology.yaml", topology)

    repo = _yaml(source / "repository-spec.yaml")
    repo["source_surfaces"]["authoritative"].pop("compiler_domain")
    repo["source_surfaces"]["authoritative"]["target_domain"] = [
        {"path": "contracts/schemas/", "semantic_role": "fixture_public_contract_schemas"}
    ]
    repo["repository_structure"].pop("compiler_domain_ledgers")
    _write_yaml(source / "repository-spec.yaml", repo)

    lock = _yaml(source / "semantics.lock.yaml")
    lock.pop("resolved_product_closure")
    _write_yaml(source / "semantics.lock.yaml", lock)
    _rebind_topology_digest(source)
    _commit_all(source, "fixture node product — no lineage")


class Fixture:
    """A clean Node source, a clean fixture factory, the real engine, an output dir."""

    def __init__(self, root: Path, engine_root: Path) -> None:
        self.root = root
        self.engine = engine_root
        self.source = root / "source"
        self.factory = root / "factory"
        self.out = root / "out"
        build_node_product(self.source, engine_root)
        self.revision = _git(self.source, "rev-parse", "HEAD")
        self.tree = _git(self.source, "rev-parse", "HEAD^{tree}")
        self._make_factory()
        self.manifest_ref = f"l9.product-manifest/{PKG}@1"

    def _make_factory(self) -> None:
        for rel in (
            "scripts/birth-runner/payload-ownership.yaml",
            "scripts/birth-runner/semantic-compiler.pin.json",
            "scripts/birth-runner/compile_birth_payload.py",
            "scripts/birth-runner/new_repo.py",
        ):
            target = self.factory / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, target)
        _commit_all(self.factory)
        _git(self.factory, "remote", "add", "origin", FACTORY_ORIGIN)
        self.factory_revision = _git(self.factory, "rev-parse", "HEAD")

    def package(self, **overrides: object) -> dict[str, object]:
        args: dict[str, object] = {
            "source": self.source,
            "semantic_compiler_src": self.engine,
            "manifest_ref": self.manifest_ref,
            "out_dir": self.out,
            "source_repository": "Quantum-L9/fixture-node",
            "factory_root": self.factory,
        }
        args.update(overrides)
        return packager.package(**args)  # type: ignore[arg-type]

    def prepare_config(self, result: dict[str, object], **overrides: object) -> object:
        cfg = new_repo.BirthConfig(
            org="Quantum-L9",
            repo="fixture-node",
            pkg=PKG,
            desc="Fixture node",
            work_dir=self.root / "work",
            payload=self.source,
            payload_contract=Path(str(result["payload"])),
            template_src=self.factory,
            org_profile_src=None,
            repo_class="non_constellation_python",
            remote=False,
            private=False,
            keep=False,
            receipt_path=None,
            bootstrap_timeout=1,
            product_birth_binding=Path(str(result["binding"])),
            product_manifest=Path(str(result["manifest"])),
            semantic_compiler_src=self.engine,
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

    def receipt(self, cfg: object, *, template_sha: str | None = None) -> object:
        receipt = new_repo.BirthReceipt(template_sha=template_sha or self.factory_revision)
        # As `_preflight_payload_contract` leaves it once the payload reproduced.
        receipt.payload_contract = str(cfg.payload_contract)  # type: ignore[attr-defined]
        return receipt


@pytest.fixture
def fx(tmp_path: Path, engine: Path) -> Fixture:
    return Fixture(tmp_path, engine)


def _read(path: object) -> dict[str, object]:
    return json.loads(Path(str(path)).read_text(encoding="utf-8"))


def _rewrite(path: Path, document: dict[str, object]) -> None:
    path.write_text(adapter.render_document(document), encoding="utf-8")


def _gate(fx: Fixture, cfg: object, receipt: object) -> None:
    new_repo._stages._preflight_product_birth_adapter(cfg, receipt)


# ─────────────────────────────────────────────────────────────────────────────
# Accept: a Node product with no PE history
# ─────────────────────────────────────────────────────────────────────────────


class TestANodeProductWithZeroPEHistoryIsBorn:
    def test_the_source_carries_no_lineage(self, fx: Fixture) -> None:
        tracked = _git(fx.source, "ls-files").splitlines()
        assert len(_git(fx.source, "rev-list", "HEAD").splitlines()) == 1
        for rel in tracked:
            assert not any(token in rel.lower() for token in LINEAGE_TOKENS), rel

    def test_the_pinned_engine_resolves_it(self, fx: Fixture) -> None:
        result = fx.package()
        assert result["status"] == "PASS"
        manifest = _read(result["manifest"])
        assert manifest["schema"] == "l9.product-manifest/v1"
        assert manifest["product"] == {"id": PRODUCT_ID, "kind": "node", "archetype_ref": ARCHETYPE}
        assert manifest["unresolved"] == []
        assert all(manifest["resolved_manifest_gate"].values())
        assert manifest["compiler"]["compiler_version"] == resolution.load_pin(REPO).version
        assert sorted(p.name for p in fx.out.iterdir()) == [
            "birth-payload.json",
            "product-birth-binding.json",
            "product-manifest.json",
        ]

    def test_the_bundle_binds_the_pinned_engine_and_nothing_else(self, fx: Fixture) -> None:
        result = fx.package()
        binding = _read(result["binding"])
        pin = resolution.load_pin(REPO)
        assert binding["schema"] == "l9.product-birth-binding/v2"
        assert binding["compiler"] == {
            **pin.coordinate,
            "inputs": packager.DEFAULT_INPUTS,
        }
        assert binding["source"] == {
            "repository": "Quantum-L9/fixture-node",
            "revision": fx.revision,
            "tree_sha": fx.tree,
        }
        assert "birth_contract" not in binding
        text = "\n".join(
            Path(str(result[key])).read_text() for key in ("binding", "manifest", "payload")
        )
        for token in (
            "l9.repo-birth-contract",
            "repo-birth-evidence",
            "pe_receipt",
            "gar_decision",
        ):
            assert token not in text

    def test_local_prepare_admits_it(self, fx: Fixture) -> None:
        result = fx.package()
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        _gate(fx, cfg, receipt)
        stage = receipt.stages[-1]  # type: ignore[attr-defined]
        assert stage.key == "preflight.adapter"
        assert stage.status == "PASS"
        assert resolution.load_pin(REPO).revision[:12] in stage.detail
        assert _git(fx.source, "status", "--porcelain") == ""

    def test_the_manifest_is_the_engines_output_untouched(self, fx: Fixture) -> None:
        result = fx.package()
        pin = resolution.load_pin(REPO)
        reproduced = resolution.reproduce_manifest(
            engine_root=fx.engine,
            pin=pin,
            source_root=fx.source,
            inputs=packager.DEFAULT_INPUTS,
        )
        assert reproduced.resolved
        assert reproduced.manifest == _read(result["manifest"])

    def test_packaging_is_deterministic(self, fx: Fixture) -> None:
        first = fx.package()
        bytes_first = {p.name: p.read_bytes() for p in fx.out.iterdir()}
        second = fx.package()
        assert first == second
        assert {p.name: p.read_bytes() for p in fx.out.iterdir()} == bytes_first


# ─────────────────────────────────────────────────────────────────────────────
# Refuse: every forgery the retired lineage contract used to stand in front of
# ─────────────────────────────────────────────────────────────────────────────


class TestForgeriesFailClosed:
    def test_a_tampered_manifest_body_is_refused_by_reproduction(self, fx: Fixture) -> None:
        """Digest left as declared, body edited: the adapter cannot see it, the engine can."""
        result = fx.package()
        manifest = _read(result["manifest"])
        manifest["capabilities"]["provides"][0]["contract_refs"] = ["urn:l9:fixture:Forged:1.0"]
        _rewrite(Path(str(result["manifest"])), manifest)
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="document disagreement"):
            _gate(fx, cfg, receipt)

    def test_a_tampered_manifest_digest_is_refused(self, fx: Fixture) -> None:
        """Binding and manifest agree with each other, not with the engine."""
        result = fx.package()
        forged = "sha256:" + "9" * 64
        manifest = _read(result["manifest"])
        manifest["manifest_digest"] = forged
        _rewrite(Path(str(result["manifest"])), manifest)
        binding = _read(result["binding"])
        binding["manifest"]["digest"] = forged
        _rewrite(Path(str(result["binding"])), binding)
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="digest disagreement"):
            _gate(fx, cfg, receipt)

    def test_a_stale_topology_is_refused(self, fx: Fixture) -> None:
        """The product moved after packaging; the manifest the bundle carries is stale."""
        result = fx.package()
        topology = _yaml(fx.source / "product-topology.yaml")
        topology["purpose"]["statement"] += " (moved)"
        _write_yaml(fx.source / "product-topology.yaml", topology)
        _rebind_topology_digest(fx.source)
        _commit_all(fx.source, "topology moved")
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="product resolution did not reproduce"):
            _gate(fx, cfg, receipt)

    def test_an_altered_payload_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        payload = _read(result["payload"])
        payload["files"][0]["sha256"] = "0" * 64
        _rewrite(Path(str(result["payload"])), payload)
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="PAYLOAD_DIGEST_MISMATCH"):
            _gate(fx, cfg, receipt)

    def test_the_wrong_factory_identity_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg, template_sha="0" * 40)
        with pytest.raises(new_repo.BirthError, match="running factory revision"):
            _gate(fx, cfg, receipt)

    def test_an_unresolved_semantic_input_is_refused_at_packaging(self, fx: Fixture) -> None:
        topology = _yaml(fx.source / "product-topology.yaml")
        topology["capabilities"]["provides"][0]["contract_refs"] = [
            "l9.fixture.contract/invented@1"
        ]
        _write_yaml(fx.source / "product-topology.yaml", topology)
        _rebind_topology_digest(fx.source)
        _commit_all(fx.source, "unresolvable capability")
        with pytest.raises(packager.HandoffError, match="unresolved"):
            fx.package()
        assert not fx.out.exists() or list(fx.out.iterdir()) == []

    def test_a_forged_source_coordinate_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        binding = _read(result["binding"])
        binding["source"]["revision"] = "f" * 40
        _rewrite(Path(str(result["binding"])), binding)
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="PAYLOAD_SOURCE_MISMATCH"):
            _gate(fx, cfg, receipt)

    def test_an_engine_that_is_not_the_pin_is_refused(self, fx: Fixture, tmp_path: Path) -> None:
        other = tmp_path / "other-engine"
        subprocess.run(["git", "clone", "-q", str(fx.engine), str(other)], check=True)
        _git(
            other,
            "remote",
            "set-url",
            "origin",
            f"https://github.com/{resolution.load_pin(REPO).repository}.git",
        )
        _git(other, "commit", "-q", "--allow-empty", "-m", "one commit past the pin")
        result = fx.package()
        cfg = fx.prepare_config(result, semantic_compiler_src=other)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="the factory pins"):
            _gate(fx, cfg, receipt)

    def test_a_dirty_engine_checkout_is_refused(self, fx: Fixture, tmp_path: Path) -> None:
        other = tmp_path / "dirty-engine"
        subprocess.run(["git", "clone", "-q", str(fx.engine), str(other)], check=True)
        _git(
            other,
            "remote",
            "set-url",
            "origin",
            f"https://github.com/{resolution.load_pin(REPO).repository}.git",
        )
        (other / "src" / "l9_semantic_compiler" / "cli.py").write_text(
            "# patched\n", encoding="utf-8"
        )
        result = fx.package()
        cfg = fx.prepare_config(result, semantic_compiler_src=other)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="dirty"):
            _gate(fx, cfg, receipt)

    def test_a_binding_naming_another_engine_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        binding = _read(result["binding"])
        binding["compiler"]["revision"] = "e" * 40
        _rewrite(Path(str(result["binding"])), binding)
        cfg = fx.prepare_config(result)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="the factory pins"):
            _gate(fx, cfg, receipt)

    def test_without_the_engine_the_gate_refuses_rather_than_trusting(self, fx: Fixture) -> None:
        result = fx.package()
        cfg = fx.prepare_config(result, semantic_compiler_src=None)
        receipt = fx.receipt(cfg)
        with pytest.raises(new_repo.BirthError, match="pinned semantic compiler"):
            _gate(fx, cfg, receipt)
