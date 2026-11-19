"""Minimal DXF (AutoCAD R12) writer for plate flat patterns (pure Python, no FreeCAD).

Each contour is written as one closed POLYLINE on layer CUT, so cutting software (plasma, laser)
receives closed outlines. Labels go on layer MARK. Units are millimetres. Output is deterministic.
"""

from collections.abc import Sequence

Point = tuple[float, float]


def write_flat_pattern(
    path: str, contours: Sequence[Sequence[Point]], labels: Sequence[tuple[Point, float, str]]
) -> None:
    lines: list[str] = ["0", "SECTION", "2", "ENTITIES"]
    for contour in contours:
        lines += ["0", "POLYLINE", "8", "CUT", "66", "1", "70", "1", "10", "0.0", "20", "0.0", "30", "0.0"]
        for x, y in contour:
            lines += ["0", "VERTEX", "8", "CUT", "10", _num(x), "20", _num(y), "30", "0.0"]
        lines += ["0", "SEQEND", "8", "CUT"]
    for (x, y), height, text in labels:
        lines += ["0", "TEXT", "8", "MARK", "10", _num(x), "20", _num(y), "30", "0.0", "40", _num(height), "1", text]
    lines += ["0", "ENDSEC", "0", "EOF"]
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def _num(value: float) -> str:
    text = f"{value:.4f}"
    return "0.0000" if text == "-0.0000" else text
