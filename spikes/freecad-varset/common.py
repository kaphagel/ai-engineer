"""Shared parameters and independent geometry for the VarSet spike (plain Python, no FreeCAD)."""

import json
import math
import os

OUT = os.environ.get("SPIKE_OUT", "/tmp/out")
TOL_MM = 1e-3

# Synthetic values (same order of size as domains/esp/examples/hopper_synthetic.toml).
BASE = {"TopLength": 8000.0, "TopWidth": 3800.0, "SlotLength": 6500.0, "SlotWidth": 400.0, "Height": 4200.0, "Thickness": 5.0}
CHANGE_1 = {"Height": 3000.0, "TopWidth": 4200.0, "SlotLength": 6000.0}
CHANGE_2 = {"TopLength": 9000.0, "SlotWidth": 600.0, "Thickness": 8.0}


def corners(p, wall):
    """Corners of the wall's sketch face (outer plate surface not modelled): bottom edge at z=0, top at z=H."""
    L, W, l, w, H = p["TopLength"], p["TopWidth"], p["SlotLength"], p["SlotWidth"], p["Height"]
    if wall == "side":
        return [(-l / 2, w / 2, 0.0), (l / 2, w / 2, 0.0), (L / 2, W / 2, H), (-L / 2, W / 2, H)]
    return [(l / 2, -w / 2, 0.0), (l / 2, w / 2, 0.0), (L / 2, W / 2, H), (L / 2, -W / 2, H)]


def volume(p, wall):
    L, W, l, w, H, t = (p[k] for k in ("TopLength", "TopWidth", "SlotLength", "SlotWidth", "Height", "Thickness"))
    if wall == "side":
        slant = math.hypot((W - w) / 2, H)
        return (L + l) / 2 * slant * t
    slant = math.hypot((L - l) / 2, H)
    return (W + w) / 2 * slant * t


def match_points(actual, expected):
    """Largest distance from each expected point to its nearest actual point."""
    return max(min(math.dist(e, a) for a in actual) for e in expected)


def write(name, result):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
