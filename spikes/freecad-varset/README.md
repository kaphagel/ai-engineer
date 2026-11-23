# Spike: editable native model with VarSet and expressions

Throw-away code for the hopper template decision (ADR-0005). Question: can the native FreeCAD file be **editable by hand** – change a parameter, recompute, correct geometry – when it is generated headless by our worker with FreeCAD 1.1.4?

Idea from [ghbalf/freecad-ai](https://github.com/ghbalf/freecad-ai) (LGPL-2.1); no code was copied. All data is synthetic.

## What is tested

One side wall and one end wall of a pyramidal hopper (sloped trapezoid plates, no gaps, mitres or stiffeners). Parameters in an `App::VarSet` named `Hopper`: `TopLength`, `TopWidth`, `SlotLength`, `SlotWidth`, `Height`, `Thickness`. Every step is checked against an independent calculation (`common.py`): all plate corners within 0.001 mm, volume within 1 ppm, valid single solid, no object in an error state.

- **Variant A – built-in objects only:** each wall is a sketch (trapezoid, fully constrained, named constraints bound to the VarSet by expressions), placed in 3D by a placement expression, and a `Part::Extrusion` whose length is `Hopper.Thickness`.
- **Variant B – scripted feature:** each wall is a `Part::FeaturePython` whose Python code (`feature/plate_feature.py`) computes the shape from properties bound to the VarSet.

Steps, each a fresh `freecadcmd` process: build → change three parameters → save; reopen → check → change three other parameters → check. Variant B is also reopened without its Python module on the path.

## Run

```bash
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev ../../workers/freecad
sh run.sh        # results and both FCStd files in out/ (git-ignored)
```

## Results (2026-11-23, FreeCAD 1.1.4, worker image)

| Step | Variant A (built-in) | Variant B (scripted) |
|:---|:---|:---|
| Build | Pass | Pass |
| Change 3 parameters, recompute | Pass (≈ 9 ms) | Pass (≈ 4 ms) |
| Reopen in a fresh process, as saved | Pass | Pass |
| Change 3 other parameters, recompute | Pass | Pass with the module |
| Reopen **without** the Python module, change parameters | – (not needed) | **Fails silently**: the old shape stays, no object is marked as an error; only the log says `module not permitted: plate_feature` |

Corner deviation was 0.000 mm and volumes matched exactly in every passing step.

Findings:

1. **Placement by expression works.** `placement(vector(...); rotation(vector(0; 1; 0); atan2(...)) * rotation(vector(0; 0; 1); 90 deg))` is accepted, including composed rotations and units (`0 mm`, `90 deg`). A sloped plate can follow the parameters without datum planes or attachment.
2. **Variant A needs no code of ours.** The file contains only `App::VarSet`, `Sketcher::SketchObject` and `Part::Extrusion`, so any FreeCAD 1.1 user can change a parameter and get correct geometry.
3. **Variant B is unsafe for files handed to users.** Without our module the file looks editable, but changes silently do nothing. This is worse than a static model.
4. **Cost.** A plate in variant A takes a fully constrained sketch (4 lines, 10 constraints), three constraint expressions, a placement expression and an extrusion – about 40 lines instead of 5 for a polygon extrusion. Every relationship has to be written a second time in FreeCAD's expression language.
5. **Expressions keep the topology fixed.** They change dimensions, not the number of objects. Changes that add or remove parts (number of tiers, stiffeners from the spacing rules, brackets per support) cannot follow a parameter change; they need regeneration.

## Not tested

Mitre cuts and panel gaps, tiers, profiles and their placement along sloped edges, TechDraw views and dimensions of an expression-driven model, recompute time at full hopper size (several hundred objects), and editing in the GUI.
