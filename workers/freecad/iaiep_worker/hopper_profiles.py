"""Tier beams and vertical stiffeners on the hopper wall panels (pure Python, no FreeCAD).

Construction (checked against a real delivery, see ADR-0004):
- A tier beam (channel) runs along the top edge of every tier except the topmost: one per wall, at
  each tier joint. Its web is horizontal and carries the upper panel; its flanges hang down outside
  the lower panel. Beam length = top edge length of the lower panel + an extension at each end
  (an input per joint and wall type; the reference delivery uses different values per joint).
- Stiffeners (angles) stand on the outer face of a panel, square to its top edge. Their positions are
  given as bays (centre distances) symmetric about the panel centreline, as the part drawings
  dimension them. A stiffener runs from the panel bottom edge, but at least a clearance above the
  bottom of the plate (bottom panel piece of a tier only), up to the top edge, and beyond it by an
  extension (input per layout) where a tier beam is above.
- Top beams (channels) run along the top edge of the topmost tier, web horizontal resting on the plate
  top edge, split into segments at given positions (the reference splits them at the support columns).
- Supports: a short H-section column stub at every support grid point on the hopper perimeter, with a
  column plate on top (level with the top beams) and a base plate below. Corner points belong to the
  end walls, the others to the side walls. Bracket plates connecting stubs and panels are not modelled.
- Brackets connect each stub to its top panel: a gusset between the stub and the sloped wall on the
  column line (shape from the geometry), and the other plates of the issued bracket (sizes from the
  input) in a simplified box arrangement around it. Corner brackets are moved along the end wall so
  that they stay on the plate.
- Bracing runs across the hopper between the side walls on given x positions (the inner support column
  lines): a strut (tube with an end plate at each end, through the panel gap) at given tier joints, and
  a truss of two tubes joined by a web plate below the top.
- Simplified representation: sections are drawn with the nominal dimensions (no root radii), the mass
  comes from the catalogue mass per metre; copes, cut-outs and corner connections are not modelled, so
  parts may overlap at connections (reported, not an error).
"""

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from iaiep_worker.hopper_geometry import HopperSpec, Panel, Vec, inner_shape

TOL = 1e-6


@dataclass(frozen=True)
class Section:
    name: str
    kind: str  # "channel", "angle", "h_section" or "tube"
    designation: str
    standard: str
    material: str
    depth: float  # channel, H: web depth; angle: outstanding leg (square to the plate)
    width: float  # channel, H: flange width; angle: leg lying on the plate
    web_thickness: float
    flange_thickness: float
    mass_per_m: float


@dataclass(frozen=True)
class StiffenerLayout:
    wall: str  # "side" or "end"
    tier: int
    bays: tuple[float, ...]
    profiles: tuple[str, ...]  # one per stiffener, from the inlet (x-) or left (y+) end
    bottom_clearance: float
    top_extension: float  # may be negative: the stiffener stops below the top edge
    stops_below_top: tuple[float, ...] = ()  # per stiffener, extra shortening at the top (0 = none)

    def stop(self, k: int) -> float:
        return self.stops_below_top[k] if self.stops_below_top else 0.0

    def offsets(self) -> list[float]:
        """Stiffener positions along the panel top edge, from the centreline."""
        positions = [0.0]
        for bay in self.bays:
            positions.append(positions[-1] + bay)
        return [p - positions[-1] / 2 for p in positions]


