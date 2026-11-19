"""Hopper geometry calculated independently of the CAD model (calculation record, spec §11).

Deliberately a separate implementation from the worker's geometry code (different method: closed
formulas, bisection and numerical integration), so that comparing the two checks the model.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from iaiep_esp.hopper.inputs import HopperCase


@dataclass(frozen=True)
class PanelSize:
    width_mm: float
    height_mm: float  # along the wall (slant height)
    area_m2: float


@dataclass(frozen=True)
class ProfilePart:
    kind: str  # "beam", "top_beam", "stiffener" or "stub"
    panel: str
    profile: str
    length_mm: float
    mass_kg: float
    position_mm: tuple[float, float] | None = None  # stubs: plan position of the centre
    top_z_mm: float | None = None  # stubs: top end


@dataclass(frozen=True)
class Fitting:
    """Column or base plate at a support."""

    kind: str
    panel: str
    size_mm: tuple[float, float, float]  # along x, along y, thickness
    position_mm: tuple[float, float]
    z_mm: tuple[float, float]  # bottom and top
    mass_kg: float


@dataclass(frozen=True)
class _Piece:
    """One flat panel: wall, tier, plate bottom and top height, slope, half size along its top edge."""

    name: str
    wall: str
    tier: int
    z_low: float
    z_high: float
    slope: float
    half: Callable[[float], float]
    at_tier_bottom: bool
    at_tier_top: bool


@dataclass(frozen=True)
class HopperCalculation:
    inner_top_length_mm: float
    inner_top_width_mm: float
    side_wall_slope_deg: float
    end_wall_slope_deg: float
    valley_angle_deg: float
    capacity_m3: float
    panels: dict[str, PanelSize]
    profiles: dict[str, ProfilePart]
    fittings: dict[str, Fitting]

    def profile_mass_kg(self) -> float:
        return sum(p.mass_kg for p in self.profiles.values())

    def fitting_mass_kg(self) -> float:
        return sum(f.mass_kg for f in self.fittings.values())

    def plate_mass_kg(self, thickness_mm: float, density_kg_m3: float) -> float:
        return sum(p.area_m2 for p in self.panels.values()) * thickness_mm / 1000 * density_kg_m3


def calculate(case: HopperCase) -> HopperCalculation:
    params = case.parameters
    h = params.height_mm.value
    hv = params.end_wall_vertical_height_mm.value
    t = params.plate_thickness_mm.value
    gap = params.panel_gap_mm.value
    ls = params.slot_length_inside_mm.value
    ws = params.slot_width_inside_mm.value
    tiers = params.tier_heights_mm.value

    # Outside = inside + 2 t / sin(slope); slope depends on the inside size. Solve by bisection.
    wt = _inside_from_outside(params.top_width_outside_mm.value, ws, h, t)
    lt = _inside_from_outside(params.top_length_outside_mm.value, ls, h - hv, t)

    side = math.atan(h / ((wt - ws) / 2))
    end = math.atan((h - hv) / ((lt - ls) / 2))

    def half_w(z: float) -> float:
        return ws / 2 + (wt - ws) / 2 * z / h

    def half_l(z: float) -> float:
        return ls / 2 if z <= hv else ls / 2 + (lt - ls) / 2 * (z - hv) / (h - hv)

    corner_dy = half_w(h) - half_w(hv)
    valley = math.atan((h - hv) / math.hypot((lt - ls) / 2, corner_dy))
    capacity = _integrate(lambda z: 4 * half_l(z) * half_w(z), 0.0, h) / 1e9

    panels: dict[str, PanelSize] = {}
    pieces: list[_Piece] = []
    z_bottom = 0.0
    top_gap = params.top_gap_mm.value if params.top_gap_mm is not None else 0.0
    for k, tier_height in enumerate(tiers, start=1):
        z_top = z_bottom + tier_height
        g = gap if k > 1 else 0.0
        g_top = top_gap if k == len(tiers) else 0.0
        z0 = z_bottom + g * math.sin(side)
        z1 = z_top - g_top * math.sin(side)
        size = PanelSize(
            2 * half_l(z1),
            (z1 - z0) / math.sin(side),
            _integrate(lambda z: 2 * half_l(z), z0, z1) / math.sin(side) / 1e6,
        )
        panels[f"SideLeft-T{k}"] = panels[f"SideRight-T{k}"] = size
        for wall in ("SideLeft", "SideRight"):
            pieces.append(_Piece(f"{wall}-T{k}", wall, k, z0, z1, side, half_l, True, True))
        for part, za, zb, slope in (
            ("lower", z_bottom, min(z_top, hv), math.pi / 2),
            ("upper", max(z_bottom, hv), z_top, end),
        ):
            if zb - za <= 1e-9:
                continue
            suffix = "" if (za, zb) == (z_bottom, z_top) else f"-{part}"
            at_bottom = za == z_bottom
            at_top = zb == z_top
            if at_bottom:
                za += g * math.sin(slope)
            if at_top:
                zb -= g_top * math.sin(slope)
            size = PanelSize(
                2 * half_w(zb),
                (zb - za) / math.sin(slope),
                _integrate(lambda z: 2 * half_w(z), za, zb) / math.sin(slope) / 1e6,
            )
            panels[f"EndOutlet-T{k}{suffix}"] = panels[f"EndInlet-T{k}{suffix}"] = size
            for wall in ("EndOutlet", "EndInlet"):
                pieces.append(_Piece(f"{wall}-T{k}{suffix}", wall, k, za, zb, slope, half_w, at_bottom, at_top))
        z_bottom = z_top

    return HopperCalculation(
        inner_top_length_mm=lt,
        inner_top_width_mm=wt,
        side_wall_slope_deg=math.degrees(side),
        end_wall_slope_deg=math.degrees(end),
        valley_angle_deg=math.degrees(valley),
        capacity_m3=capacity,
        panels=panels,
        profiles=_profiles(case, pieces, len(tiers), h),
        fittings=_fittings(case, pieces, h),
    )


def _profiles(case: HopperCase, pieces: list[_Piece], tiers: int, h: float) -> dict[str, ProfilePart]:
    """Tier and top beams, stiffeners and column stubs (rules in ADR-0004), with catalogue masses."""
    st = case.stiffening
    if st is None:
        return {}
    result: dict[str, ProfilePart] = {}

    def add(
        name: str,
        kind: str,
        panel: str,
        profile: str,
        length: float,
        position: tuple[float, float] | None = None,
        top_z: float | None = None,
    ) -> None:
        mass = case.profiles[profile].mass_per_m_kg * length / 1000
        result[name] = ProfilePart(kind, panel, profile, length, mass, position, top_z)

    beam_panels = set()
    if st.tier_beams is not None:
        tb = st.tier_beams
        for p in pieces:
            if p.tier < tiers and p.at_tier_top:
                side = p.wall.startswith("Side")
                extension = (tb.side_end_extensions_mm if side else tb.end_end_extensions_mm)[p.tier - 1]
                profile = tb.side_profile if side else tb.end_profile
                add(f"Beam-{p.wall}-J{p.tier}", "beam", p.name, profile, 2 * p.half(p.z_high) + 2 * extension)
                beam_panels.add(p.name)

    if st.top_beams is not None:
        top = st.top_beams
        for p in pieces:
            if p.tier != tiers or not p.at_tier_top:
                continue
            side = p.wall.startswith("Side")
            half = p.half(p.z_high) + (top.side_end_extension_mm if side else top.end_end_extension_mm)
            cuts = sorted(top.side_splits_mm if side else top.end_splits_mm)
            if half <= 0 or any(abs(c) >= half for c in cuts):
                raise ValueError(f"{p.name}: top beam splits outside the beam")
            ends = [-half, *cuts, half]
            for k in range(len(ends) - 1):
                suffix = "" if len(ends) == 2 else f"-{k + 1}"
                profile = top.side_profile if side else top.end_profile
                add(f"Beam-{p.wall}-Top{suffix}", "top_beam", p.name, profile, ends[k + 1] - ends[k])
            beam_panels.add(p.name)

    for layout in st.stiffeners:
        total = sum(layout.bays_mm)
        offsets = [sum(layout.bays_mm[:i]) - total / 2 for i in range(len(layout.profiles))]
        for p in pieces:
            if p.tier != layout.tier or p.wall.startswith("Side") != (layout.wall == "side"):
                continue
            for k, (x, profile) in enumerate(zip(offsets, layout.profiles, strict=True), start=1):
                if abs(x) >= p.half(p.z_high):
                    raise ValueError(f"{p.name}: stiffener {k} at {x:+.0f} mm is outside the panel")
                z_start = p.z_low if p.half(p.z_low) >= abs(x) else _solve(p.half, abs(x), p.z_low, p.z_high)
                if p.at_tier_bottom:
                    z_start = max(z_start, p.z_low + layout.bottom_clearance_mm * math.sin(p.slope))
                length = (p.z_high - z_start) / math.sin(p.slope)
                length += layout.top_extension_mm if p.name in beam_panels else 0.0
                length -= layout.stops_below_top_mm[k - 1] if layout.stops_below_top_mm else 0.0
                if length <= 0:
                    raise ValueError(f"{p.name}: stiffener {k} has no length")
                add(f"Stiff-{p.name}-{k:02d}", "stiffener", p.name, profile, length)

    sup = st.supports
    if sup is not None:
        for name, point in _support_points(case, pieces, h).items():
            stub_top = h + sup.column_plate_top_above_top_mm - point.plate[2]
            add(f"Stub-{name}", "stub", point.panel, sup.stub_profile, sup.stub_length_mm, point.xy, stub_top)
    return result


@dataclass(frozen=True)
class _SupportPoint:
    xy: tuple[float, float]
    panel: str
    plate: tuple[float, float, float]  # column plate
    plate_offset_y: float  # column plate centre from the grid line, across the hopper


def _support_points(case: HopperCase, pieces: list[_Piece], h: float) -> dict[str, _SupportPoint]:
    """Grid points on the perimeter: corners carried by the end walls, the others by the side walls."""
    sup = case.stiffening.supports if case.stiffening else None
    if sup is None:
        return {}
    tiers = len(case.parameters.tier_heights_mm.value)
    top_piece = {p.wall: p.name for p in pieces if p.tier == tiers and p.at_tier_top}
    xs, ys = sup.grid_x_mm, sup.grid_y_mm
    points = {}
    for x in xs:
        corner = x in (xs[0], xs[-1])
        for y in ys:
            wall = ("EndInlet" if x == xs[0] else "EndOutlet") if corner else ("SideLeft" if y > 0 else "SideRight")
            a, b, c = sup.corner_column_plate_mm if corner else sup.side_column_plate_mm
            name = f"{x:+.0f}_{y:+.0f}".replace("+", "P").replace("-", "M")
            offset = 0.0 if corner else math.copysign(sup.side_column_plate_outward_offset_mm, y)
            points[name] = _SupportPoint((x, y), top_piece[wall], (a, b, c), offset)
    return points


def _fittings(case: HopperCase, pieces: list[_Piece], h: float) -> dict[str, Fitting]:
    sup = case.stiffening.supports if case.stiffening else None
    if sup is None:
        return {}
    density = case.material.density_kg_m3.value
    result = {}
    for name, point in _support_points(case, pieces, h).items():
        top = h + sup.column_plate_top_above_top_mm
        stub_bottom = top - point.plate[2] - sup.stub_length_mm
        bx, by, bt = sup.base_plate_mm
        x, y = point.xy
        for kind, size, z0, dy in (
            ("column plate", point.plate, top - point.plate[2], point.plate_offset_y),
            ("base plate", (bx, by, bt), stub_bottom - bt, 0.0),
        ):
            mass = size[0] * size[1] * size[2] * 1e-9 * density
            label = "ColumnPlate" if kind == "column plate" else "BasePlate"
            result[f"{label}-{name}"] = Fitting(kind, point.panel, size, (x, y + dy), (z0, z0 + size[2]), mass)
    return result


def _solve(f: Callable[[float], float], target: float, lo: float, hi: float) -> float:
    """Lowest z in [lo, hi] with f(z) = target, for f non-decreasing (bisection)."""
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _inside_from_outside(outside: float, bottom: float, rise: float, t: float) -> float:
    def excess(inside: float) -> float:
        run = (inside - bottom) / 2
        return inside + 2 * t * math.hypot(run, rise) / rise - outside

    lo, hi = bottom, outside
    for _ in range(200):
        mid = (lo + hi) / 2
        if excess(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _integrate(f: Callable[[float], float], a: float, b: float, steps: int = 2000) -> float:
    """Trapezoidal rule; the integrands here are piecewise polynomials of degree two or less."""
    if b <= a:
        return 0.0
    dz = (b - a) / steps
    return dz * (sum(f(a + i * dz) for i in range(1, steps)) + (f(a) + f(b)) / 2)
