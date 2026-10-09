"""The factory-owned repository-birth packager (compiler-backed, v2).

`package_birth_handoff.py` turns a verified source snapshot into the three
artifacts a compiler-backed birth carries: the compiled `l9.birth-payload/v1`,
the `l9.product-manifest/v1` the pinned semantic compiler resolves from that
snapshot, and the `l9.product-birth-binding/v2`. It owns packaging only. The
payload compiler compiles bytes, the pinned engine compiles semantics, the
adapter decides.

BIRTH-ARCH-REVISION-001: the `l9.repo-birth-evidence/v1` lineage input and the
emitted `l9.repo-birth-contract/v1` are gone. Nothing here constructs an
IdeaOS receipt, a GAR decision, a Plan, a campaign source or a PE receipt,
because the packager no longer has a slot to put one in.

The engine seam. `package()` resolves the manifest through
`resolve_manifest` → `product_resolution`. The real engine is exercised by
`tests/integration/test_compiler_backed_birth.py`; this suite replaces that one
seam with the adapter fixture manifest so the packaging mechanics — factory
identity, output isolation, transactional emission, the binding's provenance,
the adapter's self-proof — are proven without a private checkout. The seam is
the engine's OUTPUT, never a receipt standing in for evidence the factory would
otherwise verify: every integrity gate below (clean source, clean factory,
adapter admission, digest binding) still runs for real.
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
BINDING_SCHEMA = BIRTH_RUNNER / "schemas" / "l9-product-birth-binding.schema.json"
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
resolution = packager.product_resolution
# The adapter suite owns the ProductManifest fixture; one reading of its shape.
adapter_fixtures = _load(
    "l9_birth_adapter_fixtures_for_packager", REPO / "tests" / "unit" / "test_l9_birth_adapter.py"
)
new_repo = _load("l9_birth_new_repo_for_packager", BIRTH_RUNNER / "new_repo.py")
# The fixture below replaces `packager.resolve_manifest`; the seam tests drive the real one.
real_resolve_manifest = packager.resolve_manifest

GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")
INPUT_FILES = tuple(packager.DEFAULT_INPUTS.values())


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


class Fixture:
    """A clean source carrying its engine inputs, a clean fixture factory, a stubbed engine."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.source = root / "source"
        self.factory = root / "factory"
        self.engine = root / "engine-checkout-not-opened-by-this-suite"
        self.out = root / "out"
        self._make_source()
        self._make_factory()
        self.manifest_doc = adapter_fixtures.make_manifest()
        self.manifest_ref = "l9.product-manifest/ideaos@1"
        self.engine_calls: list[dict[str, object]] = []
        monkeypatch.setattr(packager, "resolve_manifest", self._resolve)

    def _resolve(self, **kwargs: object) -> dict[str, object]:
        self.engine_calls.append(dict(kwargs))
        return json.loads(json.dumps(self.manifest_doc))

    def _make_source(self) -> None:
        (self.source / "src" / "ideaos").mkdir(parents=True)
        (self.source / "src" / "ideaos" / "__init__.py").write_text("", encoding="utf-8")
        (self.source / "README.md").write_text("# Fixture\n", encoding="utf-8")
        for rel in INPUT_FILES:
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {rel}\n", encoding="utf-8")
        _commit_all(self.source)
        self.revision = _git(self.source, "rev-parse", "HEAD")
        self.tree = _git(self.source, "rev-parse", "HEAD^{tree}")

    def _make_factory(self) -> None:
        """The factory surfaces the packager and compiler read, at one clean commit."""
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

    def set_manifest(self, document: dict[str, object]) -> None:
        self.manifest_doc = document

    def package(self, **overrides: object) -> dict[str, object]:
        args: dict[str, object] = {
            "source": self.source,
            "semantic_compiler_src": self.engine,
            "manifest_ref": self.manifest_ref,
            "out_dir": self.out,
            "source_repository": "Quantum-L9/IdeaOS",
            "factory_root": self.factory,
        }
        args.update(overrides)
        return packager.package(**args)  # type: ignore[arg-type]


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fixture:
    return Fixture(tmp_path, monkeypatch)


