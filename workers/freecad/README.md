# FreeCAD CAD worker

Runs one CAD job inside FreeCAD 1.1.4 (spec §12.6, ADR-0001). The platform talks to it only through files: `/job/job.json` in, `/job/out/` out (including `result.json`). It never imports platform code; it runs on FreeCAD's own Python 3.11.

## Build

```bash
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
```

The build writes FreeCAD's user preferences (`configure_freecad.py`) and fails if they are missing; without them the GUI phase can deadlock (ADR-0001, finding 9).

## Run

Normally through the platform (`uv run iaiep-hopper ...`, see `iaiep.cad.worker`). A job runs in two phases (`run_job.sh`):

1. `freecadcmd main.py`: model, measurements, BOM, flat-pattern DXF, drawing page and drawing checks, STEP AP242, FCStd.
2. `freecad export_pdf.py` (Qt offscreen): opens the saved model and exports the drawing PDF.

## Layout

| Path | Content |
|:---|:---|
| `iaiep_worker/templates/` | Templates, one module each, with `TEMPLATE_ID`, `VERSION` and `run(job, out_dir)` |
| `iaiep_worker/hopper_geometry.py` | Hopper geometry rules (pure Python) |
| `iaiep_worker/layout.py`, `panel.py`, `dxf.py` | Sheet and scale choice, parts list and notes, DXF writer (pure Python) |
| `iaiep_worker/drawing.py` | TechDraw helpers and drawing checks (needs FreeCAD) |
| `tests/` | Unit tests of the pure-Python modules, run by the platform's pytest |

Modules that need FreeCAD are covered by the integration test (`uv run pytest -m integration`).
