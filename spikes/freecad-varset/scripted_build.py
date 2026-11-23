"""Variant B: scripted walls bound to the VarSet by expressions. Build, change, save."""

import os
import sys
import time

sys.path.insert(0, os.environ["SPIKE_DIR"])
sys.path.insert(0, os.path.join(os.environ["SPIKE_DIR"], "feature"))

import FreeCAD as App  # noqa: E402

import common  # noqa: E402
import fchelp  # noqa: E402
import plate_feature  # noqa: E402


def main():
    result = {"freecad": ".".join(App.Version()[:3]), "variant": "scripted"}
    doc = App.newDocument("varset_scripted")
    vs = doc.addObject("App::VarSet", "Hopper")
    for name, value in common.BASE.items():
        vs.addProperty("App::PropertyLength", name, "Parameters")
        setattr(vs, name, value)
    for wall, name in fchelp.WALLS.items():
        obj = doc.addObject("Part::FeaturePython", name)
        plate_feature.Wall(obj, wall)
        for param in plate_feature.PARAMS:
            obj.setExpression(param, f"Hopper.{param}")

    t0 = time.perf_counter()
    doc.recompute()
    result["base"] = fchelp.check(doc, common.BASE) | {"recompute_s": time.perf_counter() - t0}

    fchelp.set_params(vs, common.CHANGE_1)
    t0 = time.perf_counter()
    doc.recompute()
    result["change_1"] = fchelp.check(doc, common.BASE | common.CHANGE_1) | {"recompute_s": time.perf_counter() - t0}

    result["type_ids"] = sorted({o.TypeId for o in doc.Objects})
    path = os.path.join(common.OUT, "varset_scripted.FCStd")
    os.makedirs(common.OUT, exist_ok=True)
    doc.saveAs(path)
    result["saved"] = path
    common.write("scripted_build.json", result)


main()
