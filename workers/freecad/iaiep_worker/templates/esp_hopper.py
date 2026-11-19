"""Template: ESP trough or pyramidal hopper built from flat welded wall panels (spec §24.3, ADR-0001).

The geometry rules are in iaiep_worker.hopper_geometry (pure Python, unit-tested). This module turns
the panels into FreeCAD solids, measures the model, and produces the BOM, flat patterns, drawing and
exports. Stiffeners, tier beams, top panels, bracing, corner joint plates and welds are not modelled
in this template version.
"""

import hashlib
import math
import os

import FreeCAD as App
import Part

from iaiep_worker import drawing as dw
from iaiep_worker import dxf
from iaiep_worker import hopper_geometry as geo
from iaiep_worker import layout as lay
from iaiep_worker import panel as pnl

TEMPLATE_ID = "esp.hopper"
VERSION = "0.2.0"

V = App.Vector


def run(job, out_dir):
    spec = geo.HopperSpec.from_parameters(job["parameters"])
    material = job["material"]
    meta = job["drawing"]

    doc = App.newDocument("Hopper")
    dw.use_millimetres(doc)
    dw.disable_face_detection()
    _store_parameters(doc, job["parameters"])
    plates = _build_plates(doc, spec)
    doc.recompute()

    measurements = _measure(plates, spec)
    bom = _bom(plates, spec, material)
    flat_patterns = _write_flat_patterns(bom, meta, out_dir)
    dw.log("model, measurements and flat patterns done")
    drawing_result = _make_drawing(doc, plates, spec, material, meta, bom, measurements)

    step_path = os.path.join(out_dir, "hopper.step")
    Part.setStaticValue("write.step.schema", "AP242DIS")
    import Import

    Import.export([pl["obj"] for pl in plates], step_path)
    doc.saveAs(os.path.join(out_dir, "hopper.FCStd"))

    return {
        "measurements": measurements,
        "bom": [{k: v for k, v in item.items() if k != "plates"} for item in bom],
        "flat_patterns": flat_patterns,
        "drawing": drawing_result,
        "files": {
            "model": "hopper.FCStd",
            "step": "hopper.step",
            "drawing_pdf": "drawing.pdf",
            "flat_patterns": [fp["file"] for fp in flat_patterns],
        },
        "geometry_signature": _signature(plates),
    }


# --- model ---------------------------------------------------------------------------------


def _store_parameters(doc, p):
    """Readable copy of the parameters inside the native model (the job file is the source)."""
    sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
    for row, name in enumerate(sorted(p), start=1):
        sheet.set(f"A{row}", name)
        sheet.set(f"B{row}", "'" + str(p[name]))


def _build_plates(doc, spec):
    plates = []
    for panel in geo.panels(spec):
        pts = [V(*p) for p in panel.points]
        face = Part.Face(Part.makePolygon([*pts, pts[0]]))
        solid = face.extrude(V(*panel.normal) * spec.plate_thickness)
        obj = doc.addObject("Part::Feature", panel.name.replace("-", "_"))
        obj.Label = panel.name
        obj.Shape = solid
        plates.append({"name": panel.name, "obj": obj, "panel": panel})
    return plates


# --- measurements (taken from the model; the platform compares them with its own calculation) ----


def _inner_face(plate):
    panel = plate["panel"]
    n, p0 = V(*panel.normal), V(*panel.points[0])
    for face in plate["obj"].Shape.Faces:
        if abs(abs(face.normalAt(0, 0).dot(n)) - 1) < 1e-9 and abs((face.Vertexes[0].Point - p0).dot(n)) < 1e-6:
            return face
    raise RuntimeError(f"{panel.name}: inner face not found")


def _model_flat_contour(plate):
    """Flat pattern of the plate measured on the model: its inner face in the plate's own plane."""
    n = plate["panel"].normal
    face = _inner_face(plate)
    measured = geo.Panel(
        plate["name"], "", 0, tuple((v.Point.x, v.Point.y, v.Point.z) for v in face.OuterWire.OrderedVertexes), n
    )
    return geo.flat_contour(measured)


