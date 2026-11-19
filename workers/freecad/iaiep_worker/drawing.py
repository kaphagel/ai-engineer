"""TechDraw helpers shared by templates: sheet, title block, views, dimensions and drawing checks.

Run in freecadcmd (no GUI). The PDF is exported separately by export_pdf.py in the GUI binary.

ADR-0001 findings applied here: views are computed in background threads and must be awaited
before export, and an export that reports success is not proof of a correct drawing, so the
drawing is checked explicitly.
"""

import math
import os
import sys
import time

import FreeCAD as App

from iaiep_worker import layout as lay


def log(message):
    """Progress log. The GUI binary redirects print() to its report view, so write to the real stderr."""
    sys.__stderr__.write(f"[iaiep-worker] {message}\n")
    sys.__stderr__.flush()


POINT_TOLERANCE = 0.5  # mm, model units
DIMENSION_TOLERANCE = 0.01  # mm

# Title block fields that must contain a value.
REQUIRED_TITLE_FIELDS = (
    "title",
    "drawing_number",
    "revision_index",
    "date_of_issue",
    "document_status",
    "document_type",
    "creator",
    "scale",
    "general_tolerances",
    "part_material",
    "sheet_number",
    "language_code",
)


def template_path(sheet):
    return os.path.join(App.getResourceDir(), f"Mod/TechDraw/Templates/ISO/{sheet}_Landscape_ISO5457_advanced.svg")


def create_page(doc, sheet):
    template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    template.Template = template_path(sheet)
    page = doc.addObject("TechDraw::DrawPage", "Drawing")
    page.Template = template
    page.ProjectionType = "First angle"
    return page, template


def fill_title_block(template, fields):
    """Set every editable field explicitly. Returns check results."""
    defaults = dict(template.EditableTexts)
    texts = dict(defaults)
    unknown = sorted(set(fields) - set(defaults))
    texts.update({k: v for k, v in fields.items() if k in defaults})
    template.EditableTexts = texts
    filled = dict(template.EditableTexts)
    checks = [
        _check(
            "title_block.fields_known", not unknown, f"unknown fields: {unknown}" if unknown else "all fields known"
        ),
    ]
    unset = sorted(k for k in defaults if k not in fields)
    checks.append(_check("title_block.all_fields_set", not unset, f"not set: {unset}" if unset else "all fields set"))
    empty = sorted(k for k in REQUIRED_TITLE_FIELDS if not str(filled.get(k, "")).strip())
    checks.append(
        _check("title_block.required_filled", not empty, f"empty: {empty}" if empty else "all required filled")
    )
    mismatch = sorted(k for k, v in fields.items() if k in filled and filled[k] != v)
    checks.append(_check("title_block.matches_metadata", not mismatch, f"mismatch: {mismatch}" if mismatch else "ok"))
    return checks


def add_view(doc, page, name, sources, direction, x_direction, scale, x, y):
    view = doc.addObject("TechDraw::DrawViewPart", name)
    page.addView(view)
    view.Source = sources
    view.Direction = App.Vector(*direction)
    view.XDirection = App.Vector(*x_direction)
    view.ScaleType = "Custom"
    view.Scale = scale
    view.X, view.Y = x, y
    return view


