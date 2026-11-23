"""Variant A: built-in objects only (VarSet, Sketcher, Part::Extrusion, expressions). Build, change, save."""

import os
import sys
import time

sys.path.insert(0, os.environ["SPIKE_DIR"])

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402

import common  # noqa: E402
import fchelp  # noqa: E402

V = App.Vector
C = Sketcher.Constraint

SIDE_SLANT = "sqrt(((Hopper.TopWidth - Hopper.SlotWidth) / 2) ^ 2 + Hopper.Height ^ 2)"
END_SLANT = "sqrt(((Hopper.TopLength - Hopper.SlotLength) / 2) ^ 2 + Hopper.Height ^ 2)"
SIDE_ANGLE = "atan2(Hopper.Height; (Hopper.TopWidth - Hopper.SlotWidth) / 2)"
END_ANGLE = "atan2(Hopper.Height; -(Hopper.TopLength - Hopper.SlotLength) / 2)"

# Candidate placement expressions, tried in order; the first that gives correct geometry is kept.
PLACEMENTS = {
    "side": [
        f"placement(vector(0 mm; Hopper.SlotWidth / 2; 0 mm); rotation(vector(1; 0; 0); {SIDE_ANGLE}))",
        f"placement(vector(0; Hopper.SlotWidth / 2; 0); rotation(vector(1; 0; 0); {SIDE_ANGLE}))",
    ],
    "end": [
        f"placement(vector(Hopper.SlotLength / 2; 0 mm; 0 mm); rotation(vector(0; 1; 0); {END_ANGLE}) * rotation(vector(0; 0; 1); 90 deg))",
        f"placement(vector(Hopper.SlotLength / 2; 0 mm; 0 mm); rotation(vector(0; 1; 0); {END_ANGLE}) * rotation(vector(0; 0; 1); 90))",
        f"placement(vector(Hopper.SlotLength / 2; 0; 0); rotation(vector(0; 1; 0); {END_ANGLE}) * rotation(vector(0; 0; 1); 90))",
    ],
}


def make_wall(doc, wall, name, bottom, top, slant):
    sk = doc.addObject("Sketcher::SketchObject", name + "Sketch")
    a, b, s = 1000.0, 2000.0, 3000.0  # start values; expressions set the real ones
    for p, q in (((-a, 0), (a, 0)), ((a, 0), (b, s)), ((-b, s), (b, s)), ((-a, 0), (-b, s))):
        sk.addGeometry(Part.LineSegment(V(*p, 0), V(*q, 0)))
    for c in (
        C("Coincident", 0, 2, 1, 1),
        C("Coincident", 1, 2, 2, 2),
        C("Coincident", 2, 1, 3, 2),
        C("Coincident", 3, 1, 0, 1),
        C("Symmetric", 0, 1, 0, 2, -2),
        C("Symmetric", 2, 1, 2, 2, -2),
        C("PointOnObject", 0, 1, -1),
    ):
        sk.addConstraint(c)
    for cname, c in (("bottom", C("DistanceX", 0, 1, 0, 2, 2 * a)), ("top", C("DistanceX", 2, 1, 2, 2, 2 * b)), ("slant", C("DistanceY", 0, 1, 2, 1, s))):
        sk.renameConstraint(sk.addConstraint(c), cname)
    sk.setExpression("Constraints.bottom", bottom)
    sk.setExpression("Constraints.top", top)
    sk.setExpression("Constraints.slant", slant)

    ext = doc.addObject("Part::Extrusion", name)
    ext.Base = sk
    ext.DirMode = "Normal"
    ext.Solid = True
    ext.setExpression("LengthFwd", "Hopper.Thickness")

    tried = []
    for expr in PLACEMENTS[wall]:
        try:
            sk.setExpression("Placement", expr)
        except Exception as exc:  # parse error
            tried.append({"expression": expr, "error": str(exc)})
            continue
        doc.recompute()
        result = fchelp.check_wall(doc, common.BASE, wall)
        tried.append({"expression": expr, "ok": result["ok"], "broken": fchelp.broken(doc)})
        if result["ok"]:
            return {"placement_expression": expr, "tried": tried, "dof": sk.solve()}
        sk.setExpression("Placement", None)
    return {"placement_expression": None, "tried": tried}


def main():
    result = {"freecad": ".".join(App.Version()[:3]), "variant": "builtin"}
    doc = App.newDocument("varset_builtin")
    vs = doc.addObject("App::VarSet", "Hopper")
    for name, value in common.BASE.items():
        vs.addProperty("App::PropertyLength", name, "Parameters")
        setattr(vs, name, value)

    result["side"] = make_wall(doc, "side", "SideWall", "Hopper.SlotLength", "Hopper.TopLength", SIDE_SLANT)
    result["end"] = make_wall(doc, "end", "EndWall", "Hopper.SlotWidth", "Hopper.TopWidth", END_SLANT)

    t0 = time.perf_counter()
    doc.recompute()
    result["base"] = fchelp.check(doc, common.BASE) | {"recompute_s": time.perf_counter() - t0}

    fchelp.set_params(vs, common.CHANGE_1)
    t0 = time.perf_counter()
    doc.recompute()
    result["change_1"] = fchelp.check(doc, common.BASE | common.CHANGE_1) | {"recompute_s": time.perf_counter() - t0}

    result["type_ids"] = sorted({o.TypeId for o in doc.Objects})
    path = os.path.join(common.OUT, "varset_builtin.FCStd")
    os.makedirs(common.OUT, exist_ok=True)
    doc.saveAs(path)
    result["saved"] = path
    common.write("builtin_build.json", result)


main()
