"""Sheet, scale and view placement for ISO 5457 sheets (pure Python, no FreeCAD).

Coordinates are paper millimetres with the origin at the bottom-left sheet corner (TechDraw convention).
Views are arranged in first-angle projection (ISO 5456-2): the top view below the front view, the view
from the left to the right of the front view.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

SHEETS: dict[str, tuple[float, float]] = {
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}
# ISO 5455 preferred reduction scales, 1:n.
SCALE_DENOMINATORS = (1, 2, 5, 10, 20, 50, 100, 200)

FRAME_LEFT = 20.0  # filing margin
FRAME_OTHER = 10.0
# Title block of FreeCAD's ISO 5457 "advanced" templates, including the projection symbol.
TITLE_BLOCK_WIDTH = 182.0
TITLE_BLOCK_HEIGHT = 70.0
STATUS_STRIP_HEIGHT = 14.0  # top strip for the "DRAFT" status marking
DIMENSION_MARGIN = 15.0  # space around orthographic views for dimensions
GAP = 8.0


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def centred(cls, x: float, y: float, width: float, height: float, margin: float = 0.0) -> "Rect":
        return cls(x - width / 2 - margin, y - height / 2 - margin, x + width / 2 + margin, y + height / 2 + margin)

    def inside(self, other: "Rect") -> bool:
        eps = 1e-6  # views are placed exactly against the frame; ignore rounding
        return (
            self.x0 >= other.x0 - eps
            and self.y0 >= other.y0 - eps
            and self.x1 <= other.x1 + eps
            and self.y1 <= other.y1 + eps
        )

    def overlaps(self, other: "Rect") -> bool:
        return self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1


@dataclass(frozen=True)
class Placement:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Layout:
    sheet: str
    scale_denominator: int
    views: dict[str, Placement]
    side_panel: Rect  # area above the title block for the parts list and notes

    @property
    def scale_label(self) -> str:
        return f"1:{self.scale_denominator}"


def frame(sheet: str) -> Rect:
    width, height = SHEETS[sheet]
    return Rect(FRAME_LEFT, FRAME_OTHER, width - FRAME_OTHER, height - FRAME_OTHER)


def title_block(sheet: str) -> Rect:
    width, _ = SHEETS[sheet]
    return Rect(
        width - FRAME_OTHER - TITLE_BLOCK_WIDTH, FRAME_OTHER, width - FRAME_OTHER, FRAME_OTHER + TITLE_BLOCK_HEIGHT
    )


def projected_size(
    extents: tuple[float, float, float], direction: tuple[float, float, float], x_direction: tuple[float, float, float]
) -> tuple[float, float]:
    """Width and height of an axis-aligned box of the given extents, projected along `direction`."""
    d = _unit(direction)
    u = _unit(x_direction)
    v = _cross(d, u)
    corners = [(x, y, z) for x in (0.0, extents[0]) for y in (0.0, extents[1]) for z in (0.0, extents[2])]
    us = [_dot(c, u) for c in corners]
    vs = [_dot(c, v) for c in corners]
    return max(us) - min(us), max(vs) - min(vs)


def plan_layout(
    front: tuple[float, float],
    top: tuple[float, float],
    side: tuple[float, float],
    iso: tuple[float, float],
    side_panel: tuple[float, float],
    max_sheet: str = "A1",
    margins: Mapping[str, float] | None = None,
) -> Layout:
    """Choose the largest preferred scale at which all views fit on a sheet up to `max_sheet`,
    using the smallest such sheet. Falls back to larger sheets only if nothing fits.

    View sizes are in model millimetres. `side_panel` (width, height) is reserved above the title block.
    `margins` (paper mm) is the space kept around the front, top and side views for their dimensions.
    """
    m = {name: DIMENSION_MARGIN for name in ("front", "top", "side")} | dict(margins or {})
    sheets = list(SHEETS)
    allowed = sheets[: sheets.index(max_sheet) + 1]
    for group in (allowed, sheets[len(allowed) :]):
        for denominator in SCALE_DENOMINATORS:
            for sheet in group:
                layout = _try_layout(sheet, denominator, front, top, side, iso, side_panel, m)
                if layout is not None:
                    return layout
    raise ValueError("The views do not fit on any sheet up to A0 at scale 1:200")


def _try_layout(
    sheet: str,
    denominator: int,
    front: tuple[float, float],
    top: tuple[float, float],
    side: tuple[float, float],
    iso: tuple[float, float],
    side_panel: tuple[float, float],
    margins: Mapping[str, float],
) -> Layout | None:
    s = 1.0 / denominator
    fw, fh = front[0] * s, front[1] * s
    tw, th = top[0] * s, top[1] * s
    sw, sh = side[0] * s, side[1] * s
    iw, ih = iso[0] * s, iso[1] * s
    mf, mt, ms = margins["front"], margins["top"], margins["side"]
    column_margin, row_margin = max(mf, mt), max(mf, ms)

    fr = frame(sheet)
    usable = Rect(fr.x0, fr.y0, fr.x1, fr.y1 - STATUS_STRIP_HEIGHT)
    tb = title_block(sheet)
    panel = Rect(tb.x1 - side_panel[0], tb.y1 + GAP / 2, tb.x1, tb.y1 + GAP / 2 + side_panel[1])
    if not panel.inside(usable) or side_panel[0] > TITLE_BLOCK_WIDTH:
        return None
    reserved = [tb, Rect(tb.x0, tb.y1, tb.x1, panel.y1)]

    column_width = max(fw, tw)
    row_height = max(fh, sh)
    x_front = usable.x0 + column_margin + column_width / 2
    y_front = usable.y1 - row_margin - row_height / 2
    y_top = y_front - row_height / 2 - row_margin - GAP - mt - th / 2
    x_side = x_front + column_width / 2 + column_margin + GAP + ms + sw / 2

    ortho = {
        "front": (x_front, y_front, fw, fh),
        "top": (x_front, y_top, tw, th),
        "side": (x_side, y_front, sw, sh),
    }
    rects = [Rect.centred(x, y, w, h, margins[name]) for name, (x, y, w, h) in ortho.items()]
    if not all(r.inside(usable) and not any(r.overlaps(z) for z in reserved) for r in rects):
        return None

    # Isometric view: right of the side view (top-aligned), else below the first row right of the top view.
    below_row1 = y_front - row_height / 2 - row_margin - GAP
    candidates = [
        (x_side + sw / 2 + ms + GAP + iw / 2, usable.y1 - GAP / 2 - ih / 2),
        (x_front + column_width / 2 + column_margin + GAP + iw / 2, below_row1 - ih / 2),
        (x_side + sw / 2 + ms + GAP + iw / 2, below_row1 - ih / 2),
    ]
    for x_iso, y_iso in candidates:
        r_iso = Rect.centred(x_iso, y_iso, iw, ih, GAP / 2)
        if r_iso.inside(usable) and not any(r_iso.overlaps(z) for z in [*reserved, *rects]):
            views = {name: Placement(x, y, w, h) for name, (x, y, w, h) in ortho.items()}
            views["iso"] = Placement(x_iso, y_iso, iw, ih)
            return Layout(sheet, denominator, views, panel)
    return None


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(_dot(v, v))
    return v[0] / n, v[1] / n, v[2] / n


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
