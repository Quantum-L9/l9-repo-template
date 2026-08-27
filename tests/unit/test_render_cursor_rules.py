"""Tests for scripts/render_cursor_rules.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RENDER = REPO / "scripts" / "render_cursor_rules.py"


def test_check_rules_current() -> None:
    proc = subprocess.run(
        [sys.executable, str(RENDER), "--check"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK:" in proc.stdout


def test_render_is_idempotent(tmp_path: Path) -> None:
    # Smoke: dry re-render to a temp output dir from real templates/config
    out = tmp_path / "rules"
    proc = subprocess.run(
        [
            sys.executable,
            str(RENDER),
            "--output-dir",
            str(out),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--force",
        ],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    mdc = list(out.glob("*.mdc"))
    assert mdc
    assert any("L9_RENDERED" in p.read_text(encoding="utf-8") for p in mdc)


# ─────────────────────────────────────────────────────────────────────────────
# Conditional rendering: a rule about a surface this repository does not have
# ─────────────────────────────────────────────────────────────────────────────

_SPEC = importlib.util.spec_from_file_location("l9_render_cursor_rules", RENDER)
assert _SPEC is not None
assert _SPEC.loader is not None
render = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = render
_SPEC.loader.exec_module(render)

CONFIG_WITH_APP = """plugin_version: "1.0.0"
repo_name: "l9-fixture"
domain: "fixture-domain"
package_name: "l9_fixture"
python_version: "3.12"
app_entrypoint: "l9_fixture.app:app"
protected_paths:
  - "uv.lock"
high_risk_commands:
  - "rm -rf .venv"
ci_gates:
  - "make verify"
"""


def _fixture(tmp_path: Path, *, app_entrypoint: bool) -> tuple[Path, Path, Path]:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "plain.mdc.template").write_text(
        '---\ndescription: "${repo_name}"\n---\n\n# ${repo_name}\n', encoding="utf-8"
    )
    (templates / "conditional.mdc.template").write_text(
        "<!-- L9_RENDER_REQUIRES: app_entrypoint -->\n"
        '---\ndescription: "${repo_name} service"\n---\n\n'
        "App entrypoint: `${app_entrypoint}`\n",
        encoding="utf-8",
    )
    config = tmp_path / "plugin-config.yaml"
    body = CONFIG_WITH_APP
    if not app_entrypoint:
        body = "".join(
            line
            for line in body.splitlines(keepends=True)
            if not line.startswith("app_entrypoint:")
        )
    config.write_text(body, encoding="utf-8")
    return templates, config, tmp_path / "rules"


def _render(tmp_path: Path, templates: Path, config: Path, out: Path, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(RENDER),
            "--template-dir",
            str(templates),
            "--config",
            str(config),
            "--output-dir",
            str(out),
            "--manifest",
            str(tmp_path / "manifest.json"),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_template_requirement_is_parsed_and_stripped() -> None:
    body, requires = render.template_requirements(
        "<!-- L9_RENDER_REQUIRES: app_entrypoint, extra -->\n---\nx\n"
    )
    assert requires == ("app_entrypoint", "extra")
    assert "L9_RENDER_REQUIRES" not in body
    assert body.startswith("---")


def test_an_unmet_requirement_is_the_missing_or_empty_key() -> None:
    assert render.unmet_requirements({"a": "v"}, ("a",)) == ()
    assert render.unmet_requirements({}, ("a",)) == ("a",)
    assert render.unmet_requirements({"a": "  "}, ("a",)) == ("a",)


def test_a_rule_renders_when_its_requirement_is_met(tmp_path: Path) -> None:
    templates, config, out = _fixture(tmp_path, app_entrypoint=True)
    proc = _render(tmp_path, templates, config, out, "--force")
    assert proc.returncode == 0, proc.stderr
    assert (out / "conditional.mdc").is_file()
    assert "l9_fixture.app:app" in (out / "conditional.mdc").read_text(encoding="utf-8")


def test_a_rule_is_not_rendered_when_its_subject_does_not_exist(tmp_path: Path) -> None:
    templates, config, out = _fixture(tmp_path, app_entrypoint=False)
    proc = _render(tmp_path, templates, config, out, "--force")
    assert proc.returncode == 0, proc.stderr
    assert not (out / "conditional.mdc").exists()
    assert (out / "plain.mdc").is_file(), "an unconditional rule was collateral damage"
    assert "skipped" in proc.stdout


def test_a_previously_rendered_unqualified_rule_is_removed(tmp_path: Path) -> None:
    """The observability-core shape: the rule is already on disk and is false."""
    templates, config, out = _fixture(tmp_path, app_entrypoint=True)
    assert _render(tmp_path, templates, config, out, "--force").returncode == 0
    assert (out / "conditional.mdc").is_file()

    config.write_text(
        "".join(
            line
            for line in config.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.startswith("app_entrypoint:")
        ),
        encoding="utf-8",
    )
    proc = _render(tmp_path, templates, config, out)
    assert proc.returncode == 0, proc.stderr
    assert not (out / "conditional.mdc").exists()
    assert "removed" in proc.stdout


def test_check_reports_an_unqualified_rule_still_on_disk(tmp_path: Path) -> None:
    templates, config, out = _fixture(tmp_path, app_entrypoint=True)
    _render(tmp_path, templates, config, out, "--force")
    config.write_text(
        "".join(
            line
            for line in config.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.startswith("app_entrypoint:")
        ),
        encoding="utf-8",
    )
    proc = _render(tmp_path, templates, config, out, "--check")
    assert proc.returncode == 1
    assert "unqualified" in proc.stderr
    assert "requires app_entrypoint" in proc.stderr


def test_the_manifest_records_what_was_skipped(tmp_path: Path) -> None:
    templates, config, out = _fixture(tmp_path, app_entrypoint=False)
    _render(tmp_path, templates, config, out, "--force")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [entry["unmet_requirements"] for entry in manifest["skipped"]] == [["app_entrypoint"]]
    assert [Path(entry["output"]).name for entry in manifest["rules"]] == ["plain.mdc"]


def test_an_unmanaged_file_is_never_removed_without_force(tmp_path: Path) -> None:
    templates, config, out = _fixture(tmp_path, app_entrypoint=False)
    out.mkdir()
    (out / "conditional.mdc").write_text("hand authored\n", encoding="utf-8")
    proc = _render(tmp_path, templates, config, out)
    assert proc.returncode != 0
    assert "Refusing to remove unmanaged file" in proc.stderr
    assert (out / "conditional.mdc").is_file()


def test_the_fastapi_rule_declares_the_entrypoint_it_documents() -> None:
    """The regression, held at its source rather than at its symptom."""
    template = REPO / ".cursor" / "rules" / "templates" / "fastapi.mdc.template"
    _, requires = render.template_requirements(template.read_text(encoding="utf-8"))
    assert "app_entrypoint" in requires
