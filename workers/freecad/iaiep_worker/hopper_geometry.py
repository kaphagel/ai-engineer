"""Geometry of a trough hopper built from flat wall panels (pure Python, no FreeCAD).

Coordinates: x along the gas flow (hopper length), y across, z up; z = 0 at the bottom of the
slot (outlet), the hopper axis at x = y = 0. All lengths in mm, on the inner plate surfaces.

Shape (spec §24.3; reference construction checked against a real delivery, see PROJECT_STATUS.md):
- Side walls (y = ±s(z)) slope from the slot width at z = 0 to the top width at z = H.
- End walls (x = ±e(z)) are vertical from z = 0 to Hv, then slope to the top length at z = H.
  Hv = 0 gives a pyramidal hopper; the slot length equal to the slot width gives a square outlet.
- The walls are divided into tiers (horizontal bands). Each tier of each wall is one flat panel,
  except where an end wall changes from vertical to sloped inside a tier (then two panels).
- At every tier joint the upper panel starts `panel_gap` above the joint, measured along the wall.
  The top panels end `top_gap` below the top (z = H, the underside of the top beams), along the wall.
- Panel edges are square to the plate. Material is added outwards; adjacent walls meet at the inner
  corner line (corner joint detail not modelled). Where an end wall bends inside a tier, the lower and
  upper plates are mitred on the bisector plane through the inner bend line (see mitre_cuts).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

Vec = tuple[float, float, float]
Point2 = tuple[float, float]


@dataclass(frozen=True)
class HopperSpec:
    top_length_outside: float
    top_width_outside: float
    slot_length_inside: float
    slot_width_inside: float
    height: float
    end_wall_vertical_height: float
    tier_heights: tuple[float, ...]  # bottom to top; must add up to `height`
    plate_thickness: float
    panel_gap: float
    top_gap: float = 0.0

    @classmethod
    def from_parameters(cls, p: Mapping[str, object]) -> "HopperSpec":
        def num(key: str) -> float:
            value = p[key]
            if not isinstance(value, int | float):
                raise TypeError(f"{key} must be a number")
            return float(value)

        tiers = p["tier_heights_mm"]
        if not isinstance(tiers, list | tuple):
            raise TypeError("tier_heights_mm must be a list")
        spec = cls(
            top_length_outside=num("top_length_outside_mm"),
            top_width_outside=num("top_width_outside_mm"),
            slot_length_inside=num("slot_length_inside_mm"),
            slot_width_inside=num("slot_width_inside_mm"),
            height=num("height_mm"),
            end_wall_vertical_height=num("end_wall_vertical_height_mm"),
            tier_heights=tuple(float(t) for t in tiers),
            plate_thickness=num("plate_thickness_mm"),
            panel_gap=num("panel_gap_mm"),
            top_gap=num("top_gap_mm") if p.get("top_gap_mm") is not None else 0.0,
        )
        spec.validate()
        return spec

    def validate(self) -> None:
        errors = []
        if abs(sum(self.tier_heights) - self.height) > 1e-6:
            errors.append(f"tier heights add up to {sum(self.tier_heights)}, not the height {self.height}")
        if any(t <= 0 for t in self.tier_heights):
            errors.append("tier heights must be positive")
        if not 0 <= self.end_wall_vertical_height < self.height:
            errors.append("end wall vertical height must be at least 0 and less than the height")
        if self.slot_length_inside >= self.top_length_outside or self.slot_width_inside >= self.top_width_outside:
            errors.append("the slot must be smaller than the top opening")
        if self.plate_thickness <= 0 or self.panel_gap < 0 or self.top_gap < 0:
            errors.append("plate thickness must be positive and the panel gap not negative")
        if errors:
            raise ValueError("; ".join(errors))


@dataclass(frozen=True)
class Panel:
    name: str
    wall: str  # SideLeft (y+), SideRight (y-), EndInlet (x-), EndOutlet (x+)
    tier: int  # 1 = bottom
    points: tuple[Vec, ...]  # inner face, ordered
    normal: Vec  # unit, pointing out of the hopper


@dataclass(frozen=True)
class InnerShape:
    """Inner surface dimensions derived from the outside top dimensions."""

    top_length: float
    top_width: float
    slot_length: float
    slot_width: float
    height: float
    end_wall_vertical_height: float

    def half_width(self, z: float) -> float:
        return self.slot_width / 2 + (self.top_width - self.slot_width) / 2 * z / self.height

    def half_length(self, z: float) -> float:
        hv = self.end_wall_vertical_height
        if z <= hv:
            return self.slot_length / 2
        return self.slot_length / 2 + (self.top_length - self.slot_length) / 2 * (z - hv) / (self.height - hv)

    def side_wall_slope_deg(self) -> float:
        return math.degrees(math.atan2(self.height, (self.top_width - self.slot_width) / 2))

    def end_wall_slope_deg(self) -> float:
        hv = self.end_wall_vertical_height
        return math.degrees(math.atan2(self.height - hv, (self.top_length - self.slot_length) / 2))

    def valley_angle_deg(self) -> float:
        """Angle of the sloped corner line (between side wall and sloped end wall) to the horizontal."""
        hv = self.end_wall_vertical_height
        dx = (self.top_length - self.slot_length) / 2
        dy = self.half_width(self.height) - self.half_width(hv)
        return math.degrees(math.atan2(self.height - hv, math.hypot(dx, dy)))

    def capacity_m3(self) -> float:
        """Volume inside the inner wall surfaces. Exact: the area is quadratic in z on each segment."""
        total = 0.0
        for z0, z1 in ((0.0, self.end_wall_vertical_height), (self.end_wall_vertical_height, self.height)):
            if z1 > z0:
                areas = [4 * self.half_length(z) * self.half_width(z) for z in (z0, (z0 + z1) / 2, z1)]
                total += (z1 - z0) / 6 * (areas[0] + 4 * areas[1] + areas[2])
        return total / 1e9


def inner_shape(spec: HopperSpec) -> InnerShape:
    """Inner top dimensions from the outside top dimensions: the outer plate surface lies
    t / sin(slope) further out horizontally. Solved by fixed-point iteration."""
    t, h, hv = spec.plate_thickness, spec.height, spec.end_wall_vertical_height
    width, length = spec.top_width_outside, spec.top_length_outside
    for _ in range(50):
        side = math.atan2(h, (width - spec.slot_width_inside) / 2)
        end = math.atan2(h - hv, (length - spec.slot_length_inside) / 2)
        width = spec.top_width_outside - 2 * t / math.sin(side)
        length = spec.top_length_outside - 2 * t / math.sin(end)
    return InnerShape(length, width, spec.slot_length_inside, spec.slot_width_inside, h, hv)


def panels(spec: HopperSpec) -> list[Panel]:
    shape = inner_shape(spec)
    hv = shape.end_wall_vertical_height
    side_rise = math.sin(math.radians(shape.side_wall_slope_deg()))
    end_rise = math.sin(math.radians(shape.end_wall_slope_deg()))
    s, e = shape.half_width, shape.half_length

    result: list[Panel] = []
    z_bottom = 0.0
    for tier, tier_height in enumerate(spec.tier_heights, start=1):
        z_top = z_bottom + tier_height
        gap = spec.panel_gap if tier > 1 else 0.0
        top_gap = spec.top_gap if tier == len(spec.tier_heights) else 0.0

        # Side walls: one panel per tier; the outline has a kink where the end walls change slope.
        z0 = z_bottom + gap * side_rise
        z1 = z_top - top_gap * side_rise
        levels = [z0, *([hv] if z0 < hv < z1 else []), z1]
        right_edge = [(e(z), z) for z in levels]
        outline = [(-e(z0), z0), *right_edge, *[(-x, z) for x, z in reversed(right_edge[1:])]]
        for wall, sign in (("SideLeft", 1.0), ("SideRight", -1.0)):
            pts = [(x * sign, s(z) * sign, z) for x, z in outline]
            result.append(_panel(f"{wall}-T{tier}", wall, tier, pts))

        # End walls: split at the change from vertical to sloped.
        segments = [(z_bottom, min(z_top, hv)), (max(z_bottom, hv), z_top)]
        for part, (za, zb) in zip(("lower", "upper"), segments, strict=True):
            if zb - za <= 1e-9:
                continue
            suffix = "" if (za, zb) == (z_bottom, z_top) else f"-{part}"
            if za == z_bottom:
                za += gap * (1.0 if part == "lower" else end_rise)
            if zb == z_top:
                zb -= top_gap * (1.0 if part == "lower" else end_rise)
            for wall, sign in (("EndOutlet", 1.0), ("EndInlet", -1.0)):
                pts = [(e(za) * sign, -s(za) * sign, za), (e(za) * sign, s(za) * sign, za)]
                pts += [(e(zb) * sign, s(zb) * sign, zb), (e(zb) * sign, -s(zb) * sign, zb)]
                result.append(_panel(f"{wall}-T{tier}{suffix}", wall, tier, pts))
        z_bottom = z_top
    return result


Plane = tuple[Vec, Vec]  # a point on the plane, and the unit normal pointing to the side to remove


def mitre_cuts(spec: HopperSpec, panels: list[Panel]) -> dict[str, list[Plane]]:
    """Cutting planes for plates that meet at a bend of the wall inside a tier (end walls at the change
    from vertical to sloped). Each plate keeps its side of the bisector plane through the inner bend
    line, so the two plates touch without overlapping."""
    t = spec.plate_thickness
    by_name = {p.name: p for p in panels}
    cuts: dict[str, list[Plane]] = {}
    for lower in panels:
        if not lower.name.endswith("-lower"):
            continue
        upper = by_name.get(lower.name[: -len("lower")] + "upper")
        if upper is None:
            continue
        shared = [p for p in lower.points if any(_distance(p, q) < 1e-6 for q in upper.points)]
        if len(shared) != 2:
            continue
        edge = _unit(_sub(shared[1], shared[0]))
        n1, n2 = lower.normal, upper.normal
        k = t / (1 + _dot(n1, n2))
        offset = (k * (n1[0] + n2[0]), k * (n1[1] + n2[1]), k * (n1[2] + n2[2]))
        normal = _unit(_cross(edge, offset))
        towards_upper = _dot(normal, _sub(_centroid(upper.points), shared[0]))
        if towards_upper < 0:
            normal = (-normal[0], -normal[1], -normal[2])
        cuts.setdefault(lower.name, []).append((shared[0], normal))
        cuts.setdefault(upper.name, []).append((shared[0], (-normal[0], -normal[1], -normal[2])))
    return cuts


def flat_contour(panel: Panel) -> list[Point2]:
    """Inner face in its own plane: u horizontal, v up the wall, origin at the lower-left corner."""
    n = panel.normal
    u = _unit(_cross((0.0, 0.0, 1.0), n))
    v = _cross(n, u)
    if v[2] < 0:
        u, v = (-u[0], -u[1], -u[2]), (-v[0], -v[1], -v[2])
    coords = [(_dot(p, u), _dot(p, v)) for p in panel.points]
    min_u = min(c[0] for c in coords)
    min_v = min(c[1] for c in coords)
    return [(cu - min_u, cv - min_v) for cu, cv in coords]


def flat_size(contour: list[Point2]) -> tuple[float, float]:
    return max(c[0] for c in contour), max(c[1] for c in contour)


def polygon_area(contour: list[Point2]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(contour, [*contour[1:], contour[0]], strict=True))) / 2


def _panel(name: str, wall: str, tier: int, pts: list[Vec]) -> Panel:
    # Newell's method gives the polygon normal; orient it away from the hopper axis.
    n = [0.0, 0.0, 0.0]
    for a, b in zip(pts, [*pts[1:], pts[0]], strict=True):
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    normal = _unit((n[0], n[1], n[2]))
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    if normal[0] * cx + normal[1] * cy < 0:
        normal = (-normal[0], -normal[1], -normal[2])
    return Panel(name, wall, tier, tuple(pts), normal)


def _sub(a: Vec, b: Vec) -> Vec:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _distance(a: Vec, b: Vec) -> float:
    return math.sqrt(_dot(_sub(a, b), _sub(a, b)))


def _centroid(points: tuple[Vec, ...]) -> Vec:
    n = len(points)
    return sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n


def _unit(v: Vec) -> Vec:
    n = math.sqrt(_dot(v, v))
    return v[0] / n, v[1] / n, v[2] / n


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]
