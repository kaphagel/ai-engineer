# ADR-0001: FreeCAD 1.1.4 headless execution for model and drawing generation

- **Status:** Accepted (spike result)
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

## Decision

- The CAD worker runs FreeCAD 1.1.4 from the official AppImage, extracted into a container image with a non-root user. The AppImage is verified by its published SHA-256 checksum.
- Drawing generation (PDF/SVG) runs the FreeCAD GUI binary with `QT_QPA_PLATFORM=offscreen`, showing the page and waiting for view computation before export. Xvfb is not needed. For simplicity the Phase 1 worker may run all CAD steps in this mode in one process.
- STEP is written as AP242 through `Part.setStaticValue`.
- Issued drawings are PDF. DXF is used for geometry and flat patterns.
- The hopper template models individual plates (finding 3).
- Drawing checks in Phase 1 include at least: every view has visible edges, every view lies inside the drawing frame, no template placeholder text remains, and the title block fields match the artifact metadata.

## Not yet tested

- The SheetMetal add-on (D-25); not needed if plates are modelled individually.
- Drawings of assemblies with parts lists and balloons.
- Run time and memory use for larger models.
