"""ACTIVATE: the post-PUBLISH stage's pure parts — pins, Foundation binding, product binding.

The meta-injector and the topology compiler themselves are exercised end to end
by `tests/integration/test_birth_activation_e2e.py` against their pinned
checkouts; everything that decides WHAT they are given is proven here without
them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "scripts" / "birth-runner" / "birth_activation.py"
GIT = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")


def _load():
    spec = importlib.util.spec_from_file_location("birth_activation_under_test", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


act = _load()


def _commit(root: Path) -> str:
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), *GIT, "commit", "-q", "-m", "x"], check=True)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _foundation(
    root: Path, *, status: str = "Release status: **ADDITIVE SUCCESSOR CANDIDATE**"
) -> Path:
    semantics = root / "semantics"
    semantics.mkdir(parents=True)
    for ledger in act.NODE_LEDGERS:
        name = ledger.split("/")[0].removeprefix("l9.").replace("-", "_") + ".yaml"
        (semantics / name).write_text(f"schema: x\nartifact_id: {ledger}\n", encoding="utf-8")
    (semantics / "unrelated.yaml").write_text("artifact_id: l9.other/global@1\n", encoding="utf-8")
    for version in ("v3.9.0", "v3.10.0"):
        release = root / "docs" / "semantic-foundation" / version
        release.mkdir(parents=True)
        (release / "MANIFEST.md").write_text(f"# {version}\n\n{status}\n", encoding="utf-8")
    return root


def _newborn(root: Path, *, name: str = "l9-state", kind: str = "node") -> Path:
    root.mkdir(parents=True)
    (root / "product-topology.yaml").write_text(
        yaml.safe_dump(
            {
                "product": {
                    "id": "l9.state",
                    "kind": kind,
                    "archetype_ref": "l9.node-archetype/authoritative-state@1",
                    "name": name,
                }
            }
        ),
        encoding="utf-8",
    )
    return root


class TestPins:
    def test_the_factory_pins_both_tools_to_exact_commits(self) -> None:
        pins = act.load_pin()
        assert pins["meta_injector"]["repository"] == "Quantum-L9/l9-meta-injector"
        assert (
            pins["constellation_topology"]["repository"] == "Quantum-L9/l9-constellation-topology"
        )
        for pin in pins.values():
            assert act.SHA_RE.match(pin["revision"])

    @pytest.mark.parametrize("revision", ["main", "v4.4.0", "54f7b5c"])
    def test_a_moving_or_short_ref_is_refused(self, tmp_path: Path, revision: str) -> None:
        doc = json.loads(act.PIN_PATH.read_text(encoding="utf-8"))
        doc["meta_injector"]["revision"] = revision
        path = tmp_path / "pin.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(act.ActivationError):
            act.load_pin(path)

    def test_a_checkout_off_the_pin_is_refused(self, tmp_path: Path) -> None:
        root = tmp_path / "tool"
        root.mkdir()
        (root / "f").write_text("x\n", encoding="utf-8")
        _commit(root)
        with pytest.raises(act.ActivationError, match="pin names"):
            act.assert_checkout_at(root, "0" * 40, "meta-injector")


class TestFoundationBinding:
    def test_binds_the_exact_revision_newest_release_and_ledger_digests(
        self, tmp_path: Path
    ) -> None:
        root = _foundation(tmp_path / "org")
        sha = _commit(root)
        binding = act.foundation_binding(root)
        assert binding["repository"] == "Quantum-L9/.github"
        assert binding["revision"] == sha
        # Numeric, not lexical: v3.10.0 is newer than v3.9.0.
        assert binding["release"] == "v3.10.0"
        assert binding["admission"] == "candidate"
        assert list(binding["ledgers"]) == list(act.NODE_LEDGERS)
        authority = root / "semantics" / "authority_model.yaml"
        expected = "sha256:" + hashlib.sha256(authority.read_bytes()).hexdigest()
        assert binding["ledgers"]["l9.authority-model/global@1"] == expected

    @pytest.mark.parametrize(
        ("status", "admission"),
        [("Release status: ADMITTED", "admitted"), ("Release status: draft", "Unknown")],
    )
    def test_admission_is_read_never_assumed(
        self, tmp_path: Path, status: str, admission: str
    ) -> None:
        root = _foundation(tmp_path / "org", status=status)
        _commit(root)
        assert act.foundation_binding(root)["admission"] == admission

    def test_a_missing_ledger_is_refused(self, tmp_path: Path) -> None:
        root = _foundation(tmp_path / "org")
        (root / "semantics" / "node_archetypes.yaml").unlink()
        _commit(root)
        with pytest.raises(act.ActivationError, match="node-archetypes"):
            act.foundation_binding(root)

    def test_a_ledger_claimed_twice_is_refused(self, tmp_path: Path) -> None:
        root = _foundation(tmp_path / "org")
        (root / "semantics" / "copy.yaml").write_text(
            "artifact_id: l9.vocabulary/global@1\n", encoding="utf-8"
        )
        _commit(root)
        with pytest.raises(act.ActivationError, match="vocabulary"):
            act.foundation_binding(root)


class TestProductBinding:
    def test_binds_the_declared_node(self, tmp_path: Path) -> None:
        product = act.product_binding(_newborn(tmp_path / "n"), "Quantum-L9/l9-state")
        assert product == {
            "id": "l9-state",
            "owner": "Quantum-L9/l9-state",
            "kind": "node",
            "archetype": "l9.node-archetype/authoritative-state@1",
        }

    def test_a_product_that_is_not_the_repository_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(act.ActivationError, match="repository name"):
            act.product_binding(_newborn(tmp_path / "n"), "Quantum-L9/other")

    @pytest.mark.parametrize("name", ["l9.state", "L9-State", ""])
    def test_a_name_the_v2_schema_rejects_is_refused_not_rewritten(
        self, tmp_path: Path, name: str
    ) -> None:
        with pytest.raises(act.ActivationError):
            act.product_binding(_newborn(tmp_path / "n", name=name), "Quantum-L9/l9-state")

    def test_an_undeclared_product_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "n").mkdir()
        with pytest.raises(act.ActivationError, match="product-topology"):
            act.product_binding(tmp_path / "n", "Quantum-L9/l9-state")

    def test_an_unactivatable_kind_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(act.ActivationError, match="kind"):
            act.product_binding(_newborn(tmp_path / "n", kind="app"), "Quantum-L9/l9-state")


class TestMetaAuthority:
    def _render(self, tmp_path: Path) -> str:
        root = _foundation(tmp_path / "org")
        _commit(root)
        return act.render_meta_authority(
            injector=act.load_pin()["meta_injector"],
            foundation=act.foundation_binding(root),
            product=act.product_binding(_newborn(tmp_path / "n"), "Quantum-L9/l9-state"),
        )

    def test_renders_a_v2_document_bound_to_an_immutable_writer(self, tmp_path: Path) -> None:
        doc = yaml.safe_load(self._render(tmp_path))
        assert doc["schema"] == "l9.meta-authority/v2"
        assert doc["writer"]["ref"] == act.load_pin()["meta_injector"]["revision"]
        assert doc["product"]["id"] == "l9-state"
        assert doc["semantic_foundation"]["release"] == "v3.10.0"
        assert doc["legacy_writers"] == "forbidden"
        assert doc["inline_allow"] == []

    def test_rendering_is_byte_stable(self, tmp_path: Path) -> None:
        root = _foundation(tmp_path / "org")
        _commit(root)
        kwargs = {
            "injector": act.load_pin()["meta_injector"],
            "foundation": act.foundation_binding(root),
            "product": act.product_binding(_newborn(tmp_path / "n"), "Quantum-L9/l9-state"),
        }
        assert act.render_meta_authority(**kwargs) == act.render_meta_authority(**kwargs)