def _measure(plates, spec):
    shape = geo.inner_shape(spec)
    panels = {}
    for pl in plates:
        contour = _model_flat_contour(pl)
        width, height = geo.flat_size(contour)
        n = _inner_face(pl).normalAt(0, 0)
        panels[pl["name"]] = {
            "flat_size_mm": [round(width, 2), round(height, 2)],
            "flat_area_m2": round(geo.polygon_area(contour) / 1e6, 6),
            "slope_to_horizontal_deg": round(math.degrees(math.acos(min(1.0, abs(n.z)))), 4),
            "volume_m3": round(pl["obj"].Shape.Volume * 1e-9, 9),
        }
    compound = Part.makeCompound([pl["obj"].Shape for pl in plates])
    bb = compound.optimalBoundingBox()
    return {
        "panels": panels,
        "inner_top_mm": [round(shape.top_length, 2), round(shape.top_width, 2)],
        "slot_mm": [shape.slot_length, shape.slot_width],
        "side_wall_slope_deg": round(shape.side_wall_slope_deg(), 4),
        "end_wall_slope_deg": round(shape.end_wall_slope_deg(), 4),
        "valley_angle_deg": round(shape.valley_angle_deg(), 4),
        "capacity_m3": round(shape.capacity_m3(), 4),
        "overall_mm": [round(bb.XLength, 2), round(bb.YLength, 2), round(bb.ZLength, 2)],
        "solids_valid": all(pl["obj"].Shape.isValid() for pl in plates),
        "interferences": _interferences(plates),
    }


def _interferences(plates):
    """Pairs of plates whose solids overlap by more than 1 mm³ (they should at most touch)."""
    found = []
    for i, a in enumerate(plates):
        for b in plates[i + 1 :]:
            sa, sb = a["obj"].Shape, b["obj"].Shape
            if not sa.BoundBox.intersect(sb.BoundBox):
                continue
            volume = sa.common(sb).Volume
            if volume > 1.0:
                found.append({"plates": [a["name"], b["name"]], "volume_mm3": round(volume, 1)})
    return found


# --- BOM and flat patterns ---------------------------------------------------------------------


def _bom(plates, spec, material):
    """One BOM item per distinct flat pattern (mirror-identical panels share an item)."""
    groups = {}
    for pl in plates:
        contour = _model_flat_contour(pl)
        width, height = geo.flat_size(contour)
        key = (round(width, 1), round(height, 1), round(geo.polygon_area(contour), -2))
        groups.setdefault(key, []).append((pl, contour))
    items = []
    for (width, height, _), members in sorted(
        groups.items(), key=lambda kv: (kv[1][0][0]["panel"].tier, kv[1][0][0]["panel"].wall)
    ):
        first = members[0][0]
        panel = first["panel"]
        kind = "side" if panel.wall.startswith("Side") else "end"
        unit_mass = first["obj"].Shape.Volume * 1e-9 * material["density_kg_m3"]
        items.append(
            {
                "item": len(items) + 1,
                "mark": f"P{len(items) + 1}",
                "description": f"{kind.capitalize()} wall panel, tier {panel.tier}",
                "panels": [m[0]["name"] for m in members],
                "quantity": len(members),
                "thickness_mm": spec.plate_thickness,
                "flat_size_mm": [round(width, 1), round(height, 1)],
                "material": f"{material['designation']} {material['standard']}",
                "unit_mass_kg": round(unit_mass, 2),
                "total_mass_kg": round(unit_mass * len(members), 2),
                "contour": members[0][1],
            }
        )
    return items