def _read(path: object) -> dict[str, object]:
    return json.loads(Path(str(path)).read_text(encoding="utf-8"))


def _outputs(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir()) if out.exists() else []


BUNDLE = ["birth-payload.json", "product-birth-binding.json", "product-manifest.json"]


# ─────────────────────────────────────────────────────────────────────────────
# A complete, consistent package
# ─────────────────────────────────────────────────────────────────────────────


class TestACompletePackage:
    def test_it_is_adapter_admissible(self, fx: Fixture) -> None:
        result = fx.package()
        assert result["status"] == "PASS"
        assert _outputs(fx.out) == BUNDLE
        verdict = adapter.bind(
            adapter.load_binding(Path(str(result["binding"]))),
            manifest=adapter.load_artifact(Path(str(result["manifest"]))),
            payload=adapter.load_artifact(Path(str(result["payload"]))),
        )
        assert verdict.admissible, verdict.failures

    def test_the_binding_carries_only_proven_coordinates(self, fx: Fixture) -> None:
        result = fx.package()
        binding = _read(result["binding"])
        pin = resolution.load_pin(REPO)
        product = fx.manifest_doc["product"]
        assert isinstance(product, dict)
        assert binding["schema"] == "l9.product-birth-binding/v2"
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
        assert binding["payload"] == {
            "ref": str(result["payload"]),
            "digest": _digest(Path(str(result["payload"]))),
        }
        assert binding["factory"] == {
            "repository": "Quantum-L9/l9-repo-template",
            "revision": fx.factory_revision,
        }
        assert binding["compiler"] == {**pin.coordinate, "inputs": packager.DEFAULT_INPUTS}
        assert "birth_contract" not in binding
        assert (
            list(Draft202012Validator(json.loads(BINDING_SCHEMA.read_text())).iter_errors(binding))
            == []
        )

    def test_the_engine_is_asked_for_exactly_the_snapshot_and_inputs(self, fx: Fixture) -> None:
        fx.package()
        (call,) = fx.engine_calls
        assert call["engine_root"] == fx.engine.resolve()
        assert call["source"] == fx.source.resolve()
        assert call["inputs"] == packager.DEFAULT_INPUTS
        assert call["factory_root"] == fx.factory.resolve()

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

    def test_the_manifest_is_the_engines_output_in_the_factory_rendering(self, fx: Fixture) -> None:
        result = fx.package()
        assert Path(str(result["manifest"])).read_text(encoding="utf-8") == (
            packager.compiler.render_payload(fx.manifest_doc)
        )

    def test_emission_is_deterministic(self, fx: Fixture) -> None:
        first = fx.package()
        before = {name: (fx.out / name).read_bytes() for name in _outputs(fx.out)}
        second = fx.package()
        assert first == second
        assert {name: (fx.out / name).read_bytes() for name in _outputs(fx.out)} == before

    def test_the_source_repository_override_is_honored(self, fx: Fixture) -> None:
        result = fx.package(source_repository="Quantum-L9/IdeaOS-renamed")
        assert _read(result["binding"])["source"]["repository"] == "Quantum-L9/IdeaOS-renamed"
        assert _read(result["payload"])["source"]["repository"] == "Quantum-L9/IdeaOS-renamed"

    def test_explicit_inputs_are_carried_and_handed_to_the_engine(self, fx: Fixture) -> None:
        (fx.source / "semantics" / "lock.yaml").parent.mkdir()
        (fx.source / "semantics" / "lock.yaml").write_text("# lock\n", encoding="utf-8")
        _git(fx.source, "add", "-A")
        _git(fx.source, "commit", "-q", "-m", "moved lock")
        result = fx.package(inputs={"authority_lock": "semantics/lock.yaml"})
        binding = _read(result["binding"])
        assert binding["compiler"]["inputs"]["authority_lock"] == "semantics/lock.yaml"
        assert fx.engine_calls[0]["inputs"] == {
            **packager.DEFAULT_INPUTS,
            "authority_lock": "semantics/lock.yaml",
        }


