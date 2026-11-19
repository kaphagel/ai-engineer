"""Phase 0 spike: headless FreeCAD parametric part + TechDraw drawing + exports.

Run inside the spike container:
    freecadcmd spike_hopper.py            (writes to /work/out)

Throw-away code (spec §25, Phase 0). Results are recorded in doc/adr/0001.
"""

import hashlib
import json
import os
import sys
import time

import FreeCAD as App
import Import
import Part
import Sketcher
import TechDraw

OUT = os.environ.get("SPIKE_OUT", "/work/out")
os.makedirs(OUT, exist_ok=True)
results = {"freecad_version": ".".join(App.Version()[:3]), "python": sys.version.split()[0], "steps": {}}


def step(name, ok, **info):
    results["steps"][name] = {"ok": bool(ok), **info}
    print(f"[{'OK' if ok else 'FAIL'}] {name} {info if info else ''}", flush=True)


# --- 1. Parametric model driven by a spreadsheet -------------------------------------------
doc = App.newDocument("HopperSpike")
sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")
params = {  # synthetic values, mm
    "top_length": 6000, "top_width": 4000,
    "outlet_length": 400, "outlet_width": 400,
    "height": 3500, "plate_thickness": 6,
}
for row, (name, value) in enumerate(params.items(), start=1):
    sheet.set(f"A{row}", name)
    sheet.set(f"B{row}", f"={value} mm")
    sheet.setAlias(f"B{row}", name)


def rectangle_sketch(name, length_alias, width_alias, z_expr):
    sk = doc.addObject("Sketcher::SketchObject", name)
    p = [App.Vector(-1, -1, 0), App.Vector(1, -1, 0), App.Vector(1, 1, 0), App.Vector(-1, 1, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(p[i], p[(i + 1) % 4]), False)
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 2))
    sk.addConstraint(Sketcher.Constraint("Vertical", 1))
    sk.addConstraint(Sketcher.Constraint("Vertical", 3))
    sk.addConstraint(Sketcher.Constraint("Symmetric", 0, 1, 1, 2, -1, 1))  # centred on origin
    c_len = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 2))
    c_wid = sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 2))
    sk.setExpression(f"Constraints[{c_len}]", f"Parameters.{length_alias}")
    sk.setExpression(f"Constraints[{c_wid}]", f"Parameters.{width_alias}")
    sk.setExpression(".Placement.Base.z", z_expr)
    return sk


outlet = rectangle_sketch("OutletProfile", "outlet_length", "outlet_width", "0 mm")
top = rectangle_sketch("TopProfile", "top_length", "top_width", "Parameters.height")

loft = doc.addObject("Part::Loft", "HopperSolid")
loft.Sections = [outlet, top]
loft.Solid = True
loft.Ruled = True
doc.recompute()

cap_faces = [f"Face{i + 1}" for i, f in enumerate(loft.Shape.Faces)
             if abs(abs(f.normalAt(0, 0).z) - 1.0) < 1e-9]
shell = doc.addObject("Part::Thickness", "Hopper")
shell.Faces = (loft, cap_faces)
shell.setExpression("Value", "-Parameters.plate_thickness")  # material inside the profile
shell.Join = "Arc"  # "Intersection" fails on the ruled loft (spike finding)
loft.Visibility = False
doc.recompute()

bb = shell.Shape.optimalBoundingBox()  # .BoundBox is not tight on curved faces
step("model_built", shell.Shape.isValid() and shell.Shape.Volume > 0,
     volume_m3=round(shell.Shape.Volume / 1e9, 4), bbox_mm=[round(bb.XLength), round(bb.YLength), round(bb.ZLength)],
     cap_faces_removed=cap_faces)

# --- 2. Parametric change + regeneration ----------------------------------------------------
sheet.set("B5", "=4000 mm")  # height 3500 -> 4000
doc.recompute()
new_z = round(shell.Shape.optimalBoundingBox().ZLength)
step("parametric_regeneration", new_z == 4000, new_height_mm=new_z)

# Valley angle (angle of the hopper corner edge to the horizontal): a pure-geometry check.
corner_edges = [e for e in loft.Shape.Edges if abs(e.Vertexes[0].Z - e.Vertexes[-1].Z) > 1]
d = corner_edges[0].Vertexes[-1].Point - corner_edges[0].Vertexes[0].Point
import math
valley = math.degrees(math.atan2(abs(d.z), math.hypot(d.x, d.y)))
step("geometry_check_valley_angle", 0 < valley < 90, valley_angle_deg=round(valley, 2))