def _write_flat_patterns(bom, meta, out_dir):
    results = []
    for item in bom:
        contour = item.pop("contour")
        file_name = f"flat_{item['mark']}.dxf"
        label = (
            f"{meta['drawing_number']} {item['mark']} QTY {item['quantity']} "
            f"T={item['thickness_mm']:g} {item['material']}"
        )
        dxf.write_flat_pattern(os.path.join(out_dir, file_name), [contour], [((10.0, -40.0), 25.0, label)])
        results.append(
            {"mark": item["mark"], "file": file_name, "contour": [[round(u, 3), round(v, 3)] for u, v in contour]}
        )
    return results


# --- drawing ---------------------------------------------------------------------------------

PARTS_LIST_HEADER = ["Item", "Mark", "Qty", "Description", "Plate", "Mass kg"]
PARTS_LIST_COLUMNS = [12.0, 14.0, 10.0, 80.0, 24.0, 22.0]


def _make_drawing(doc, plates, spec, material, meta, bom, m):
    sources = [pl["obj"] for pl in plates]
    ex, ey, ez = m["overall_mm"]
    iso_dir, iso_x = (1, -1, 1), (1, 1, 0)
    notes = _notes(spec, material, meta, m)
    rows = [
        [
            str(i["item"]),
            i["mark"],
            str(i["quantity"]),
            i["description"],
            f"PL {i['thickness_mm']:g}",
            f"{i['total_mass_kg']:.1f}",
        ]
        for i in bom
    ]
    panel_svg, panel_w, panel_h = pnl.side_panel_svg(PARTS_LIST_HEADER, rows, PARTS_LIST_COLUMNS, notes)
    layout = lay.plan_layout(
        front=(ex, ez),
        top=(ex, ey),
        side=(ey, ez),
        iso=lay.projected_size((ex, ey, ez), iso_dir, iso_x),
        side_panel=(panel_w, panel_h),
    )
    scale = 1.0 / layout.scale_denominator
    dw.log(f"layout {layout.sheet} {layout.scale_label}")
    page, template = dw.create_page(doc, layout.sheet)
    checks = dw.fill_title_block(
        template,
        {
            "title": meta["title"],
            "supplementary_title_1": meta["subtitle"],
            "supplementary_title_2": f"Template {TEMPLATE_ID} {VERSION}",
            "drawing_number": meta["drawing_number"],
            "revision_index": meta["revision"],
            "date_of_issue": meta["date"],
            "document_status": meta["status"],
            "document_type": "Weldment drawing",
            "creator": meta["author"],
            "approval_person": "-",
            "responsible_department": meta["department"],
            "scale": layout.scale_label,
            "general_tolerances": meta["general_tolerances"],
            "part_material": material["designation"],
            "language_code": "EN",
            "sheet_number": "1/1",
            "legal_owner_1": meta["owner"],
            "legal_owner_2": "",
            "legal_owner_3": "",
            "legal_owner_4": "",
        },
    )

    pv = layout.views
    views = {
        "front": dw.add_view(
            doc, page, "ViewFront", sources, (0, -1, 0), (1, 0, 0), scale, pv["front"].x, pv["front"].y
        ),
        "top": dw.add_view(doc, page, "ViewTop", sources, (0, 0, 1), (1, 0, 0), scale, pv["top"].x, pv["top"].y),
        "side": dw.add_view(doc, page, "ViewLeft", sources, (-1, 0, 0), (0, -1, 0), scale, pv["side"].x, pv["side"].y),
        "iso": dw.add_view(doc, page, "ViewIso", sources, iso_dir, iso_x, scale, pv["iso"].x, pv["iso"].y),
    }
    if not dw.wait_for_views(doc, list(views.values())):
        raise RuntimeError("TechDraw views were not computed in time")
    dw.log("views computed")

    shape = geo.inner_shape(spec)
    lt, wt = shape.top_length / 2, shape.top_width / 2
    ls, ws = shape.slot_length / 2, shape.slot_width / 2
    h, hv = spec.height, spec.end_wall_vertical_height
    top, front, side = views["top"], views["front"], views["side"]
    th, tw, fw, sw = pv["top"].height, pv["top"].width, pv["front"].width, pv["side"].width
    dims = [
        ("top_length_inside", "DistanceX", top, (-lt, wt, h), (lt, wt, h), 2 * lt, th / 2 + 8),
        ("top_width_inside", "DistanceY", top, (lt, -wt, h), (lt, wt, h), 2 * wt, tw / 2 + 8),
        ("slot_length_inside", "DistanceX", top, (-ls, -ws, 0), (ls, -ws, 0), 2 * ls, -th / 2 - 8),
        ("slot_width_inside", "DistanceY", top, (-ls, -ws, 0), (-ls, ws, 0), 2 * ws, -tw / 2 - 8),
        ("height", "DistanceY", front, (ls, -ws, 0), (lt, -wt, h), h, fw / 2 + 18),
    ]
    if hv > 0:
        dims.append(
            (
                "end_wall_vertical_height",
                "DistanceY",
                front,
                (ls, -ws, 0),
                (ls, -shape.half_width(hv), hv),
                hv,
                fw / 2 + 8,
            )
        )
    z = 0.0
    for tier, tier_height in enumerate(spec.tier_heights, start=1):
        a, b = (0.0, -shape.half_width(z), z), (0.0, -shape.half_width(z + tier_height), z + tier_height)
        dims.append((f"tier_{tier}_height", "DistanceY", side, a, b, tier_height, sw / 2 + 8))
        z += tier_height
    for name, kind, view, a, b, expected, offset in dims:
        checks.append(dw.add_distance(doc, page, view, name, kind, a, b, expected, offset))
    dw.log("dimensions added")

    panel = layout.side_panel
    symbol = doc.addObject("TechDraw::DrawViewSymbol", "PartsListAndNotes")
    symbol.Symbol = panel_svg
    page.addView(symbol)
    symbol.X, symbol.Y = (panel.x0 + panel.x1) / 2, (panel.y0 + panel.y1) / 2
    frame = lay.frame(layout.sheet)
    dw.add_text(doc, page, "StatusMark", [meta["status"]], (frame.x0 + frame.x1) / 2, frame.y1 - 7, 7.0)
    doc.recompute()

    checks += dw.view_checks(list(views.values()), layout.sheet, [lay.title_block(layout.sheet), panel])
    return {
        "sheet": layout.sheet,
        "scale": layout.scale_label,
        "projection": "first angle",
        "standard_profile": "ISO (EN ISO)",
        "notes": notes,
        "checks": checks,
    }


