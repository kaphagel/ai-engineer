"""End-to-end: input set -> FreeCAD worker container -> checked outputs. Needs Docker and the worker image:

docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
uv run pytest -m integration
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from iaiep.cad.worker import WorkerSettings
from iaiep_esp.hopper.cli import main

EXAMPLE = Path(__file__).parents[2] / "domains" / "esp" / "examples" / "hopper_synthetic.toml"


def _worker_image_available() -> bool:
    if shutil.which("docker") is None:
        return False
    image = WorkerSettings.from_env().image
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False).returncode == 0


@pytest.mark.integration
@pytest.mark.skipif(not _worker_image_available(), reason="Docker or the FreeCAD worker image is not available")
def test_synthetic_hopper_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "hopper"
    assert main([str(EXAMPLE), "--out", str(out)]) == 0
    report = json.loads((out / "report.json").read_text())
    assert not [c for c in report["checks"] if c["status"] == "fail"]
    assert {"drawing.pdf", "hopper.step", "hopper.FCStd", "flat_P1.dxf"} <= set(report["files_sha256"])


@pytest.mark.integration
@pytest.mark.skipif(not _worker_image_available(), reason="Docker or the FreeCAD worker image is not available")
def test_end_wall_bending_inside_a_tier_end_to_end(tmp_path: Path) -> None:
    # The mitred plates at the bend must not overlap; dimensions must still be exact.
    text = EXAMPLE.read_text(encoding="utf-8")
    old = 'end_wall_vertical_height_mm = { value = 1200, source = "synthetic" }'
    assert old in text
    case = tmp_path / "case.toml"
    case.write_text(text.replace(old, old.replace("1200", "1800")), encoding="utf-8")
    out = tmp_path / "hopper"
    assert main([str(case), "--out", str(out)]) == 0
    report = json.loads((out / "report.json").read_text())
    assert "EndOutlet-T2-upper" in report["calculation"]["panels"]
