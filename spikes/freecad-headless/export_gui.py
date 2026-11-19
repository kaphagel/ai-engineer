"""Phase 0 spike: export the TechDraw page as PDF and SVG using the FreeCAD GUI without a real display.

Run:  freecad export_gui.py   (with QT_QPA_PLATFORM=offscreen, or under xvfb-run)
"""
import json
import os

import FreeCAD as App
import FreeCADGui as Gui

OUT = os.environ.get("SPIKE_OUT", "/work/out")
res = {}
try:
    import TechDrawGui

    doc = App.openDocument(os.path.join(OUT, "hopper.FCStd"))
    doc.recompute()
    page = doc.getObject("Drawing")
    page.ViewObject.show()  # create the page scene, as an interactive user would

    # Hidden-line removal runs in background threads that report back through the Qt event loop.
    import time
    views = [v for v in page.Views if v.isDerivedFrom("TechDraw::DrawViewPart")]
    for v in page.Views:
        if v.isDerivedFrom("TechDraw::DrawProjGroup"):
            views += list(v.Views)
    deadline = time.time() + 60
    while time.time() < deadline:
        Gui.updateGui()
        if all(v.getVisibleEdges() for v in views):
            break
        time.sleep(0.2)
    for _ in range(20):
        Gui.updateGui()
        time.sleep(0.05)
    res["views_ready"] = {v.Name: len(v.getVisibleEdges()) for v in views}
    for kind, fn in (("pdf", TechDrawGui.exportPageAsPdf), ("svg", TechDrawGui.exportPageAsSvg)):
        path = os.path.join(OUT, f"drawing.{kind}")
        try:
            fn(page, path)
            res[kind] = {"ok": os.path.exists(path) and os.path.getsize(path) > 1000,
                         "bytes": os.path.getsize(path) if os.path.exists(path) else 0}
        except Exception as e:
            res[kind] = {"ok": False, "error": repr(e)}
except Exception as e:
    res["error"] = repr(e)
with open(os.path.join(OUT, f"gui_results_{os.environ.get('QT_QPA_PLATFORM', 'xcb')}.json"), "w") as fh:
    json.dump(res, fh, indent=2)
print("GUI_RESULTS", res, flush=True)
os._exit(0)