def _notes(spec, material, meta, m):
    notes = [
        "NOTES",
        "1. DIMENSIONS IN mm. INSIDE DIMENSIONS ON THE INNER PLATE SURFACE.",
        f"2. PLATES T={spec.plate_thickness:g} {material['designation']} {material['standard']}.",
        f"3. GENERAL TOLERANCES: {meta['general_tolerances']}.",
        f"4. GAP BETWEEN PANEL PLATES {spec.panel_gap:g} mm.",
        f"5. VALLEY ANGLE {m['valley_angle_deg']:.1f}°, WALL SLOPES {m['side_wall_slope_deg']:.1f}° (SIDE) / "
        f"{m['end_wall_slope_deg']:.1f}° (END).",
        f"6. CAPACITY {m['capacity_m3']:.1f} m³.",
        "7. STIFFENERS, BEAMS, BRACING, CORNER JOINTS AND WELDS NOT SHOWN.",
    ]
    # Standard notes come from the design basis (spec §12.8); never chosen by the template.
    notes += [f"{len(notes) + i}. {text}" for i, text in enumerate(meta.get("standard_notes", []))]
    return notes


def _signature(plates):
    """Geometry summary for repeatability comparison (F-6)."""
    data = []
    for pl in plates:
        s = pl["obj"].Shape
        bb = s.optimalBoundingBox()
        data.append(
            [
                pl["name"],
                round(s.Volume, 3),
                round(s.Area, 3),
                [round(x, 3) for x in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)],
            ]
        )
    return {"plates": data, "sha256": hashlib.sha256(repr(data).encode()).hexdigest()}