# ─────────────────────────────────────────────────────────────────────────────
# ProductManifest: resolved by the engine, never produced or defaulted here
# ─────────────────────────────────────────────────────────────────────────────


class TestTheProductManifestIsResolvedNeverAuthored:
    @pytest.mark.parametrize("ref", ["", "   ", " padded", "two\nlines"])
    def test_a_missing_or_unusable_ref_is_refused_not_inferred(self, fx: Fixture, ref: str) -> None:
        with pytest.raises(packager.HandoffError, match="ProductManifest ref"):
            fx.package(manifest_ref=ref)
        assert _outputs(fx.out) == []
        assert fx.engine_calls == []

    def test_the_ref_is_carried_verbatim(self, fx: Fixture) -> None:
        """Not derived from product id, repository, topology, filename or kind."""
        result = fx.package(manifest_ref="l9.product-manifest/anything-the-owner-says@7")
        assert _read(result["binding"])["manifest"]["ref"] == (
            "l9.product-manifest/anything-the-owner-says@7"
        )

    def test_the_cli_requires_the_ref_and_the_engine(self, fx: Fixture) -> None:
        for argv in (
            [
                "--source",
                str(fx.source),
                "--semantic-compiler-src",
                str(fx.engine),
                "--out-dir",
                str(fx.out),
            ],
            [
                "--source",
                str(fx.source),
                "--manifest-ref",
                fx.manifest_ref,
                "--out-dir",
                str(fx.out),
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                packager.parse_args(argv)
            assert exc.value.code == 2

    @pytest.mark.parametrize("flag", ["--factory", "--evidence", "--manifest", "--operation"])
    def test_retired_and_foreign_flags_are_gone(self, flag: str) -> None:
        with pytest.raises(SystemExit):
            packager.parse_args([flag, "/elsewhere"])

    @pytest.mark.parametrize("kind", ["node", "library"])
    def test_product_kind_is_read_from_the_manifest(self, fx: Fixture, kind: str) -> None:
        product = {"id": "l9.product/ideaos", "kind": kind, "archetype_ref": "l9.archetype/x@1"}
        fx.set_manifest(adapter_fixtures.make_manifest(product=product))
        result = fx.package()
        assert _read(result["binding"])["product"]["kind"] == kind

    @pytest.mark.parametrize("drop", ["id", "kind"])
    def test_a_manifest_without_product_coordinates_is_refused_not_filled_in(
        self, fx: Fixture, drop: str
    ) -> None:
        product = {"id": "l9.product/ideaos", "kind": "node", "archetype_ref": "l9.archetype/x@1"}
        del product[drop]
        fx.set_manifest(adapter_fixtures.make_manifest(product=product))
        with pytest.raises(packager.HandoffError, match=f"product.{drop}"):
            fx.package()
        assert _outputs(fx.out) == []

    def test_an_unresolved_manifest_is_refused_by_the_existing_adapter(self, fx: Fixture) -> None:
        fx.set_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
        with pytest.raises(packager.HandoffError, match="MANIFEST_UNRESOLVED"):
            fx.package()
        assert _outputs(fx.out) == [], "a refused bundle leaves nothing behind"

    def test_a_manifest_from_another_compiler_version_is_refused(self, fx: Fixture) -> None:
        """The binding names the factory's pin; a manifest another engine resolved cannot bind."""
        fx.set_manifest(
            adapter_fixtures.make_manifest(
                compiler={"profile_ref": "p", "profile_digest": "d", "compiler_version": "0.0.1"}
            )
        )
        with pytest.raises(packager.HandoffError, match="COMPILER_COORDINATE_MISMATCH"):
            fx.package()
        assert _outputs(fx.out) == []


class TestTheEngineSeam:
    """`resolve_manifest` itself, driven against the product-resolution module."""

    def _reproduction(self, *, exit_code: int, unresolved: list[object]) -> object:
        manifest = adapter_fixtures.make_manifest(unresolved=unresolved)
        return resolution.Reproduction(manifest=manifest, exit_code=exit_code)

    def test_an_unresolved_product_is_refused_at_packaging(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resolution, "prove_engine_checkout", lambda root, pin: root)
        monkeypatch.setattr(
            resolution,
            "reproduce_manifest",
            lambda **kw: self._reproduction(exit_code=2, unresolved=["resolved_manifest_gate:x"]),
        )
        with pytest.raises(packager.HandoffError, match="unresolved"):
            real_resolve_manifest(
                engine_root=fx.engine,
                source=fx.source,
                inputs=packager.DEFAULT_INPUTS,
                factory_root=fx.factory,
            )

    def test_a_nonzero_engine_exit_is_refused_even_with_an_empty_list(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resolution, "prove_engine_checkout", lambda root, pin: root)
        monkeypatch.setattr(
            resolution,
            "reproduce_manifest",
            lambda **kw: self._reproduction(exit_code=2, unresolved=[]),
        )
        with pytest.raises(packager.HandoffError, match="unresolved"):
            real_resolve_manifest(
                engine_root=fx.engine,
                source=fx.source,
                inputs=packager.DEFAULT_INPUTS,
                factory_root=fx.factory,
            )

    def test_an_unproven_engine_is_refused_before_it_runs(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ran: list[object] = []
        monkeypatch.setattr(resolution, "reproduce_manifest", lambda **kw: ran.append(kw))
        with pytest.raises(packager.HandoffError, match="semantic compiler did not resolve"):
            real_resolve_manifest(
                engine_root=fx.engine,
                source=fx.source,
                inputs=packager.DEFAULT_INPUTS,
                factory_root=fx.factory,
            )
        assert ran == []

    def test_a_resolved_product_hands_back_the_engines_manifest(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resolution, "prove_engine_checkout", lambda root, pin: root)
        monkeypatch.setattr(
            resolution,
            "reproduce_manifest",
            lambda **kw: self._reproduction(exit_code=0, unresolved=[]),
        )
        manifest = real_resolve_manifest(
            engine_root=fx.engine,
            source=fx.source,
            inputs=packager.DEFAULT_INPUTS,
            factory_root=fx.factory,
        )
        assert manifest == adapter_fixtures.make_manifest()


# ─────────────────────────────────────────────────────────────────────────────
# Source and inputs
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceAndInputs:
    def test_a_dirty_source_is_refused(self, fx: Fixture) -> None:
        (fx.source / "dirty.txt").write_text("drift\n", encoding="utf-8")
        with pytest.raises(packager.HandoffError, match="dirty"):
            fx.package()
        assert _outputs(fx.out) == []

    def test_an_input_the_snapshot_does_not_carry_is_refused_by_the_adapter(
        self, fx: Fixture
    ) -> None:
        with pytest.raises(packager.HandoffError, match="COMPILER_INPUT_NOT_IN_PAYLOAD"):
            fx.package(inputs={"topology": "elsewhere/topology.yaml"})
        assert _outputs(fx.out) == []

    @pytest.mark.parametrize("value", ["/abs/topology.yaml", "../topology.yaml", "", "./x.yaml"])
    def test_an_unusable_input_path_is_refused_before_anything_runs(
        self, fx: Fixture, value: str
    ) -> None:
        with pytest.raises(packager.HandoffError, match="repository-relative"):
            fx.package(inputs={"topology": value})
        assert fx.engine_calls == []

    def test_an_unknown_input_key_is_refused(self, fx: Fixture) -> None:
        with pytest.raises(packager.HandoffError, match="unknown compiler input"):
            fx.package(inputs={"lineage": "lineage/pe-receipt.json"})

    def test_no_lineage_is_read_written_or_required(self, fx: Fixture) -> None:
        """The whole point of the revision: a packaging with zero PE history passes,
        and nothing in the bundle names a lineage artifact."""
        result = fx.package()
        tracked = _git(fx.source, "ls-files").splitlines()
        assert not [p for p in tracked if "lineage" in p or "receipt" in p]
        documents = {k: _read(result[k]) for k in ("binding", "manifest", "payload")}
        documents["binding"]["payload"].pop("ref")  # a filesystem path, not a coordinate
        text = json.dumps(documents)
        for token in (
            "lineage",
            "pe_receipt",
            "gar_decision",
            "idea_execute",
            "campaign_source",
            "birth_contract",
        ):
            assert token not in text


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

    def test_the_pin_is_read_from_the_factory_not_the_running_checkout(self, fx: Fixture) -> None:
        pin_path = fx.factory / "scripts" / "birth-runner" / "semantic-compiler.pin.json"
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        pin["revision"] = "f" * 40
        pin_path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        _git(fx.factory, "add", "-A")
        _git(fx.factory, "commit", "-q", "-m", "moved pin")
        result = fx.package()
        assert _read(result["binding"])["compiler"]["revision"] == "f" * 40


# ─────────────────────────────────────────────────────────────────────────────
# Self-proof: the existing adapter decides, and refuses every inconsistency
# ─────────────────────────────────────────────────────────────────────────────


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


def _edit_json(path: Path, dotted: str, value: object) -> None:
    path.write_text(
        packager.compiler.render_payload(_mutate(_read(path), dotted, value)), encoding="utf-8"
    )


class TestTheSelfProof:
    def _prove(self, result: dict[str, object]) -> object:
        return packager.prove_bundle(
            binding=Path(str(result["binding"])),
            manifest=Path(str(result["manifest"])),
            payload=Path(str(result["payload"])),
        )

    def test_the_emitted_bundle_proves(self, fx: Fixture) -> None:
        assert self._prove(fx.package()).admissible

    @pytest.mark.parametrize(
        ("dotted", "value", "code"),
        [
            ("manifest.digest", "sha256:" + "9" * 64, "MANIFEST_DIGEST_MISMATCH"),
            ("topology.digest", "sha256:" + "8" * 64, "TOPOLOGY_COORDINATE_MISMATCH"),
            ("source.revision", "f" * 40, "PAYLOAD_SOURCE_MISMATCH"),
            ("payload.digest", "sha256:" + "7" * 64, "PAYLOAD_DIGEST_MISMATCH"),
            ("compiler.version", "0.0.0", "COMPILER_COORDINATE_MISMATCH"),
            ("compiler.inputs.topology", "elsewhere.yaml", "COMPILER_INPUT_NOT_IN_PAYLOAD"),
        ],
    )
    def test_a_mismatched_binding_is_refused(
        self, fx: Fixture, dotted: str, value: str, code: str
    ) -> None:
        result = fx.package()
        _edit_json(Path(str(result["binding"])), dotted, value)
        with pytest.raises(packager.HandoffError, match=code):
            self._prove(result)

    def test_a_changed_payload_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        _edit_json(Path(str(result["payload"])), "mode", "authoritative")
        with pytest.raises(packager.HandoffError, match="PAYLOAD_DIGEST_MISMATCH"):
            self._prove(result)

    def test_a_changed_manifest_digest_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        _edit_json(Path(str(result["manifest"])), "manifest_digest", "sha256:" + "6" * 64)
        with pytest.raises(packager.HandoffError, match="MANIFEST_DIGEST_MISMATCH"):
            self._prove(result)

    def test_a_birth_contract_smuggled_into_the_binding_is_refused(self, fx: Fixture) -> None:
        result = fx.package()
        _edit_json(
            Path(str(result["binding"])),
            "birth_contract",
            {"ref": "x", "digest": "sha256:" + "0" * 64},
        )
        with pytest.raises(packager.HandoffError, match="BINDING_MALFORMED"):
            self._prove(result)


# ─────────────────────────────────────────────────────────────────────────────
# The packaged bundle meets the PREPARE gate
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
            product_manifest=Path(str(result["manifest"])),
            semantic_compiler_src=fx.engine,
        )

    def _receipt(self, cfg: object, template_sha: str) -> object:
        receipt = new_repo.BirthReceipt(template_sha=template_sha)
        # As `_preflight_payload_contract` leaves it once the payload reproduced.
        receipt.payload_contract = str(cfg.payload_contract)  # type: ignore[attr-defined]
        return receipt

    def _resolved(self, monkeypatch: pytest.MonkeyPatch, fx: Fixture) -> list[dict[str, object]]:
        """PREPARE's own reproduction seam: the real engine is the integration suite's."""
        calls: list[dict[str, object]] = []

        def resolve_product(**kwargs: object) -> object:
            calls.append(dict(kwargs))
            pin = resolution.load_pin(fx.factory)
            return resolution.Resolution(
                engine=pin.coordinate,
                manifest_digest=str(fx.manifest_doc["manifest_digest"]),
                inputs=dict(packager.DEFAULT_INPUTS),
            )

        monkeypatch.setattr(new_repo._stages.product_resolution, "resolve_product", resolve_product)
        return calls

    def test_a_package_from_the_running_factory_is_admitted(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = fx.package()
        cfg = self._cfg(fx, result)
        receipt = self._receipt(cfg, fx.factory_revision)
        calls = self._resolved(monkeypatch, fx)
        new_repo._stages._preflight_product_birth_adapter(cfg, receipt)
        assert receipt.stages[-1].key == "preflight.adapter"
        assert receipt.stages[-1].status == "PASS"
        (call,) = calls
        assert call["engine_root"] == fx.engine
        assert call["source_root"] == fx.source
        assert call["supplied_manifest"] == fx.manifest_doc
        assert call["claimed_compiler"] == _read(result["binding"])["compiler"]
        assert call["factory_root"] == fx.factory

    def test_a_package_from_another_factory_revision_is_still_refused(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = fx.package()
        cfg = self._cfg(fx, result)
        receipt = self._receipt(cfg, "0" * 40)
        calls = self._resolved(monkeypatch, fx)
        with pytest.raises(new_repo.BirthError, match="running factory revision"):
            new_repo._stages._preflight_product_birth_adapter(cfg, receipt)
        assert calls == [], "the engine never runs for a bundle bound to another factory"


def test_the_cli_reports_a_refusal_and_exits_nonzero(
    fx: Fixture, capsys: pytest.CaptureFixture[str]
) -> None:
    code = packager.main(
        [
            "--source",
            str(fx.root / "absent-source"),
            "--semantic-compiler-src",
            str(fx.engine),
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
        fx.set_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
        with pytest.raises(packager.HandoffError, match="MANIFEST_UNRESOLVED"):
            fx.package()
        assert _state(fx.out) == before

    @pytest.mark.parametrize("refusal", ["manifest_ref", "dirty_source", "engine"])
    def test_an_early_refusal_cannot_make_a_stale_bundle_look_new(
        self, fx: Fixture, refusal: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fx.package()
        before = _state(fx.out)
        overrides: dict[str, object] = {}
        if refusal == "manifest_ref":
            overrides["manifest_ref"] = ""
        elif refusal == "dirty_source":
            (fx.source / "dirty.txt").write_text("drift\n", encoding="utf-8")
        else:

            def refuse(**kwargs: object) -> object:
                raise packager.HandoffError(
                    "semantic compiler did not resolve the product: refused"
                )

            monkeypatch.setattr(packager, "resolve_manifest", refuse)
        with pytest.raises(packager.HandoffError):
            fx.package(**overrides)
        assert _state(fx.out) == before

    def test_a_failure_while_exposing_never_leaves_a_mixed_bundle(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The second file's exposure fails after the first moved: everything rolls back."""
        fx.package()
        before = _state(fx.out)
        real_replace = Path.replace

        def failing_replace(self: Path, target: object) -> Path:
            if Path(str(target)).name == "product-manifest.json" and self.parent != fx.out:
                raise OSError("simulated failure exposing the manifest")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", failing_replace)
        fx.set_manifest(
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
        fx.set_manifest(adapter_fixtures.make_manifest(unresolved=[{"id": "gap"}]))
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
            ("source", "contracts/out"),
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
        assert fx.engine_calls == []