@dataclass(frozen=True)
class Stiffening:
    sections: Mapping[str, Section]
    side_beam: str | None
    end_beam: str | None
    side_beam_extensions: tuple[float, ...]  # per tier joint, bottom first
    end_beam_extensions: tuple[float, ...]
    layouts: tuple[StiffenerLayout, ...]
    top: "TopBeams | None" = None
    supports: "Supports | None" = None
    brackets: "Brackets | None" = None
    bracing: Mapping[str, Any] | None = None  # job data, see bracing()

    @classmethod
    def from_job(cls, data: Mapping[str, Any] | None) -> "Stiffening":
        if not data:
            return cls({}, None, None, (), (), ())
        sections = {
            name: Section(
                name,
                p["kind"],
                p["designation"],
                p["standard"],
                p["material"],
                float(p["depth_mm"]),
                float(p["width_mm"]),
                float(p["web_thickness_mm"]),
                float(p["flange_thickness_mm"]),
                float(p["mass_per_m_kg"]),
            )
            for name, p in data.get("profiles", {}).items()
        }
        beams = data.get("tier_beams") or {}
        result = cls(
            sections=sections,
            side_beam=beams.get("side_profile"),
            end_beam=beams.get("end_profile"),
            side_beam_extensions=tuple(float(x) for x in beams.get("side_end_extensions_mm", ())),
            end_beam_extensions=tuple(float(x) for x in beams.get("end_end_extensions_mm", ())),
            layouts=tuple(
                StiffenerLayout(
                    s["wall"],
                    int(s["tier"]),
                    tuple(s["bays_mm"]),
                    tuple(s["profiles"]),
                    float(s["bottom_clearance_mm"]),
                    float(s["top_extension_mm"]),
                    tuple(float(x) for x in s.get("stops_below_top_mm") or ()),
                )
                for s in data.get("stiffeners", [])
            ),
            top=TopBeams.from_job(data["top_beams"]) if data.get("top_beams") else None,
            supports=Supports.from_job(data["supports"]) if data.get("supports") else None,
            brackets=Brackets.from_job(data["brackets"]) if data.get("brackets") else None,
            bracing=data.get("bracing") or None,
        )
        result.validate()
        return result

    def validate(self) -> None:
        errors = []
        for name, kind in ((self.side_beam, "channel"), (self.end_beam, "channel")):
            if name is not None and (name not in self.sections or self.sections[name].kind != kind):
                errors.append(f"tier beam profile {name!r} is not a {kind} in the profile list")
        for lay in self.layouts:
            if len(lay.profiles) != len(lay.bays) + 1:
                errors.append(f"{lay.wall} tier {lay.tier}: {len(lay.bays)} bays need {len(lay.bays) + 1} profiles")
            for name in lay.profiles:
                if name not in self.sections or self.sections[name].kind != "angle":
                    errors.append(f"{lay.wall} tier {lay.tier}: stiffener profile {name!r} is not an angle")
            if lay.stops_below_top and len(lay.stops_below_top) != len(lay.profiles):
                errors.append(f"{lay.wall} tier {lay.tier}: one stop below the top per stiffener needed")
        if self.top is not None:
            for name in (self.top.side_profile, self.top.end_profile):
                if name not in self.sections or self.sections[name].kind != "channel":
                    errors.append(f"top beam profile {name!r} is not a channel in the profile list")
        if self.supports is not None:
            name = self.supports.stub_profile
            if name not in self.sections or self.sections[name].kind != "h_section":
                errors.append(f"column stub profile {name!r} is not an H section in the profile list")
        if errors:
            raise ValueError("; ".join(errors))


@dataclass(frozen=True)
class TopBeams:
    side_profile: str
    end_profile: str
    side_end_extension: float  # may be negative: shorter than the plate top edge
    end_end_extension: float
    side_splits: tuple[float, ...]  # joint positions along the beam from the centreline
    end_splits: tuple[float, ...]

    @classmethod
    def from_job(cls, d: Mapping[str, Any]) -> "TopBeams":
        return cls(
            d["side_profile"],
            d["end_profile"],
            float(d["side_end_extension_mm"]),
            float(d["end_end_extension_mm"]),
            tuple(sorted(float(x) for x in d.get("side_splits_mm", ()))),
            tuple(sorted(float(x) for x in d.get("end_splits_mm", ()))),
        )


@dataclass(frozen=True)
class Supports:
    grid_x: tuple[float, ...]  # support column lines along the hopper (x), first and last at the corners
    grid_y: tuple[float, float]  # the two column lines across (y)
    stub_profile: str
    stub_length: float
    top_above_hopper_top: float  # top of the column plate above the hopper top (z = height)
    corner_plate: tuple[float, float, float]  # column plate at corners: along x, along y, thickness
    side_plate: tuple[float, float, float]  # column plate at the side columns
    side_plate_offset: float  # centre of the side column plate moved away from the hopper axis
    base_plate: tuple[float, float, float]
    material: str

    @classmethod
    def from_job(cls, d: Mapping[str, Any]) -> "Supports":
        def triple(key: str) -> tuple[float, float, float]:
            a, b, c = (float(x) for x in d[key])
            return a, b, c

        y0, y1 = sorted(float(y) for y in d["grid_y_mm"])
        return cls(
            tuple(sorted(float(x) for x in d["grid_x_mm"])),
            (y0, y1),
            d["stub_profile"],
            float(d["stub_length_mm"]),
            float(d["column_plate_top_above_top_mm"]),
            triple("corner_column_plate_mm"),
            triple("side_column_plate_mm"),
            float(d.get("side_column_plate_outward_offset_mm", 0.0)),
            triple("base_plate_mm"),
            d["plate_material"],
        )


