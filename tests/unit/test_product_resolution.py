"""Compiler-backed product resolution: the factory's side of the engine boundary.

`product_resolution.py` proves that a checkout is exactly the pinned engine,
runs the engine's product-build capability in an isolated child interpreter,
and compares what comes back with the manifest the birth was handed. The real
engine is driven by `tests/integration/test_compiler_backed_birth.py`; this
suite drives the module's OWN obligations — the pin, the checkout proof, input
confinement, process isolation, snapshot immutability, and the comparison — and
for that it uses a fixture engine whose only behavior is to write the manifest
the test chose. Nothing here stands in for a receipt or an integrity gate: the
fixture engine is the thing under test's collaborator, not its evidence.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIRTH_RUNNER = REPO / "scripts" / "birth-runner"
GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


resolution = _load("l9_product_resolution_under_test", BIRTH_RUNNER / "product_resolution.py")
adapter_fixtures = _load(
    "l9_birth_adapter_fixtures_for_resolution", REPO / "tests" / "unit" / "test_l9_birth_adapter.py"
)

ENGINE_REPOSITORY = "Quantum-L9/l9-semantic-compiler-engine"
PACKAGE = "l9-semantic-compiler"
VERSION = "0.9.3"

# The fixture engine's CLI: the real product-build signature, writing the manifest
# that ships beside it. `--dirty-source` and `--crash` exist so the factory's
# refusals can be driven; a real engine has neither.
FIXTURE_CLI = textwrap.dedent(
    """
    import json, os, sys
    from pathlib import Path
    import yaml

    HERE = Path(__file__).resolve().parent


    def main(argv=None):
        argv = list(sys.argv[1:] if argv is None else argv)
        assert argv[0] == "product-build"
        opts = dict(zip(argv[1::2], argv[2::2]))
        behavior = json.loads((HERE / "behavior.json").read_text())
        if behavior.get("crash"):
            raise RuntimeError("fixture engine crashed")
        if behavior.get("dirty_source"):
            Path(opts["--topology"]).with_name("scratch.txt").write_text("written by the engine\\n")
        out = Path(opts["--output-dir"])
        out.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((HERE / "manifest.json").read_text())
        manifest["provenance"] = {"inputs_seen": sorted(k for k in opts if k != "--output-dir"),
                                  "env_seen": sorted(k for k in os.environ if k.startswith("L9_") or k == "PYTHONPATH")}
        if behavior.get("record_cwd"):
            manifest["provenance"]["cwd"] = os.getcwd()
        (out / "product-manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=True))
        return int(behavior.get("exit_code", 0))
    """
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *GIT_IDENTITY, *args], check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _commit_all(root: Path, message: str = "fixture") -> None:
    if not (root / ".git").is_dir():
        _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _manifest() -> dict[str, object]:
    return adapter_fixtures.make_manifest()


class Fixture:
    """A fixture engine at a known commit, a factory pinning exactly it, a clean source."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.engine = root / "engine"
        self.factory = root / "factory"
        self.source = root / "source"
        self._make_engine()
        self._make_factory()
        self._make_source()
        self.pin = resolution.load_pin(self.factory)
        # What the fixture engine really emits for this source (it stamps its own
        # provenance), captured once before any test changes its behavior.
        self.baseline = self.reproduce().manifest

    def _make_engine(self) -> None:
        pkg = self.engine / "src" / "l9_semantic_compiler"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "cli.py").write_text(FIXTURE_CLI, encoding="utf-8")
        self.set_behavior({})
        self.set_engine_manifest(_manifest())
        (self.engine / "pyproject.toml").write_text(
            f'[build-system]\nrequires = ["setuptools"]\n\n[project]\nname = "{PACKAGE}"\n'
            f'version = "{VERSION}"\n\n[tool.other]\nversion = "9.9.9"\n',
            encoding="utf-8",
        )
        _commit_all(self.engine)
        _git(self.engine, "remote", "add", "origin", f"https://github.com/{ENGINE_REPOSITORY}.git")
        self.engine_revision = _git(self.engine, "rev-parse", "HEAD")

    def set_behavior(self, behavior: dict[str, object]) -> None:
        # Untracked by design: behavior.json lives in .gitignore so the checkout stays clean.
        (self.engine / ".gitignore").write_text("behavior.json\nmanifest.json\n", encoding="utf-8")
        (self.engine / "src" / "l9_semantic_compiler" / "behavior.json").write_text(
            json.dumps(behavior), encoding="utf-8"
        )

    def set_engine_manifest(self, manifest: dict[str, object]) -> None:
        (self.engine / "src" / "l9_semantic_compiler" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _make_factory(self) -> None:
        pin = {
            "schema": resolution.PIN_SCHEMA,
            "repository": ENGINE_REPOSITORY,
            "revision": self.engine_revision,
            "package": PACKAGE,
            "version": VERSION,
            "module": "l9_semantic_compiler",
            "source_dir": "src",
        }
        path = self.factory / resolution.PIN_PATH
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")

    def _make_source(self) -> None:
        for rel in adapter_fixtures.INPUTS.values():
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {rel}\n", encoding="utf-8")
        _commit_all(self.source)

    def reproduce(self, **overrides: object) -> object:
        args: dict[str, object] = {
            "engine_root": self.engine,
            "pin": self.pin,
            "source_root": self.source,
            "inputs": dict(adapter_fixtures.INPUTS),
        }
        args.update(overrides)
        return resolution.reproduce_manifest(**args)  # type: ignore[arg-type]

    def resolve(self, **overrides: object) -> object:
        args: dict[str, object] = {
            "engine_root": self.engine,
            "claimed_compiler": {**self.pin.coordinate, "inputs": dict(adapter_fixtures.INPUTS)},
            "source_root": self.source,
            "supplied_manifest": self.baseline,
            "factory_root": self.factory,
        }
        args.update(overrides)
        return resolution.resolve_product(**args)  # type: ignore[arg-type]


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# The pin
# ─────────────────────────────────────────────────────────────────────────────


class TestThePin:
    def test_the_factory_pin_is_well_formed_and_names_the_engine(self) -> None:
        pin = resolution.load_pin(REPO)
        assert pin.repository == ENGINE_REPOSITORY
        assert len(pin.revision) == 40
        assert pin.package == PACKAGE
        assert pin.module == "l9_semantic_compiler"
        assert pin.coordinate == {
            "engine": pin.repository,
            "revision": pin.revision,
            "version": pin.version,
        }

    @pytest.mark.parametrize(
        "mutation",
        [
            {"schema": "l9.semantic-compiler-pin/v2"},
            {"revision": "main"},
            {"revision": "abc"},
            {"repository": "engine"},
            {"version": ""},
            {"version": " 0.9.3"},
            {"module": "l9-semantic-compiler"},
            {"source_dir": "../src"},
            {"source_dir": "."},
        ],
    )
    def test_a_malformed_pin_is_refused(self, fx: Fixture, mutation: dict) -> None:
        path = fx.factory / resolution.PIN_PATH
        document = json.loads(path.read_text(encoding="utf-8"))
        document.update(mutation)
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(resolution.ProductResolutionError, match="semantic compiler pin|not an"):
            resolution.load_pin(fx.factory)

    def test_a_missing_pin_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(resolution.ProductResolutionError, match="cannot read"):
            resolution.load_pin(tmp_path)

    def test_a_binding_naming_another_engine_disagrees(self, fx: Fixture) -> None:
        claimed = {**fx.pin.coordinate, "revision": "0" * 40, "version": "0.0.1"}
        found = resolution.engine_disagreements(claimed, fx.pin)
        assert len(found) == 2
        assert resolution.engine_disagreements(fx.pin.coordinate, fx.pin) == []


# ─────────────────────────────────────────────────────────────────────────────
# The engine checkout is proven
# ─────────────────────────────────────────────────────────────────────────────


class TestTheEngineCheckoutIsProven:
    def test_the_fixture_engine_proves(self, fx: Fixture) -> None:
        assert resolution.prove_engine_checkout(fx.engine, fx.pin) == fx.engine.resolve()

    def test_a_dirty_checkout_is_refused(self, fx: Fixture) -> None:
        (fx.engine / "src" / "l9_semantic_compiler" / "cli.py").write_text("# patched\n")
        with pytest.raises(resolution.ProductResolutionError, match="dirty"):
            resolution.prove_engine_checkout(fx.engine, fx.pin)

    def test_an_untracked_file_is_dirt_too(self, fx: Fixture) -> None:
        (fx.engine / "extra.py").write_text("print('hi')\n")
        with pytest.raises(resolution.ProductResolutionError, match="dirty"):
            resolution.prove_engine_checkout(fx.engine, fx.pin)

    def test_another_revision_is_refused(self, fx: Fixture) -> None:
        _git(fx.engine, "commit", "-q", "--allow-empty", "-m", "past the pin")
        with pytest.raises(resolution.ProductResolutionError, match="the factory pins"):
            resolution.prove_engine_checkout(fx.engine, fx.pin)

    def test_another_origin_is_refused(self, fx: Fixture) -> None:
        _git(fx.engine, "remote", "set-url", "origin", "https://github.com/Quantum-L9/fork.git")
        with pytest.raises(resolution.ProductResolutionError, match="origin"):
            resolution.prove_engine_checkout(fx.engine, fx.pin)

    @pytest.mark.parametrize(
        ("field", "value", "match"),
        [("name", "other-package", "declares package"), ("version", "0.9.4", "declares version")],
    )
    def test_another_package_or_version_is_refused(
        self, fx: Fixture, field: str, value: str, match: str
    ) -> None:
        pyproject = fx.engine / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        original = f'{field} = "{PACKAGE if field == "name" else VERSION}"'
        pyproject.write_text(text.replace(original, f'{field} = "{value}"', 1), encoding="utf-8")
        _commit_all(fx.engine, "repackaged")
        pin = resolution.EnginePin(
            **{**fx.pin.__dict__, "revision": _git(fx.engine, "rev-parse", "HEAD")}
        )
        with pytest.raises(resolution.ProductResolutionError, match=match):
            resolution.prove_engine_checkout(fx.engine, pin)

    def test_a_subdirectory_of_the_checkout_is_not_the_checkout(self, fx: Fixture) -> None:
        with pytest.raises(resolution.ProductResolutionError, match="not the root"):
            resolution.prove_engine_checkout(fx.engine / "src", fx.pin)

    def test_a_tree_that_is_not_a_checkout_is_refused(self, tmp_path: Path, fx: Fixture) -> None:
        (tmp_path / "copy").mkdir()
        with pytest.raises(resolution.ProductResolutionError, match="not a git checkout"):
            resolution.prove_engine_checkout(tmp_path / "copy", fx.pin)

    def test_a_missing_package_directory_is_refused(self, fx: Fixture) -> None:
        pin = resolution.EnginePin(**{**fx.pin.__dict__, "module": "l9_other"})
        with pytest.raises(resolution.ProductResolutionError, match="carries no src/l9_other"):
            resolution.prove_engine_checkout(fx.engine, pin)


# ─────────────────────────────────────────────────────────────────────────────
# Inputs are confined to the snapshot
# ─────────────────────────────────────────────────────────────────────────────


class TestInputsAreConfined:
    def test_defaults_resolve_inside_the_source(self, fx: Fixture) -> None:
        paths = resolution.resolve_inputs(adapter_fixtures.INPUTS, fx.source)
        assert set(paths) == set(resolution.INPUT_KEYS)
        for path in paths.values():
            assert fx.source.resolve() in path.parents

    def test_the_contract_catalog_defaults_to_the_engines_default(self, fx: Fixture) -> None:
        inputs = {k: v for k, v in adapter_fixtures.INPUTS.items() if k != "contract_catalog"}
        paths = resolution.resolve_inputs(inputs, fx.source)
        assert (
            paths["contract_catalog"] == (fx.source / resolution.DEFAULT_CONTRACT_CATALOG).resolve()
        )

    @pytest.mark.parametrize(
        "value", ["/etc/passwd", "../outside.yaml", "a/../../b.yaml", "", "./x.yaml"]
    )
    def test_an_escaping_or_malformed_input_is_refused(self, fx: Fixture, value: str) -> None:
        with pytest.raises(resolution.ProductResolutionError, match="compiler input topology"):
            resolution.resolve_inputs({**adapter_fixtures.INPUTS, "topology": value}, fx.source)

    def test_a_missing_required_input_is_refused(self, fx: Fixture) -> None:
        inputs = {**adapter_fixtures.INPUTS, "workflow_spec": "absent.yaml"}
        with pytest.raises(resolution.ProductResolutionError, match="not a file in the source"):
            resolution.resolve_inputs(inputs, fx.source)

    def test_a_symlink_escaping_the_source_is_refused(self, fx: Fixture) -> None:
        (fx.root / "outside.yaml").write_text("# outside\n", encoding="utf-8")
        (fx.source / "link.yaml").symlink_to(fx.root / "outside.yaml")
        with pytest.raises(resolution.ProductResolutionError, match="escapes the source"):
            resolution.resolve_inputs(
                {**adapter_fixtures.INPUTS, "topology": "link.yaml"}, fx.source
            )


# ─────────────────────────────────────────────────────────────────────────────
# Reproduction: isolated, read-only, exact
# ─────────────────────────────────────────────────────────────────────────────


class TestReproduction:
    def test_the_engines_manifest_comes_back_as_json(self, fx: Fixture) -> None:
        reproduction = fx.reproduce()
        assert reproduction.exit_code == 0
        assert reproduction.resolved
        assert reproduction.manifest["product"] == _manifest()["product"]
        assert reproduction.manifest["manifest_digest"] == _manifest()["manifest_digest"]

    def test_the_engine_receives_exactly_the_bound_inputs(self, fx: Fixture) -> None:
        seen = fx.reproduce().manifest["provenance"]["inputs_seen"]
        assert seen == sorted(
            [
                "--topology",
                "--repository-spec",
                "--workflow-spec",
                "--authority-lock",
                "--contract-catalog",
            ]
        )

    def test_the_engine_runs_isolated_from_this_process(
        self, fx: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No inherited PYTHON* or L9_* environment, no cwd in the source or the factory."""
        monkeypatch.setenv("L9_BIRTH_PRIVILEGED_TOKEN", "leak")
        monkeypatch.setenv("PYTHONPATH", str(fx.root / "injected"))
        fx.set_behavior({"record_cwd": True})
        provenance = fx.reproduce().manifest["provenance"]
        assert provenance["env_seen"] == []
        cwd = Path(provenance["cwd"]).resolve()
        assert fx.source.resolve() not in (cwd, *cwd.parents)
        assert fx.engine.resolve() not in (cwd, *cwd.parents)
        assert not cwd.exists(), "the scratch working directory is removed afterwards"

    def test_an_unresolved_product_is_reported_not_hidden(self, fx: Fixture) -> None:
        fx.set_engine_manifest(
            adapter_fixtures.make_manifest(unresolved=["resolved_manifest_gate:x"])
        )
        fx.set_behavior({"exit_code": 2})
        reproduction = fx.reproduce()
        assert reproduction.exit_code == 2
        assert reproduction.resolved is False
        assert reproduction.unresolved == ["resolved_manifest_gate:x"]

    def test_an_engine_that_writes_into_the_snapshot_is_refused(self, fx: Fixture) -> None:
        fx.set_behavior({"dirty_source": True})
        with pytest.raises(resolution.ProductResolutionError, match="changed the source snapshot"):
            fx.reproduce()

    def test_an_engine_that_crashes_is_refused_with_its_output(self, fx: Fixture) -> None:
        fx.set_behavior({"crash": True})
        with pytest.raises(resolution.ProductResolutionError, match="fixture engine crashed"):
            fx.reproduce()

    def test_a_source_that_is_not_a_checkout_is_refused(self, fx: Fixture, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(resolution.ProductResolutionError, match="not a git checkout"):
            fx.reproduce(source_root=plain)

    def test_a_dirty_snapshot_is_refused_before_the_engine_runs(self, fx: Fixture) -> None:
        """A snapshot already moving cannot be the one the payload reproduced."""
        (fx.source / "dirty.txt").write_text("drift\n", encoding="utf-8")
        fx.set_behavior({"crash": True})  # would be reported if the engine ran
        with pytest.raises(resolution.ProductResolutionError, match="dirty"):
            fx.reproduce()


# ─────────────────────────────────────────────────────────────────────────────
# Comparison
# ─────────────────────────────────────────────────────────────────────────────


def _reproduction(manifest: dict[str, object], exit_code: int = 0) -> object:
    return resolution.Reproduction(manifest=json.loads(json.dumps(manifest)), exit_code=exit_code)


class TestComparison:
    def test_identical_manifests_agree(self) -> None:
        assert resolution.manifest_disagreements(_reproduction(_manifest()), _manifest()) == []

    def test_a_different_digest_disagrees(self) -> None:
        supplied = _manifest()
        supplied["manifest_digest"] = "sha256:" + "9" * 64
        found = resolution.manifest_disagreements(_reproduction(_manifest()), supplied)
        assert any("digest disagreement" in f for f in found)

    def test_a_different_body_under_the_same_digest_disagrees(self) -> None:
        supplied = _manifest()
        supplied["capabilities"] = {"provides": ["forged"]}
        found = resolution.manifest_disagreements(_reproduction(_manifest()), supplied)
        assert found == [
            "manifest document disagreement: the supplied manifest differs from the reproduced one at capabilities"
        ]

    def test_an_unresolved_reproduction_disagrees_with_everything(self) -> None:
        unresolved = adapter_fixtures.make_manifest(unresolved=["gap"])
        found = resolution.manifest_disagreements(
            _reproduction(unresolved, exit_code=2), unresolved
        )
        assert any("exited 2" in f for f in found)
        assert any("unresolved entr" in f for f in found)

    def test_a_wrong_schema_on_either_side_disagrees(self) -> None:
        other = adapter_fixtures.make_manifest(schema="l9.product-manifest/v2")
        assert resolution.manifest_disagreements(_reproduction(other), _manifest())
        assert resolution.manifest_disagreements(_reproduction(_manifest()), other)

    def test_every_disagreement_is_reported(self) -> None:
        supplied = adapter_fixtures.make_manifest(
            manifest_digest="sha256:" + "9" * 64, ports={"x": 1}
        )
        found = resolution.manifest_disagreements(_reproduction(_manifest()), supplied)
        assert len(found) == 2


# ─────────────────────────────────────────────────────────────────────────────
# The whole proof
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveProduct:
    def test_a_reproduced_manifest_resolves(self, fx: Fixture) -> None:
        result = fx.resolve()
        assert result.engine == fx.pin.coordinate
        assert result.manifest_digest == _manifest()["manifest_digest"]
        assert result.inputs == adapter_fixtures.INPUTS
        assert result.to_dict()["engine"]["revision"] == fx.engine_revision

    def test_a_binding_naming_another_engine_is_refused_before_anything_runs(
        self, fx: Fixture
    ) -> None:
        fx.set_behavior({"crash": True})
        claimed = {
            **fx.pin.coordinate,
            "revision": "0" * 40,
            "inputs": dict(adapter_fixtures.INPUTS),
        }
        with pytest.raises(resolution.ProductResolutionError, match="the factory pins"):
            fx.resolve(claimed_compiler=claimed)

    def test_a_binding_without_inputs_is_refused(self, fx: Fixture) -> None:
        with pytest.raises(resolution.ProductResolutionError, match="no compiler inputs"):
            fx.resolve(claimed_compiler=dict(fx.pin.coordinate))

    def test_a_supplied_manifest_the_engine_does_not_reproduce_is_refused(
        self, fx: Fixture
    ) -> None:
        supplied = adapter_fixtures.make_manifest(manifest_digest="sha256:" + "9" * 64)
        with pytest.raises(resolution.ProductResolutionError, match="digest disagreement"):
            fx.resolve(supplied_manifest=supplied)

    def test_an_unproven_engine_is_refused(self, fx: Fixture) -> None:
        _git(fx.engine, "commit", "-q", "--allow-empty", "-m", "past the pin")
        with pytest.raises(resolution.ProductResolutionError, match="the factory pins"):
            fx.resolve()
