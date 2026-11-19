# ADR-0001: FreeCAD 1.1.4 headless execution for model and drawing generation

- **Status:** Accepted (spike result; amended 2026-11-19 with Phase 1 worker findings 9–12)
- **Date:** 2026-11-18
- **Related:** spec §12.6, §12.7, §12.8, §1.2 (F-6), D-02, D-25, X-01
- **Evidence:** [spikes/freecad-headless](../../spikes/freecad-headless/)

## Context

The specification requires CAD workers that generate models and drawings without user interaction (§12.6), and identified TechDraw PDF export as a known risk. This spike tested FreeCAD 1.1.4 (official Linux AppImage, Python 3.11.14) in a Debian container with a synthetic hopper.

## Results

| Capability | Mode | Result |
|:---|:---|:---|
| Parametric model (spreadsheet → sketches → ruled loft → plate thickness) | `freecadcmd` | Works |
| Regeneration after parameter change | `freecadcmd` | Works (height 3500 → 4000 mm) |
| Geometry check (valley angle) | `freecadcmd` | Works (50.23°, matches hand calculation) |
| TechDraw page, ISO 5457 A3 template, ISO 7200 title block fields, first-angle projection | `freecadcmd` | Works |
| Projection views and isometric view (hidden-line removal) | `freecadcmd` | Works |
| Dimension placed on a computed view edge | `freecadcmd` | Works (6000.0 mm exact) |
| Save native `.FCStd` | `freecadcmd` | Works |
| STEP AP242 export | `freecadcmd` | Works, with `Part.setStaticValue("write.step.schema", "AP242DIS")` |
| DXF page export | `freecadcmd` | Works for views and dimensions; **the template and title block are not included** |
| SVG and PDF page export | `freecadcmd` | **Not available**: only in `TechDrawGui` |
| SVG and PDF page export | `freecad` GUI binary with `QT_QPA_PLATFORM=offscreen` | Works, **if** the page is shown and the background view computation is awaited (see below) |
| SVG and PDF page export | GUI under Xvfb | Hung; not investigated further because offscreen works |
| Repeatability (two runs, same inputs) | — | Geometry signature and DXF identical; STEP identical except the header timestamp |

## Findings that affect the design

1. **Silent wrong output.** Exporting the PDF immediately after opening the document reported success but produced a page with views missing or misplaced. Views are computed in background threads and must be awaited through the Qt event loop. **An export that reports success is not proof of a correct drawing.** The automated drawing checks of §12.7 are therefore essential, and must include checking that every view has geometry and lies inside the frame.
2. **Container user.** FreeCAD crashes at start-up if the process user has no `/etc/passwd` entry. The worker image must define a non-root user.
3. **Plate thickness on a ruled loft.** `Part::Thickness` fails with the `Intersection` join and works with `Arc`, but `Arc` produces rounded inner corners that do not represent welded plates. The Phase 1 hopper template should model the hopper as **individual plates**. This matches fabrication, gives exact flat patterns directly, and avoids the thickness operation.
4. **Bounding boxes.** `Shape.BoundBox` is not tight on curved faces (6808 mm reported for a 6000 mm part). Geometry checks must use `Shape.optimalBoundingBox()` or exact measurements.
5. **Layout.** At 1:50 the side view extends outside the frame. View placement and scale selection must be computed from view sizes, and checked (§12.7).
6. **Template defaults.** Unfilled title-block fields show template placeholder text ("ST2", "RD"). Company templates must have every field set explicitly, and a drawing check must reject placeholder text.
7. **Fonts.** The SVG output depends on FreeCAD's drawing font (osifont); viewers without it render text wider, so the drawing number overflows its field. The PDF embeds the font and renders correctly. PDF is the issue format (§12.7); SVG is for previews only.
8. **DXF scope.** The DXF page export contains geometry and dimensions but no frame or title block. DXF is therefore suitable for geometry exchange and flat patterns, not as an issued drawing.

Findings from the Phase 1 worker (19 Nov 2026):

9. **GUI deadlock in offscreen mode.** The PDF export hung intermittently, and on some models every time. A native stack trace showed the GUI main thread deadlocked on itself: FreeCAD shows a notification pop-up, the offscreen Qt platform logs "This plugin does not support raise()", and FreeCAD routes that log message back into its notification area while holding the area's lock. Disabling the notification area (`NotificationAreaEnabled` and `NonIntrusiveNotificationsEnabled` set to false in the user preferences) removes it: 60 of 60 export runs passed on three models, against 0 of 6 with the notification area enabled. Earlier workarounds (pumping the event loop differently) only changed how often it happened.
10. **Threaded views with the GUI.** Without the GUI, TechDraw computes hidden lines synchronously. With the GUI, each view runs in its own background thread and a document recompute starts all views at once. Python code must not pump the event loop (`Gui.updateGui()`) while waiting; the worker uses Qt timers in the real event loop and computes views one at a time. Face finding (only needed for hatching) is switched off.
11. **Units.** FreeCAD's default unit schema shows lengths over 10 m in metres ("11.09"). The worker sets the `MmMin` schema, including the per-document unit system that FreeCAD 1.x applies when the GUI opens a file, and formats dimensions as whole millimetres.
12. **Native file for users.** A model saved only by `freecadcmd` has no GUI document; one re-saved from the GUI phase had all solids hidden and the default camera (a 4 mm field of view), so it opened as an "empty" 3D view. The worker now shows the solids, sets a fitted isometric camera, closes the drawing tab and saves from the GUI phase; the platform checks the saved file (`native.plates_visible`, `native.camera_fitted`).

## Decision

- The CAD worker runs FreeCAD 1.1.4 from the official AppImage, extracted into a container image with a non-root user. The AppImage is verified by its published SHA-256 checksum.
- The worker runs a job in two phases (`workers/freecad/`): `freecadcmd` builds the model, measurements, flat patterns, drawing page, drawing checks, STEP and FCStd (synchronous, no GUI); then the GUI binary with `QT_QPA_PLATFORM=offscreen` only opens the saved model and exports the PDF (findings 9 and 10). Xvfb is not needed.
- The worker image writes FreeCAD's user preferences at build time (notification area off, face finding off, mm units), and the build fails if they are missing.
- STEP is written as AP242 through `Part.setStaticValue`.
- Issued drawings are PDF. DXF is used for geometry and flat patterns.
- The hopper template models individual plates (finding 3).
- Drawing checks in Phase 1 include at least: every view has visible edges, every view lies inside the drawing frame, no template placeholder text remains, and the title block fields match the artifact metadata.

## Not yet tested

- The SheetMetal add-on (D-25); not needed if plates are modelled individually.
- Drawings of assemblies with parts lists and balloons.
- Run time and memory use for larger models.
