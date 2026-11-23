"""FreeCAD-side checks for the VarSet spike: geometry of both walls against the independent calculation."""

import common

WALLS = {"side": "SideWall", "end": "EndWall"}


def broken(doc):
    return [f"{o.Name}: {','.join(o.State)}" for o in doc.Objects if "Invalid" in o.State or "Error" in o.State]


def check_wall(doc, p, wall):
    obj = doc.getObject(WALLS[wall])
    shape = obj.Shape
    points = [tuple(v.Point) for v in shape.Vertexes]
    deviation = common.match_points(points, common.corners(p, wall)) if points else None
    expected = common.volume(p, wall)
    volume = shape.Volume if not shape.isNull() else 0.0
    ok = (
        deviation is not None
        and deviation < common.TOL_MM
        and abs(volume - expected) <= 1e-6 * expected
        and shape.isValid()
        and len(shape.Solids) == 1
    )
    return {
        "ok": ok,
        "corner_deviation_mm": deviation,
        "volume_mm3": volume,
        "expected_volume_mm3": expected,
        "valid": shape.isValid() if not shape.isNull() else False,
    }


def check(doc, p):
    walls = {wall: check_wall(doc, p, wall) for wall in WALLS}
    errors = broken(doc)
    return {"ok": all(w["ok"] for w in walls.values()) and not errors, "walls": walls, "broken_objects": errors}


def set_params(vs, values):
    for name, value in values.items():
        setattr(vs, name, value)
