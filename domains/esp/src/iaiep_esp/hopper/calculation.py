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
    kind: str  # "beam" or "stiffener"
    panel: str
    profile: str
    length_mm: float
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

    def profile_mass_kg(self) -> float:
        return sum(p.mass_kg for p in self.profiles.values())

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
    for k, tier_height in enumerate(tiers, start=1):
        z_top = z_bottom + tier_height
        g = gap if k > 1 else 0.0
        z0 = z_bottom + g * math.sin(side)
        size = PanelSize(
            2 * half_l(z_top),
            (z_top - z0) / math.sin(side),
            _integrate(lambda z: 2 * half_l(z), z0, z_top) / math.sin(side) / 1e6,
        )
        panels[f"SideLeft-T{k}"] = panels[f"SideRight-T{k}"] = size
        for wall in ("SideLeft", "SideRight"):
            pieces.append(_Piece(f"{wall}-T{k}", wall, k, z0, z_top, side, half_l, True, True))
        for part, za, zb, slope in (
            ("lower", z_bottom, min(z_top, hv), math.pi / 2),
            ("upper", max(z_bottom, hv), z_top, end),
        ):
            if zb - za <= 1e-9:
                continue
            suffix = "" if (za, zb) == (z_bottom, z_top) else f"-{part}"
            at_bottom = za == z_bottom
            if at_bottom:
                za += g * math.sin(slope)
            size = PanelSize(
                2 * half_w(zb),
                (zb - za) / math.sin(slope),
                _integrate(lambda z: 2 * half_w(z), za, zb) / math.sin(slope) / 1e6,
            )
            panels[f"EndOutlet-T{k}{suffix}"] = panels[f"EndInlet-T{k}{suffix}"] = size
            for wall in ("EndOutlet", "EndInlet"):
                pieces.append(_Piece(f"{wall}-T{k}{suffix}", wall, k, za, zb, slope, half_w, at_bottom, zb == z_top))
        z_bottom = z_top

    return HopperCalculation(
        inner_top_length_mm=lt,
        inner_top_width_mm=wt,
        side_wall_slope_deg=math.degrees(side),
        end_wall_slope_deg=math.degrees(end),
        valley_angle_deg=math.degrees(valley),
        capacity_m3=capacity,
        panels=panels,
        profiles=_profiles(case, pieces, len(tiers)),
    )


def _profiles(case: HopperCase, pieces: list[_Piece], tiers: int) -> dict[str, ProfilePart]:
    """Tier beams and stiffeners (rules in ADR-0004), with catalogue masses."""
    st = case.stiffening
    if st is None:
        return {}
    result: dict[str, ProfilePart] = {}

    def add(name: str, kind: str, panel: str, profile: str, length: float) -> None:
        mass = case.profiles[profile].mass_per_m_kg * length / 1000
        result[name] = ProfilePart(kind, panel, profile, length, mass)

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
                if length <= 0:
                    raise ValueError(f"{p.name}: stiffener {k} has no length")
                add(f"Stiff-{p.name}-{k:02d}", "stiffener", p.name, profile, length)
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