@dataclass(frozen=True)
class BracketPlateSpec:
    role: str  # gusset, back, side, bottom, bar (see iaiep_esp.hopper.inputs.BracketPlate)
    thickness: float
    size: tuple[float, float]
    quantity: int
    level: float

    @classmethod
    def from_job(cls, d: Mapping[str, Any]) -> "BracketPlateSpec":
        a, b = (float(v) for v in (d.get("size_mm") or (0.0, 0.0)))
        return cls(d["role"], float(d["thickness_mm"]), (a, b), int(d.get("quantity", 1)), float(d.get("level_mm", 0)))


@dataclass(frozen=True)
class Brackets:
    depth: float
    side: tuple[BracketPlateSpec, ...]
    corner: tuple[BracketPlateSpec, ...]
    material: str

    @classmethod
    def from_job(cls, d: Mapping[str, Any]) -> "Brackets":
        return cls(
            float(d["depth_mm"]),
            tuple(BracketPlateSpec.from_job(x) for x in d["side"]),
            tuple(BracketPlateSpec.from_job(x) for x in d["corner"]),
            d["material"],
        )


@dataclass(frozen=True)
class Slab:
    """Flat plate of constant thickness: a face polygon swept along `extrude`."""

    name: str
    panel: str
    role: str
    thickness: float
    plate_size: tuple[float, float]  # for the BOM
    outline: tuple[Vec, ...]
    extrude: Vec
    material: str
    kind: str = "bracket plate"


@dataclass(frozen=True)
class SupportPoint:
    name: str
    panel: Panel
    x: float
    y: float
    corner: bool


@dataclass(frozen=True)
class Box:
    """Rectangular plate: centre of its bottom face, size along x, y and thickness (z)."""

    name: str
    panel: str
    kind: str  # "column plate" or "base plate"
    centre: Vec
    size: tuple[float, float, float]
    material: str


@dataclass(frozen=True)
class Stub:
    name: str
    panel: str
    section: Section
    length: float
    origin: Vec  # centre of the section at the lower end
    along: Vec = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class Beam:
    name: str
    panel: str  # the panel whose top edge carries the beam
    section: Section
    length: float
    origin: Vec  # inner-top corner of the section at the start of the beam
    along: Vec  # unit, along the beam
    outward: Vec  # unit, horizontal, away from the hopper


@dataclass(frozen=True)
class Stiffener:
    name: str
    panel: str
    section: Section
    length: float
    origin: Vec  # heel of the angle on the plate's outer face, at the lower end
    along: Vec  # unit, up the panel, square to its top edge
    normal: Vec  # unit, out of the plate
    across: Vec  # unit, along the panel top edge (the plate leg points this way)


def wall_kind(wall: str) -> str:
    return "side" if wall.startswith("Side") else "end"


