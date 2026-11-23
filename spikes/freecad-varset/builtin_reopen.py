"""Variant A: reopen the saved file in a fresh process, check it, change parameters, recompute, check."""

import os
import sys
import time

sys.path.insert(0, os.environ["SPIKE_DIR"])

import FreeCAD as App  # noqa: E402

import common  # noqa: E402
import fchelp  # noqa: E402


def main():
    result = {"variant": "builtin"}
    doc = App.openDocument(os.path.join(common.OUT, "varset_builtin.FCStd"))
    before = common.BASE | common.CHANGE_1
    result["as_opened"] = fchelp.check(doc, before)

    fchelp.set_params(doc.getObject("Hopper"), common.CHANGE_2)
    t0 = time.perf_counter()
    doc.recompute()
    result["change_2"] = fchelp.check(doc, before | common.CHANGE_2) | {"recompute_s": time.perf_counter() - t0}
    common.write("builtin_reopen.json", result)


main()
