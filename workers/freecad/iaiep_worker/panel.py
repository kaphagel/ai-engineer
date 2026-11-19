"""Side panel above the title block: parts list (ISO 7573) and notes, as one SVG (pure Python).

Drawn by us rather than with TechDraw's spreadsheet view, so that its size is exact and can be
reserved in the layout. Units are paper millimetres.
"""

from collections.abc import Sequence
from xml.sax.saxutils import escape

ROW_HEIGHT = 7.0
NOTE_LINE_HEIGHT = 5.0
TEXT_SIZE = 3.5
GAP = 6.0
PADDING = 2.0
FONT = "osifont"


def panel_height(rows: int, notes: int) -> float:
    """Height of the panel for `rows` parts-list rows (plus header) and `notes` note lines."""
    return (rows + 1) * ROW_HEIGHT + GAP + notes * NOTE_LINE_HEIGHT + PADDING


def side_panel_svg(
    header: Sequence[str], rows: Sequence[Sequence[str]], column_widths: Sequence[float], notes: Sequence[str]
) -> tuple[str, float, float]:
    """SVG of the panel and its width and height in mm.

    The parts list sits at the bottom with its header row next to the title block and item 1 above it
    (ISO 7573); the notes are above the parts list.
    """
    width = sum(column_widths)
    height = panel_height(len(rows), len(notes))
    parts: list[str] = []
    table_rows = [header, *rows]
    for r, row in enumerate(table_rows):
        y_bottom = height - r * ROW_HEIGHT
        y_top = y_bottom - ROW_HEIGHT
        parts.append(_line(0, y_top, width, y_top))
        x = 0.0
        for text, column_width in zip(row, column_widths, strict=True):
            if r == 0:
                parts.append(_line(x, height - len(table_rows) * ROW_HEIGHT, x, height))
            parts.append(_text(x + 1.5, y_bottom - (ROW_HEIGHT - TEXT_SIZE) / 2, text, bold=r == 0))
            x += column_width
    parts.append(_line(width, height - len(table_rows) * ROW_HEIGHT, width, height))
    notes_bottom = height - len(table_rows) * ROW_HEIGHT - GAP
    for i, line in enumerate(reversed(notes)):
        parts.append(_text(0.5, notes_bottom - i * NOTE_LINE_HEIGHT, line))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}mm" height="{height:.3f}mm" '
        f'viewBox="0 0 {width:.3f} {height:.3f}">' + "".join(parts) + "</svg>"
    )
    return svg, width, height


def _line(x0: float, y0: float, x1: float, y1: float) -> str:
    return f'<path d="M {x0:.3f},{y0:.3f} L {x1:.3f},{y1:.3f}" stroke="#000000" stroke-width="0.35" fill="none"/>'


def _text(x: float, y: float, text: str, bold: bool = False) -> str:
    weight = ' font-weight="bold"' if bold else ""
    return (
        f'<text x="{x:.3f}" y="{y:.3f}" font-family="{FONT}" font-size="{TEXT_SIZE}"{weight} fill="#000000">'
        f"{escape(text)}</text>"
    )
