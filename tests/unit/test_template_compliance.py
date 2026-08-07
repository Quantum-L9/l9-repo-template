"""Template compliance: side-by-side identity + hard rejects."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_three_template_docs() -> None:
    for rel in ("README.md", "ARCHITECTURE.md", "docs/WHEN_TO_USE.md"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "L9-Node-Template" in text
        assert "PackageTemplate" in text or "Constellation.PackageTemplate" in text


def test_absent_forbidden_scaffolds() -> None:
    assert not (REPO / "Justfile").exists()
    assert not (REPO / "contracts").exists()
    assert not (REPO / "engine").exists()
    hits = list(REPO.rglob("enginehandlers.py"))
    assert hits == [], f"enginehandlers present: {hits}"


def test_inventory_classifies_wrong_product() -> None:
    text = (REPO / "TEMPLATE_INVENTORY.md").read_text(encoding="utf-8")
    assert "REJECT_WRONG_PRODUCT" in text
    assert "create_node_app" in text
