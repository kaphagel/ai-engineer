"""CAD worker phase 1 entry point. Runs in freecadcmd (FreeCAD's Python 3.11, no GUI).

Reads $IAIEP_JOB_DIR/job.json, runs the requested template, writes all outputs except the PDF and
$IAIEP_JOB_DIR/out/result.json. Exit code 0 means the job ran; check results are in result.json.
The PDF is exported afterwards by export_pdf.py (run_job.sh).
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULT_SCHEMA_VERSION = 1


def main() -> int:
    job_dir = os.environ.get("IAIEP_JOB_DIR", "/job")
    out_dir = os.path.join(job_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    result = {"schema_version": RESULT_SCHEMA_VERSION, "ok": False}
    try:
        import FreeCAD as App

        result["freecad_version"] = ".".join(App.Version()[:3])
        with open(os.path.join(job_dir, "job.json"), encoding="utf-8") as fh:
            job = json.load(fh)

        from iaiep_worker.templates import TEMPLATES

        requested = job["template"]
        template = TEMPLATES.get(requested["id"])
        if template is None:
            raise ValueError(f"Unknown template {requested['id']!r}")
        if requested["version"] != template.VERSION:
            raise ValueError(
                f"Template {requested['id']} is version {template.VERSION}, job requires {requested['version']}"
            )
        result["template"] = {"id": template.TEMPLATE_ID, "version": template.VERSION}
        result.update(template.run(job, out_dir))
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print("IAIEP_WORKER_DONE", "ok" if result["ok"] else result.get("error"), file=sys.stderr, flush=True)
    return 0 if result["ok"] else 1


# The FreeCAD GUI binary would otherwise keep running after the script.
os._exit(main())
