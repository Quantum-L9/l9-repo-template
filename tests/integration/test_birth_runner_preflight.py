"""Birth-runner preflight dry acceptance (no push)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_birth_preflight_with_template_src() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        play = Path(tmp)
        work = play / "work"
        lines = [
            'org: "Quantum-L9"',
            'repo_name: "demo-museum-pkg"',
            'package_name: "demo_museum_pkg"',
            'description: "demo birth"',
            f'work_dir: "{work}"',
            'template_repo: "Quantum-L9/l9-repo-template"',
            f'template_src: "{REPO}"',
        ]
        (play / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        env = os.environ.copy()
        env["PLAY_DIR"] = str(play)
        proc = subprocess.run(
            ["bash", str(REPO / "scripts" / "birth-runner" / "01_preflight.sh")],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert (play / ".checkpoints" / "01_preflight.done").is_file()