def wait_for_views(doc, views, timeout=120.0):
    """Recompute until every view has visible edges (freecadcmd, no GUI). Returns False on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        doc.recompute()
        if all(_safe_edges(v) for v in views):
            return True
        time.sleep(0.2)
    return False


def view_vertices(view):
    count = len(view.getVisibleVertexes()) + len(view.getHiddenVertexes())
    return [(i, view.getVertexByIndex(i).Point) for i in range(count)]


def find_vertex(view, point):
    """Name of the view vertex at the projection of a 3D model point (cosmetic if hidden), or None."""
    centre = view.projectPoint(view.getGeometricCenter())
    target = view.projectPoint(App.Vector(*point)) - centre
    best = None
    for index, p in view_vertices(view):
        distance = math.hypot(p.x - target.x, p.y - target.y)
        if best is None or distance < best[0]:
            best = (distance, index)
    if best is not None and best[0] <= POINT_TOLERANCE:
        return f"Vertex{best[1]}"
    # The point is hidden behind other parts (only visible vertices exist): add a cosmetic vertex there.
    # Cosmetic vertices use the same view coordinates and are appended to the vertex list.
    index = len(view_vertices(view))
    view.makeCosmeticVertex(target)
    view.recompute()
    p = view.getVertexBySelection(f"Vertex{index}").Point
    if math.hypot(p.x - target.x, p.y - target.y) > POINT_TOLERANCE:
        return None
    return f"Vertex{index}"


def disable_face_detection():
    """Skip TechDraw's face finding: it only serves hatching (not used) and adds a background thread
    per view when the GUI is up. Also set in the image (configure_freecad.py)."""
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/General").SetBool("HandleFaces", False)


def use_millimetres(doc=None):
    """Show all lengths in mm. The default unit schema switches to metres for large values.

    FreeCAD 1.x also stores a unit system per document, which the GUI applies when it opens the file.
    """
    index = App.Units.listSchemas().index("MmMin")
    App.Units.setSchema(index)
    App.ParamGet("User parameter:BaseApp/Preferences/Units").SetInt("UserSchema", index)
    if doc is not None and "UnitSystem" in doc.PropertiesList:
        doc.UnitSystem = doc.getEnumerationsOfProperty("UnitSystem")[index]


def add_distance(doc, page, view, name, kind, point_a, point_b, expected, offset):
    """Dimension between two model points; returns a check result.

    `offset` is the distance of the dimension line from the view centre (paper mm), perpendicular to
    the measured direction; along it, the text is centred between the two points.
    """
    vertices = [find_vertex(view, point_a), find_vertex(view, point_b)]
    if None in vertices:
        return _check(f"dimension.{name}", False, f"vertices not found in view {view.Name}: {vertices}")
    dim = doc.addObject("TechDraw::DrawViewDimension", f"Dim_{name}")
    dim.Type = kind
    dim.References2D = [(view, vertices[0]), (view, vertices[1])]
    dim.MeasureType = "Projected"
    dim.FormatSpec = "%.0f"
    page.addView(dim)
    a, b = (view.getVertexBySelection(v).Point for v in vertices)
    s = view.Scale
    if kind == "DistanceY":
        dim.X, dim.Y = offset, (a.y + b.y) / 2 * s
    else:
        dim.X, dim.Y = (a.x + b.x) / 2 * s, offset
    doc.recompute()
    value = dim.getRawValue()
    ok = abs(value - expected) <= DIMENSION_TOLERANCE
    return _check(f"dimension.{name}", ok, f"{value:.3f} mm (expected {expected:.3f})", value=round(value, 3))


def add_text(doc, page, name, lines, x, y, size):
    note = doc.addObject("TechDraw::DrawViewAnnotation", name)
    page.addView(note)
    note.Text = lines
    note.TextSize = size
    note.X, note.Y = x, y
    return note


def view_checks(views, sheet, reserved):
    """Every view has geometry, lies inside the frame and stays clear of the reserved areas."""
    checks = []
    usable = lay.frame(sheet)
    for view in views:
        edges = _safe_edges(view)
        checks.append(_check(f"view.{view.Name}.has_geometry", bool(edges), f"{len(edges)} visible edges"))
        points = [p for _, p in view_vertices(view)]
        if not points:
            checks.append(_check(f"view.{view.Name}.inside_frame", False, "no vertices"))
            continue
        s, x, y = view.Scale, _mm(view.X), _mm(view.Y)
        rect = lay.Rect(
            x + min(p.x for p in points) * s,
            y + min(p.y for p in points) * s,
            x + max(p.x for p in points) * s,
            y + max(p.y for p in points) * s,
        )
        inside = rect.inside(usable)
        clear = not any(rect.overlaps(r) for r in reserved)
        detail = f"x {rect.x0:.1f}..{rect.x1:.1f}, y {rect.y0:.1f}..{rect.y1:.1f} mm"
        checks.append(_check(f"view.{view.Name}.inside_frame", inside, detail))
        checks.append(_check(f"view.{view.Name}.clear_of_title_block_and_lists", clear, detail))
    return checks


def _mm(value):
    """Plain float from a FreeCAD length property (Quantity) or a number."""
    return float(getattr(value, "Value", value))


def _safe_edges(view):
    try:
        return view.getVisibleEdges()
    except Exception:
        return []


def _check(check_id, ok, detail, **extra):
    return {"id": check_id, "status": "pass" if ok else "fail", "detail": detail, **extra}
