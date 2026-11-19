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
- Simplified representation: sections are drawn with the nominal dimensions (no root radii), the mass
  comes from the catalogue mass per metre; copes, cut-outs and corner connections are not modelled, so
  parts may overlap at connections (reported, not an error).
"""

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from iaiep_worker.hopper_geometry import HopperSpec, Panel, Vec

TOL = 1e-6


@dataclass(frozen=True)
class Section:
    name: str
    kind: str  # "channel", "angle" or "h_section"
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


def supports(spec: HopperSpec, panels: Sequence[Panel], stiffening: Stiffening) -> tuple[list[Stub], list[Box]]:
    """Column stubs with column and base plates at the support grid points on the hopper perimeter."""
    sup = stiffening.supports
    if sup is None:
        return [], []
    section = stiffening.sections[sup.stub_profile]
    top_panels = {p.wall: p.name for p in top_tier_panels(spec, panels)}
    stubs, boxes = [], []
    top_level = spec.height + sup.top_above_hopper_top
    for i, x in enumerate(sup.grid_x):
        corner = i in (0, len(sup.grid_x) - 1)
        for y in sup.grid_y:
            end = "EndInlet" if i == 0 else "EndOutlet"
            wall = end if corner else "SideLeft" if y > 0 else "SideRight"
            name = f"{x:+.0f}_{y:+.0f}".replace("+", "P").replace("-", "M")
            panel = top_panels[wall]
            plate = sup.corner_plate if corner else sup.side_plate
            stub_top = top_level - plate[2]
            stub_bottom = stub_top - sup.stub_length
            dy = 0.0 if corner else math.copysign(sup.side_plate_offset, y)
            boxes.append(Box(f"ColumnPlate-{name}", panel, "column plate", (x, y + dy, stub_top), plate, sup.material))
            stubs.append(Stub(f"Stub-{name}", panel, section, sup.stub_length, (x, y, stub_bottom)))
            base = sup.base_plate
            boxes.append(
                Box(f"BasePlate-{name}", panel, "base plate", (x, y, stub_bottom - base[2]), base, sup.material)
            )
    return stubs, boxes


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


def box_mass_kg(box: Box, density_kg_m3: float) -> float:
    return box.size[0] * box.size[1] * box.size[2] * 1e-9 * density_kg_m3


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
