"""Variant B: a scripted (FeaturePython) wall whose shape is computed in Python from its properties.

Self-contained on purpose: FreeCAD re-imports this module by name when a saved file is opened.
"""

import math

import FreeCAD as App
import Part

PARAMS = ("TopLength", "TopWidth", "SlotLength", "SlotWidth", "Height", "Thickness")


def corners(p, wall):
    L, W, l, w, H = p["TopLength"], p["TopWidth"], p["SlotLength"], p["SlotWidth"], p["Height"]
    if wall == "side":
        return [(-l / 2, w / 2, 0.0), (l / 2, w / 2, 0.0), (L / 2, W / 2, H), (-L / 2, W / 2, H)]
    return [(l / 2, -w / 2, 0.0), (l / 2, w / 2, 0.0), (L / 2, W / 2, H), (L / 2, -W / 2, H)]


class Wall:
    def __init__(self, obj, wall):
        for name in PARAMS:
            obj.addProperty("App::PropertyLength", name, "Parameters")
        obj.addProperty("App::PropertyString", "Wall", "Parameters")
        obj.Wall = wall
        obj.Proxy = self

    def execute(self, obj):
        p = {name: getattr(obj, name).Value for name in PARAMS}
        pts = [App.Vector(*c) for c in corners(p, obj.Wall)]
        face = Part.Face(Part.makePolygon([*pts, pts[0]]))
        normal = face.normalAt(0, 0)
        if not math.isfinite(normal.Length) or normal.Length == 0:
            raise ValueError("degenerate wall")
        obj.Shape = face.extrude(normal * p["Thickness"])

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads
