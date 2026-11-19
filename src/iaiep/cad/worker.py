"""Client side of the FreeCAD CAD worker (spec §12.6, §28): runs one job in the worker container.

The worker never imports platform code and the platform never imports worker code; they exchange
job.json and result.json plus output files. Files are copied in and out of the container with
`docker cp`, so no host paths need to be shared (this also works from inside the Dev Container,
which uses the host's Docker daemon).
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WorkerError(RuntimeError):
    """The worker container could not run the job."""


@dataclass(frozen=True)
class WorkerSettings:
    image: str = "iaiep-freecad-worker:dev"
    timeout_s: float = 900.0
    docker: str = "docker"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WorkerSettings":
        env = os.environ if env is None else env
        default = cls()
        return cls(
            image=env.get("IAIEP_FREECAD_IMAGE", default.image),
            timeout_s=float(env.get("IAIEP_FREECAD_TIMEOUT_S", default.timeout_s)),
        )


@dataclass(frozen=True)
class WorkerRun:
    result: dict[str, Any]
    out_dir: Path
    image_id: str
    log: str
    files_sha256: dict[str, str]


def run_job(job: Mapping[str, Any], out_dir: Path, settings: WorkerSettings) -> WorkerRun:
    """Run `job` in a fresh worker container and copy all outputs to `out_dir` (replaced if present)."""
    image_id = _docker(settings, "image", "inspect", "--format", "{{.Id}}", settings.image).strip()
    container = _docker(settings, "create", settings.image).strip()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            job_path = Path(tmp) / "job.json"
            job_path.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
            _docker(settings, "cp", str(job_path), f"{container}:/job/job.json")
        try:
            completed = subprocess.run(
                [settings.docker, "start", "--attach", container],
                capture_output=True,
                text=True,
                timeout=settings.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerError(f"CAD worker timed out after {settings.timeout_s:.0f} s") from exc
        log = completed.stdout + completed.stderr
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        _docker(settings, "cp", f"{container}:/job/out", str(out_dir))
    finally:
        subprocess.run([settings.docker, "rm", "--force", container], capture_output=True, check=False)

    result_path = out_dir / "result.json"
    if not result_path.exists():
        raise WorkerError(f"CAD worker wrote no result (exit code {completed.returncode}):\n{log[-2000:]}")
    result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    hashes = {p.name: _sha256(p) for p in sorted(out_dir.iterdir()) if p.is_file() and p.name != "result.json"}
    return WorkerRun(result=result, out_dir=out_dir, image_id=image_id, log=log, files_sha256=hashes)


def _docker(settings: WorkerSettings, *args: str) -> str:
    completed = subprocess.run([settings.docker, *args], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise WorkerError(f"docker {args[0]} failed: {completed.stderr.strip()}")
    return completed.stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
