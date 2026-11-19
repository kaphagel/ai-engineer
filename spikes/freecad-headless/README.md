# Spike: FreeCAD headless model and drawing generation

Throw-away code for Phase 0 (spec §25). The results and decisions are recorded in [ADR-0001](../../doc/adr/0001-freecad-headless-execution.md).

## Run

```bash
cd spikes/freecad-headless
docker build --build-arg UID=$(id -u) -t iaiep-freecad-spike:1.1.4 .

# Model, checks, TechDraw page, FCStd, STEP AP242, DXF (headless)
docker run --rm -v "$PWD":/work iaiep-freecad-spike:1.1.4 freecadcmd spike_hopper.py

# PDF and SVG of the drawing page (GUI binary, offscreen, no display needed)
docker run --rm -v "$PWD":/work -e QT_QPA_PLATFORM=offscreen iaiep-freecad-spike:1.1.4 freecad export_gui.py
```

Outputs are written to `out/` (git-ignored): `hopper.FCStd`, `hopper.step`, `drawing.dxf`, `drawing.pdf`, `drawing.svg`, `results.json` and `gui_results_offscreen.json`.

All data is synthetic. The drawing is marked "DRAFT - NOT FOR FABRICATION".
