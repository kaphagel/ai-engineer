"""Variant B: reopen the saved file, with or without the feature module on the path (SPIKE_WITH_MODULE)."""

import os
import sys
import time

sys.path.insert(0, os.environ["SPIKE_DIR"])
with_module = os.environ.get("SPIKE_WITH_MODULE", "1") == "1"
if with_module:
    sys.path.insert(0, os.path.join(os.environ["SPIKE_DIR"], "feature"))

import FreeCAD as App  # noqa: E402

import common  # noqa: E402
import fchelp  # noqa: E402


def main():
    result = {"variant": "scripted", "with_module": with_module}
    try:
        import plate_feature  # noqa: F401

        result["module_importable"] = True
    except ImportError:
        result["module_importable"] = False

    doc = App.openDocument(os.path.join(common.OUT, "varset_scripted.FCStd"))
    before = common.BASE | common.CHANGE_1
    result["as_opened"] = fchelp.check(doc, before)
    result["proxies"] = {name: repr(getattr(doc.getObject(name), "Proxy", None)) for name in fchelp.WALLS.values()}

    fchelp.set_params(doc.getObject("Hopper"), common.CHANGE_2)
    t0 = time.perf_counter()
    doc.recompute()
    result["change_2"] = fchelp.check(doc, before | common.CHANGE_2) | {"recompute_s": time.perf_counter() - t0}
    name = "scripted_reopen.json" if with_module else "scripted_reopen_nomodule.json"
    common.write(name, result)


main()