# --- 3. TechDraw page: ISO A3 template, first-angle projection, title block --------------
tpl_path = os.path.join(App.getResourceDir(), "Mod/TechDraw/Templates/ISO/A3_Landscape_ISO5457_advanced.svg")
page = doc.addObject("TechDraw::DrawPage", "Drawing")
template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
template.Template = tpl_path
page.Template = template
page.ProjectionType = "First angle"

texts = template.EditableTexts
texts.update({
    "title": "ESP HOPPER - SPIKE",
    "supplementary_title_1": "Synthetic data",
    "drawing_number": "P0000-ESP-HOP-DWG-0001",
    "revision_index": "A",
    "date_of_issue": "2026-11-18",
    "document_status": "DRAFT - NOT FOR FABRICATION",
    "document_type": "Assembly drawing",
    "creator": "iaiep-spike",
    "approval_person": "-",
    "scale": "1:50",
    "general_tolerances": "ISO 13920-BF",
    "part_material": "S355J2 (synthetic)",
    "language_code": "en",
    "sheet_number": "1/1",
})
template.EditableTexts = texts

group = doc.addObject("TechDraw::DrawProjGroup", "Views")
page.addView(group)
group.Source = [shell]
group.ScaleType = "Custom"
group.Scale = 1 / 50
group.ProjectionType = "First angle"
group.addProjection("Front")
group.addProjection("Top")
group.addProjection("Right")
group.X, group.Y = 150, 160

iso = doc.addObject("TechDraw::DrawViewPart", "Isometric")
page.addView(iso)
iso.Source = [shell]
iso.Direction = App.Vector(1, -1, 1)
iso.ScaleType = "Custom"
iso.Scale = 1 / 80
iso.X, iso.Y = 330, 200

t0 = time.time()
doc.recompute()
front = next(v for v in group.Views if v.Type == "Front")


def wait_for_edges(view, timeout=30):
    """TechDraw may compute hidden-line removal in a background thread."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            edges = view.getVisibleEdges()
        except Exception:
            edges = []
        if edges:
            return edges
        time.sleep(0.5)
        doc.recompute()
    return []


edges = wait_for_edges(front)
step("techdraw_views_computed", len(edges) > 0, front_visible_edges=len(edges), seconds=round(time.time() - t0, 1))

# Overall top length dimension on the front view: the longest horizontal edge.
dim_ok = False
try:
    horiz = [(i, e) for i, e in enumerate(edges) if abs(e.Vertexes[0].Y - e.Vertexes[-1].Y) < 1e-6]
    idx, _ = max(horiz, key=lambda ie: ie[1].Length)
    dim = doc.addObject("TechDraw::DrawViewDimension", "DimTopLength")
    dim.Type = "DistanceX"
    dim.References2D = [(front, f"Edge{idx}")]
    page.addView(dim)
    doc.recompute()
    dim_ok = abs(dim.getRawValue() - 6000) < 0.5
    step("techdraw_dimension", dim_ok, value_mm=round(dim.getRawValue(), 1), edge=f"Edge{idx}")
except Exception as e:
    step("techdraw_dimension", False, error=repr(e))

# --- 4. Exports ----------------------------------------------------------------------------
def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


fcstd = os.path.join(OUT, "hopper.FCStd")
doc.saveAs(fcstd)
step("save_fcstd", os.path.getsize(fcstd) > 0, bytes=os.path.getsize(fcstd))

Part.setStaticValue("write.step.schema", "AP242DIS")
step_path = os.path.join(OUT, "hopper.step")
Import.export([shell], step_path)
with open(step_path, errors="ignore") as fh:
    header = fh.read(4000)
schema = next((l.strip() for l in header.splitlines() if "FILE_SCHEMA" in l), "")
step("export_step", os.path.getsize(step_path) > 0, schema=schema[:90])

# SVG/PDF page export exists only in TechDrawGui (GUI module); see export_gui.py.

dxf_path = os.path.join(OUT, "drawing.dxf")
try:
    TechDraw.writeDXFPage(page, dxf_path)
    dxf_text = open(dxf_path, errors="ignore").read()
    step("export_dxf_page", os.path.getsize(dxf_path) > 1000, bytes=os.path.getsize(dxf_path),
         contains_title_block=("P0000-ESP-HOP-DWG-0001" in dxf_text), contains_dimension=("6000" in dxf_text))
except Exception as e:
    step("export_dxf_page", False, error=repr(e))

bb = shell.Shape.optimalBoundingBox()
results["geometry_signature"] = {
    "volume_mm3": round(shell.Shape.Volume, 3),
    "area_mm2": round(shell.Shape.Area, 3),
    "bbox": [round(v, 3) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)],
}
with open(os.path.join(OUT, "results.json"), "w") as fh:
    json.dump(results, fh, indent=2)
print("RESULTS_WRITTEN", flush=True)
