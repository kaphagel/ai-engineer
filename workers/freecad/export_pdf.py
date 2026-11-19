"""Second worker phase: export the drawing page of the saved model as PDF.

Runs in the FreeCAD GUI binary with QT_QPA_PLATFORM=offscreen, because PDF export exists only in
TechDrawGui (ADR-0001). Adds the export check to $IAIEP_JOB_DIR/out/result.json and saves the model
again, now including its GUI document.

The image must have FreeCAD's notification area disabled (configure_freecad.py); otherwise the GUI
deadlocks intermittently (ADR-0001, finding 9). In addition, as a precaution, this script never pumps
the event loop from Python: it works from timers in Qt's own event loop, computes the views one at a
time (TechDraw runs each view's hidden-line removal in a background thread when the GUI is up), and
exports only when every view has geometry.
"""

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide import QtCore

TIMEOUT_S = 180
POLL_MS = 500
SETTLE_MS = 1000

OUT_DIR = os.path.join(os.environ.get("IAIEP_JOB_DIR", "/job"), "out")
RESULT_PATH = os.path.join(OUT_DIR, "result.json")
_state = {}


def _log(message):
    sys.__stderr__.write(f"[iaiep-worker] export: {message}\n")
    sys.__stderr__.flush()


def _finish(check):
    with open(RESULT_PATH, encoding="utf-8") as fh:
        result = json.load(fh)
    result["drawing"]["checks"].append(check)
    with open(RESULT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    _log(check)
    os._exit(0 if check["status"] == "pass" else 1)


def _fail(exc):
    _log(traceback.format_exc())
    _finish({"id": "export.pdf", "status": "fail", "detail": f"{type(exc).__name__}: {exc}"})


def _start():
    try:
        import FreeCAD as App

        from iaiep_worker import drawing as dw

        dw.disable_face_detection()
        with open(RESULT_PATH, encoding="utf-8") as fh:
            files = json.load(fh)["files"]
        _state["pdf"] = os.path.join(OUT_DIR, files["drawing_pdf"])
        doc = App.openDocument(os.path.join(OUT_DIR, files["model"]))
        dw.use_millimetres(doc)  # dimension text is rendered at export
        page = doc.getObject("Drawing")
        _state.update(doc=doc, page=page, index=0, ready=True)
        _state["views"] = [v for v in page.Views if v.isDerivedFrom("TechDraw::DrawViewPart")]
        _state["deadline"] = time.time() + TIMEOUT_S
        timer = QtCore.QTimer()
        timer.timeout.connect(_poll)
        _state["timer"] = timer
        _compute_next_view()
    except Exception as exc:
        _fail(exc)


def _compute_next_view():
    """Start the hidden-line computation of the next view (one background thread at a time)."""
    view = _state["views"][_state["index"]]
    _log(f"computing {view.Name}")
    view.recompute()
    _state["timer"].start(POLL_MS)


def _poll():
    try:
        view = _state["views"][_state["index"]]
        done = bool(view.getVisibleEdges())
        if not done and time.time() < _state["deadline"]:
            return
        _state["timer"].stop()
        _state["ready"] = _state["ready"] and done
        _state["index"] += 1
        if done and _state["index"] < len(_state["views"]):
            QtCore.QTimer.singleShot(0, _compute_next_view)
        else:
            QtCore.QTimer.singleShot(0, _show_page)
    except Exception as exc:
        _fail(exc)


def _show_page():
    try:
        # Recompute only the dimensions and annotations; a document recompute would start the views again.
        views = _state["views"]
        for obj in _state["page"].Views:
            if obj not in views:
                obj.recompute()
        _log(f"touched views: {[v.Name for v in views if 'Touched' in v.State]}")
        _state["page"].ViewObject.show()
        _log("page shown")
        QtCore.QTimer.singleShot(SETTLE_MS, _export)
    except Exception as exc:
        _fail(exc)


def _export():
    try:
        import TechDrawGui

        _log("settled, checking views")
        path, views = _state["pdf"], _state["views"]
        # Exporting a page whose views are not computed silently gives a wrong PDF (ADR-0001).
        ready = _state["ready"] and all(v.getVisibleEdges() for v in views)
        _log(f"views ready: {ready}, exporting")
        if ready:
            TechDrawGui.exportPageAsPdf(_state["page"], path)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        ok = ready and size > 1000
        # Save again from the GUI, so that the file also contains the GUI document, like a file saved
        # by a user: it opens on the 3D model in an isometric view that fits the model, and the drawing
        # opens on double-click. (Saved by freecadcmd alone, the 3D camera showed a 4 mm field of view.)
        _set_isometric_camera(_state["doc"])
        _state["page"].ViewObject.hide()
        _state["doc"].save()
        _finish(
            {"id": "export.pdf", "status": "pass" if ok else "fail", "detail": f"{size} bytes, views ready: {ready}"}
        )
    except Exception as exc:
        _fail(exc)


def _set_isometric_camera(doc):
    """Isometric camera fitted to the model. Set explicitly: fitAll() needs a rendered scene."""
    import FreeCAD as App
    import FreeCADGui as Gui

    views = Gui.getDocument(doc.Name).mdiViewsOfType("Gui::View3DInventor")
    shapes = [o.Shape for o in doc.Objects if o.isDerivedFrom("Part::Feature") and not o.Shape.isNull()]
    if not views or not shapes:
        return
    box = shapes[0].BoundBox
    for shape in shapes[1:]:
        box.add(shape.BoundBox)
    centre, size = box.Center, box.DiagonalLength
    towards_viewer = App.Vector(1, -1, 1).normalize()
    right = App.Vector(0, 0, 1).cross(towards_viewer).normalize()
    up = towards_viewer.cross(right)
    rotation = App.Rotation(
        App.Matrix(
            right.x, up.x, towards_viewer.x, 0, right.y, up.y, towards_viewer.y, 0, right.z, up.z, towards_viewer.z, 0
        )
    )
    axis, position = rotation.Axis, centre + towards_viewer * (2 * size)
    views[0].setCamera(
        "#Inventor V2.1 ascii\nOrthographicCamera {\n viewportMapping ADJUST_CAMERA\n"
        f" position {position.x:.3f} {position.y:.3f} {position.z:.3f}\n"
        f" orientation {axis.x:.6f} {axis.y:.6f} {axis.z:.6f} {rotation.Angle:.6f}\n"
        f" nearDistance {size:.3f}\n farDistance {3 * size:.3f}\n aspectRatio 1\n"
        f" focalDistance {2 * size:.3f}\n height {1.1 * size:.3f}\n}}\n"
    )


QtCore.QTimer.singleShot(0, _start)
