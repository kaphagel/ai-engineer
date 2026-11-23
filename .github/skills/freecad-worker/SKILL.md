---
name: freecad-worker
description: >
  Rules and verified commands for working on the IAIEP FreeCAD CAD worker (workers/freecad), its
  platform client (src/iaiep/cad) and FreeCAD spikes (spikes/). Use before writing or changing any
  code that runs inside FreeCAD, builds geometry, TechDraw drawings, STEP/DXF/PDF exports, or runs
  the worker container.
---

# FreeCAD worker (coding-agent skill)

This is a skill for **coding assistants working on this repository**. It is not a platform skill: platform skills live in `skills/` and follow spec §6.8 and Appendix B.

The details and evidence are in the ADRs; this file only lists the rules that cause silent failures when forgotten. Record new FreeCAD findings in ADR-0001, not here.

- [ADR-0001](../../../doc/adr/0001-freecad-headless-execution.md): headless execution, findings 1–16
- [ADR-0004](../../../doc/adr/0004-hopper-template-wall-panels.md): hopper template
- [ADR-0005](../../../doc/adr/0005-weldment-operations-and-editable-model.md): direction for CAD construction (plan of general weldment operations); accepted: do not add equipment-specific geometry to the worker; new geometry goes into plan generators in the domain packages, new general operations into the worker
- [workers/freecad/README.md](../../../workers/freecad/README.md): layout and job phases

## Boundaries

- The worker runs on **FreeCAD's own Python 3.11** (AppImage), the platform on Python 3.12. The worker never imports platform code and the platform never imports worker code; they exchange `job.json`, `result.json` and output files.
- Every model the worker builds is checked against an **independent calculation** in the domain package. Do not make the checks use the worker's own geometry code.
- Committed tests and examples use **synthetic data only**. Real reference data (`data/reference/`, `doc/drawings/`) is confidential (D-15) and git-ignored.
- Drawings are always marked "DRAFT – NOT FOR FABRICATION" (spec §30.2).

## Rules that prevent silent failures

1. **Never call `Gui.updateGui()`** or otherwise pump the event loop while waiting. Use Qt timers in the real event loop and compute TechDraw views one at a time (ADR-0001 findings 9–10).
2. The GUI phase deadlocks unless the **notification area is disabled**; the image build writes these preferences and fails without them. Do not remove that check (finding 9).
3. **PDF export needs the GUI binary** (`freecad`, `QT_QPA_PLATFORM=offscreen`, no Xvfb). Everything else runs in `freecadcmd` (Decision).
4. **A successful export is not proof of a correct drawing.** Keep and extend the drawing checks: views have edges and lie inside the frame, no template placeholder text, title block matches metadata (findings 1, 5, 6).
5. Use **`Shape.optimalBoundingBox()`** or exact measurements, not `BoundBox` (finding 4).
6. Model welded parts as **individual plates**, not `Part::Thickness` on a loft (finding 3).
7. **Units:** set the `MmMin` schema, including the per-document unit system (finding 11).
8. **Native file:** save from the GUI phase with solids visible and a fitted camera; the platform checks it (finding 12).
9. `abortTransaction` does nothing in documents created without the GUI: **remove partial objects explicitly** on failure (note 14).
10. **Check object state after every recompute** (`Invalid`/`Error`), not only the final shape (note 15).
11. Between PartDesign Bodies use `PartDesign::Boolean`, not `Part::Cut`/`Fuse`/`Common` (note 13).
12. Do not use `FeaturePython` objects in files given to users: without our module they silently keep stale geometry (note 16, spikes/freecad-varset).
13. STEP is AP242 via `Part.setStaticValue("write.step.schema", "AP242DIS")`.
14. Template IDs and versions must match between `domains/esp/src/iaiep_esp/hopper/__init__.py` and the worker template.

## Containers

The Dev Container uses Docker outside of Docker: bind mounts resolve on the host. **Copy files in and out with `docker cp`** (as `iaiep.cad.worker` and `spikes/freecad-varset/run.sh` do); do not bind-mount. The container user must have a passwd entry (finding 2).

## Verified commands

```bash
# Platform checks (CI)
uv sync --locked && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest

# Worker image (after any worker change) and the integration test
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
uv run pytest -m integration

# End-to-end hopper run (synthetic; the reference case needs the confidential files)
uv run iaiep-hopper domains/esp/examples/hopper_synthetic.toml --out out/hopper-synthetic
```

`spikes/` is excluded from Ruff and mypy; spike outputs in `out/` are git-ignored.