def tier_beams(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> list[Beam]:
    """One beam per wall on top of every tier except the topmost."""
    beams = []
    top_tier = len(spec.tier_heights)
    for lower in panels:
        kind = wall_kind(lower.wall)
        profile = stiffening.side_beam if kind == "side" else stiffening.end_beam
        if profile is None or lower.tier == top_tier or not _reaches_tier_top(lower, spec):
            continue
        upper = next(
            p for p in panels if p.wall == lower.wall and p.tier == lower.tier + 1 and _is_tier_bottom(p, spec)
        )
        section = stiffening.sections[profile]
        extensions = stiffening.side_beam_extensions if kind == "side" else stiffening.end_beam_extensions
        if len(extensions) < lower.tier:
            raise ValueError(f"no {kind} beam end extension given for tier joint {lower.tier}")
        extension = extensions[lower.tier - 1]
        top = sorted(lower.points, key=lambda p: p[2])[-2:]
        along = _unit(_sub(top[1], top[0]))
        if _dot(along, _cross((0.0, 0.0, 1.0), lower.normal)) < 0:
            along, top = _neg(along), top[::-1]
        outward = _unit((lower.normal[0], lower.normal[1], 0.0))
        horizontal = math.hypot(lower.normal[0], lower.normal[1])
        # Web top at the lowest point of the upper plate; inner flange against the lower plate's outer face.
        web_top = min(
            min(p[2] for p in upper.points), min(p[2] for p in upper.points) + spec.plate_thickness * upper.normal[2]
        )
        start = _add(top[0], _scale(along, -extension))
        origin = _add(_add(start, _scale(outward, spec.plate_thickness / horizontal)), (0.0, 0.0, web_top - start[2]))
        beams.append(
            Beam(
                f"Beam-{lower.wall}-J{lower.tier}",
                lower.name,
                section,
                _distance(top[0], top[1]) + 2 * extension,
                origin,
                along,
                outward,
            )
        )
    return beams


def top_beams(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> list[Beam]:
    """Top beams on the top edge of the topmost tier, web resting on the plate top edge, split in segments."""
    top = stiffening.top
    if top is None:
        return []
    beams = []
    for panel in top_tier_panels(spec, panels):
        kind = wall_kind(panel.wall)
        section = stiffening.sections[top.side_profile if kind == "side" else top.end_profile]
        extension = top.side_end_extension if kind == "side" else top.end_end_extension
        splits = top.side_splits if kind == "side" else top.end_splits
        edge = sorted(panel.points, key=lambda p: p[2])[-2:]
        along = _unit(_sub(edge[1], edge[0]))
        if _dot(along, _cross((0.0, 0.0, 1.0), panel.normal)) < 0:
            along, edge = _neg(along), edge[::-1]
        half = _distance(edge[0], edge[1]) / 2 + extension
        if half <= 0 or any(abs(x) >= half for x in splits):
            raise ValueError(f"{panel.name}: top beam splits {splits} outside the beam")
        outward = _unit((panel.normal[0], panel.normal[1], 0.0))
        horizontal = math.hypot(panel.normal[0], panel.normal[1])
        middle = _scale(_add(edge[0], edge[1]), 0.5)
        # Inner flange against the plate's outer face (as the tier beams), web underside at the top edge.
        corner = _add(middle, _scale(outward, spec.plate_thickness / horizontal))
        bounds = [-half, *splits, half]
        for k, (a, b) in enumerate(itertools.pairwise(bounds), start=1):
            suffix = "" if len(bounds) == 2 else f"-{k}"
            origin = _add(_add(corner, _scale(along, a)), (0.0, 0.0, section.web_thickness))
            beams.append(Beam(f"Beam-{panel.wall}-Top{suffix}", panel.name, section, b - a, origin, along, outward))
    return beams


def top_tier_panels(spec: HopperSpec, panels: Sequence[Panel]) -> list[Panel]:
    """The highest panel of each wall in the top tier (it carries the top beam)."""
    top = len(spec.tier_heights)
    highest: dict[str, Panel] = {}
    for p in panels:
        if p.tier == top and (p.wall not in highest or _top_z(p) > _top_z(highest[p.wall])):
            highest[p.wall] = p
    return list(highest.values())


def _top_z(panel: Panel) -> float:
    return max(p[2] for p in panel.points)


def support_points(spec: HopperSpec, panels: Sequence[Panel], sup: "Supports") -> list[SupportPoint]:
    """Grid points on the perimeter: corners carried by the end walls, the others by the side walls."""
    top_panels = {p.wall: p for p in top_tier_panels(spec, panels)}
    points = []
    for i, x in enumerate(sup.grid_x):
        corner = i in (0, len(sup.grid_x) - 1)
        for y in sup.grid_y:
            end = "EndInlet" if i == 0 else "EndOutlet"
            wall = end if corner else "SideLeft" if y > 0 else "SideRight"
            name = f"{x:+.0f}_{y:+.0f}".replace("+", "P").replace("-", "M")
            points.append(SupportPoint(name, top_panels[wall], x, y, corner))
    return points


def supports(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> tuple[list[Stub], list[Box]]:
    """Column stubs with column and base plates at the support grid points on the hopper perimeter."""
    sup = stiffening.supports
    if sup is None:
        return [], []
    section = stiffening.sections[sup.stub_profile]
    stubs, boxes = [], []
    top_level = spec.height + sup.top_above_hopper_top
    for point in support_points(spec, panels, sup):
        x, y, corner, name, panel = point.x, point.y, point.corner, point.name, point.panel.name
        plate = sup.corner_plate if corner else sup.side_plate
        stub_top = top_level - plate[2]
        stub_bottom = stub_top - sup.stub_length
        dy = 0.0 if corner else math.copysign(sup.side_plate_offset, y)
        boxes.append(Box(f"ColumnPlate-{name}", panel, "column plate", (x, y + dy, stub_top), plate, sup.material))
        stubs.append(Stub(f"Stub-{name}", panel, section, sup.stub_length, (x, y, stub_bottom)))
        base = sup.base_plate
        boxes.append(Box(f"BasePlate-{name}", panel, "base plate", (x, y, stub_bottom - base[2]), base, sup.material))
    return stubs, boxes


def brackets(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> list[Slab]:
    """Bracket plates at every support point (simplified arrangement, see the module docstring)."""
    sup, br = stiffening.supports, stiffening.brackets
    if sup is None or br is None:
        return []
    section = stiffening.sections[sup.stub_profile]
    z_top, z_bottom = spec.height, spec.height - br.depth
    result = []
    for point in support_points(spec, panels, sup):
        panel = point.panel
        side_wall = wall_kind(panel.wall) == "side"
        along: Vec = (1.0, 0.0, 0.0) if side_wall else (0.0, 1.0, 0.0)
        sign = math.copysign(1.0, point.y if side_wall else point.x)
        out: Vec = (0.0, sign, 0.0) if side_wall else (sign, 0.0, 0.0)
        a_col = point.x if side_wall else point.y
        extent = section.depth if side_wall else section.width  # stub size across the wall
        n_stub = (point.y if side_wall else point.x) * sign - extent / 2
        plates = br.corner if point.corner else br.side
        back_row = sum(p.size[0] * p.quantity for p in plates if p.role == "back")
        half_row = back_row / 2 if back_row else max((p.thickness for p in plates if p.role == "gusset"), default=0) / 2
        a_c = a_col
        if point.corner:  # keep the bracket on the end wall plate
            limit = _half_extent_at(panel, along, z_bottom) - half_row
            a_c = math.copysign(min(abs(a_col), max(limit, 0.0)), a_col)

        def wall_n(z: float, panel: Panel = panel, out: Vec = out, along: Vec = along) -> float:
            """Outer wall face along `out` at height z (the wall plane has no component along the wall)."""
            n = panel.normal
            d = _dot(n, panel.points[0]) + spec.plate_thickness
            return (d - n[2] * z) / _dot(n, out)

        def at(a: float, n: float, z: float, along: Vec = along, out: Vec = out) -> Vec:
            return _add(_add(_scale(along, a), _scale(out, n)), (0.0, 0.0, z))

        k = 0

        def add(
            role: str,
            spec_: BracketPlateSpec,
            size: tuple[float, float],
            outline: list[Vec],
            extrude: Vec,
            point: SupportPoint = point,
        ) -> None:
            nonlocal k
            k += 1
            result.append(
                Slab(
                    f"Bracket-{point.name}-{k:02d}",
                    point.panel.name,
                    role,
                    spec_.thickness,
                    size,
                    tuple(outline),
                    extrude,
                    br.material,
                )
            )

        def plate_at(
            role: str,
            spec_: BracketPlateSpec,
            a: tuple[float, float],
            n: tuple[float, float],
            z: tuple[float, float],
            size: tuple[float, float] | None = None,
            wall_n: Callable[[float], float] = wall_n,
            at: Callable[[float, float, float], Vec] = at,
            point: SupportPoint = point,
            along: Vec = along,
        ) -> None:
            """Box over the ranges a, n, z, trimmed by the outer wall face (the plate is cut to the wall)."""
            section = clip_to_wall([(n[0], z[0]), (n[1], z[0]), (n[1], z[1]), (n[0], z[1])], wall_n)
            if len(section) < 3:
                raise ValueError(f"support {point.name}: a {role} plate lies entirely inside the wall")
            if size is None:  # gusset: its size follows from the trimmed shape
                ns, zs = [q[0] for q in section], [q[1] for q in section]
                size = (round(max(zs) - min(zs), 1), round(max(ns) - min(ns), 1))
            add(role, spec_, size, [at(a[0], q[0], q[1]) for q in section], _scale(along, a[1] - a[0]))

        inward = -math.copysign(1.0, a_col) if point.corner else -1.0
        bottom_row = sum(p.size[0] * p.quantity for p in plates if p.role == "bottom")
        cursor: dict[str, float] = {"back": -back_row / 2, "bottom": -bottom_row / 2}
        side_count = 0
        for plate in plates:
            t, (l1, l2) = plate.thickness, plate.size
            left, right = a_c - half_row, a_c + half_row  # bar rows start beside the bracket
            for q in range(plate.quantity):
                if plate.role == "gusset":
                    span = (a_c - t / 2, a_c + t / 2)
                    plate_at("gusset", plate, span, (wall_n(z_bottom), n_stub), (z_bottom, z_top))
                elif plate.role == "back":
                    a0 = a_c + cursor["back"]
                    cursor["back"] += l1
                    plate_at("back", plate, (a0, a0 + l1), (n_stub - t, n_stub), (z_top - l2, z_top), (l1, l2))
                elif plate.role == "side":
                    end = inward if side_count % 2 == 0 else -inward
                    side_count += 1
                    a0 = a_c + half_row if end > 0 else a_c - half_row - t
                    plate_at("side", plate, (a0, a0 + t), (n_stub - l1, n_stub), (z_top - l2, z_top), (l1, l2))
                elif plate.role == "bottom":
                    a0 = a_c + cursor["bottom"]
                    cursor["bottom"] += l1
                    plate_at("bottom", plate, (a0, a0 + l1), (n_stub - l2, n_stub), (z_bottom - t, z_bottom), (l1, l2))
                else:  # bar on the outer wall face
                    z0 = z_bottom + plate.level
                    if q % 2 == 0:
                        left -= l1
                        a0 = left
                    else:
                        a0 = right
                        right += l1
                    plate_at("bar", plate, (a0, a0 + l1), (wall_n(z0), wall_n(z0) + l2), (z0, z0 + t), (l1, l2))
    return result


def clip_to_wall(polygon: list[tuple[float, float]], wall_n: Callable[[float], float]) -> list[tuple[float, float]]:
    """Part of a polygon in (n, z) on or outside the wall face n = wall_n(z) (wall_n linear in z)."""
    inside = [n - wall_n(z) >= -TOL for n, z in polygon]
    result = []
    for k, (p, p_in) in enumerate(zip(polygon, inside, strict=True)):
        q, q_in = polygon[(k + 1) % len(polygon)], inside[(k + 1) % len(polygon)]
        if p_in:
            result.append(p)
        if p_in != q_in:
            fp, fq = p[0] - wall_n(p[1]), q[0] - wall_n(q[1])
            r = fp / (fp - fq)
            result.append((p[0] + r * (q[0] - p[0]), p[1] + r * (q[1] - p[1])))
    cleaned: list[tuple[float, float]] = []
    for pt in result:
        if not cleaned or math.dist(pt, cleaned[-1]) > 1e-6:
            cleaned.append(pt)
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) <= 1e-6:
        cleaned.pop()
    return cleaned


BRACING_PANEL = "Bracing"


def bracing(spec: HopperSpec, stiffening: Stiffening) -> tuple[list[Stub], list[Slab]]:
    """Tubes and plates of the internal bracing (along y, between the side walls)."""
    data = stiffening.bracing
    if not data:
        return [], []
    width = inner_shape(spec).half_width
    joints = [sum(spec.tier_heights[:k]) for k in range(1, len(spec.tier_heights))]
    along: Vec = (0.0, 1.0, 0.0)
    tubes: list[Stub] = []
    plates: list[Slab] = []
    material = data["material"]
    for x in data["x_mm"]:
        tag = f"{x:+.0f}".replace("+", "P").replace("-", "M")
        for strut in data.get("struts", []):
            section = stiffening.sections[strut["tube_profile"]]
            k = int(strut["joint"])
            z = joints[k - 1] + float(strut.get("level_offset_mm", 0.0))
            half = width(z) + float(strut["overhang_mm"])
            projection = float(strut["plate_projection_mm"])
            plate_len, plate_h, plate_t = (float(v) for v in strut["end_plate_mm"])
            name = f"Strut-{tag}-J{k}"
            tubes.append(
                Stub(name, BRACING_PANEL, section, 2 * (half - projection), (x, -(half - projection), z), along)
            )
            for end in (-1.0, 1.0):
                y0 = end * half if end < 0 else half - plate_len
                outline = [
                    (x - plate_t / 2, y0, z - plate_h / 2),
                    (x - plate_t / 2, y0 + plate_len, z - plate_h / 2),
                    (x - plate_t / 2, y0 + plate_len, z + plate_h / 2),
                    (x - plate_t / 2, y0, z + plate_h / 2),
                ]
                plates.append(
                    Slab(
                        f"{name}-{'L' if end > 0 else 'R'}",
                        BRACING_PANEL,
                        "end plate",
                        plate_t,
                        (plate_len, plate_h),
                        tuple(outline),
                        (plate_t, 0.0, 0.0),
                        material,
                        "bracing plate",
                    )
                )
        truss = data.get("top_truss")
        if truss:
            section = stiffening.sections[truss["tube_profile"]]
            z_up = spec.height - float(truss["upper_below_top_mm"])
            z_low = z_up - float(truss["depth_mm"])
            clearance = float(truss["end_clearance_mm"])
            half_low = width(z_low) - clearance
            for label, z in (("upper", z_up), ("lower", z_low)):
                half = width(z) - clearance
                tubes.append(Stub(f"Truss-{tag}-{label}", BRACING_PANEL, section, 2 * half, (x, -half, z), along))
            t = float(truss["web_thickness_mm"])
            web_half = half_low - float(truss["web_end_inset_mm"])
            z0, z1 = z_low + section.depth / 2, z_up - section.depth / 2
            outline = [
                (x - t / 2, -web_half, z0),
                (x - t / 2, web_half, z0),
                (x - t / 2, web_half, z1),
                (x - t / 2, -web_half, z1),
            ]
            plates.append(
                Slab(
                    f"Truss-{tag}-web",
                    BRACING_PANEL,
                    "web",
                    t,
                    (round(2 * web_half, 1), round(z1 - z0, 1)),
                    tuple(outline),
                    (t, 0.0, 0.0),
                    material,
                    "bracing plate",
                )
            )
    return tubes, plates


def _half_extent_at(panel: Panel, along: Vec, z: float) -> float:
    """Largest distance from the axis, along `along`, of the panel outline at height z."""
    found = []
    pts = list(panel.points)
    for p, q in zip(pts, [*pts[1:], pts[0]], strict=True):
        if min(p[2], q[2]) - TOL <= z <= max(p[2], q[2]) + TOL and abs(q[2] - p[2]) > TOL:
            r = (z - p[2]) / (q[2] - p[2])
            found.append(abs(_dot(along, p) + r * (_dot(along, q) - _dot(along, p))))
    if not found:
        raise ValueError(f"{panel.name}: no outline at z = {z:.1f}")
    return max(found)


def slab_volume(slab: Slab) -> float:
    """Polygon area (Newell) times the sweep length."""
    n = [0.0, 0.0, 0.0]
    pts = list(slab.outline)
    for a, b in zip(pts, [*pts[1:], pts[0]], strict=True):
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) / 2 * math.sqrt(_dot(slab.extrude, slab.extrude))


def stiffeners(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> list[Stiffener]:
    beam_panels = {b.panel for b in tier_beams(spec, panels, stiffening) + top_beams(spec, panels, stiffening)}
    result = []
    for layout in stiffening.layouts:
        pieces = [p for p in panels if wall_kind(p.wall) == layout.wall and p.tier == layout.tier]
        if not pieces:
            raise ValueError(f"no {layout.wall} wall panel in tier {layout.tier}")
        for panel in pieces:
            along, across = _panel_axes(panel)
            top = sorted(panel.points, key=lambda p: p[2])[-2:]
            mid_top = _scale(_add(top[0], top[1]), 0.5)
            half_top = _distance(top[0], top[1]) / 2
            outline = [(_dot(_sub(p, mid_top), across), _dot(_sub(p, mid_top), along)) for p in panel.points]
            for k, (offset, profile) in enumerate(zip(layout.offsets(), layout.profiles, strict=True), start=1):
                stop = layout.stop(k - 1)
                if abs(offset) > half_top - TOL:
                    raise ValueError(f"{panel.name}: stiffener {k} at {offset:+.0f} mm is outside the panel")
                bottom = _lowest(outline, offset)
                if _is_tier_bottom(panel, spec):
                    bottom = max(bottom, min(v for _, v in outline) + layout.bottom_clearance)
                top_end = (layout.top_extension if panel.name in beam_panels else 0.0) - stop
                if bottom >= top_end:
                    raise ValueError(f"{panel.name}: stiffener {k} has no length")
                heel = _add(mid_top, _add(_scale(across, offset), _scale(panel.normal, spec.plate_thickness)))
                result.append(
                    Stiffener(
                        f"Stiff-{panel.name}-{k:02d}",
                        panel.name,
                        stiffening.sections[profile],
                        top_end - bottom,
                        _add(heel, _scale(along, bottom)),
                        along,
                        panel.normal,
                        across,
                    )
                )
    return result


def beam_section(beam: Beam) -> list[tuple[float, float]]:
    """Channel outline in (outward, up) coordinates from the beam origin: web on top, flanges down."""
    s = beam.section
    d, b, tw, tf = s.depth, s.width, s.web_thickness, s.flange_thickness
    return [(0, 0), (d, 0), (d, -b), (d - tf, -b), (d - tf, -tw), (tf, -tw), (tf, -b), (0, -b)]


def h_section(section: Section) -> list[tuple[float, float]]:
    """H outline in (x, y) from its centre: flanges parallel to x, web along y."""
    h, b, tw, tf = section.depth / 2, section.width / 2, section.web_thickness / 2, section.flange_thickness
    return [
        (-b, -h), (b, -h), (b, -h + tf), (tw, -h + tf), (tw, h - tf), (b, h - tf),
        (b, h), (-b, h), (-b, h - tf), (-tw, h - tf), (-tw, -h + tf), (-b, -h + tf),
    ]  # fmt: skip


def stiffener_section(stiffener: Stiffener) -> list[tuple[float, float]]:
    """Angle outline in (across, normal) coordinates from the heel: one leg on the plate, one standing."""
    s = stiffener.section
    t = s.web_thickness
    return [(-t / 2, 0), (s.width - t / 2, 0), (s.width - t / 2, t), (t / 2, t), (t / 2, s.depth), (-t / 2, s.depth)]


def mass_kg(section: Section, length: float) -> float:
    return section.mass_per_m * length / 1000


def _panel_axes(panel: Panel) -> tuple[Vec, Vec]:
    """(up the panel square to the top edge, along the top edge), as in hopper_geometry.flat_contour."""
    across = _unit(_cross((0.0, 0.0, 1.0), panel.normal))
    along = _cross(panel.normal, across)
    if along[2] < 0:
        along, across = _neg(along), _neg(across)
    return along, across


def _lowest(outline: list[tuple[float, float]], u: float) -> float:
    """Lowest point of the outline on the line at `u` (outline in (across, along) coordinates)."""
    found = []
    for (u0, v0), (u1, v1) in zip(outline, [*outline[1:], outline[0]], strict=True):
        if min(u0, u1) - TOL <= u <= max(u0, u1) + TOL:
            found += [v0, v1] if abs(u1 - u0) < TOL else [v0 + (v1 - v0) * (u - u0) / (u1 - u0)]
    return min(found)


def _reaches_tier_top(panel: Panel, spec: HopperSpec) -> bool:
    return abs(max(p[2] for p in panel.points) - sum(spec.tier_heights[: panel.tier])) < TOL


def _is_tier_bottom(panel: Panel, spec: HopperSpec) -> bool:
    joint = sum(spec.tier_heights[: panel.tier - 1])
    return min(p[2] for p in panel.points) - joint < spec.panel_gap + TOL


def _add(a: Vec, b: Vec) -> Vec:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec, b: Vec) -> Vec:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _scale(a: Vec, k: float) -> Vec:
    return a[0] * k, a[1] * k, a[2] * k


def _neg(a: Vec) -> Vec:
    return -a[0], -a[1], -a[2]


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _unit(a: Vec) -> Vec:
    return _scale(a, 1 / math.sqrt(_dot(a, a)))


def _distance(a: Vec, b: Vec) -> float:
    return math.sqrt(_dot(_sub(a, b), _sub(a, b)))
