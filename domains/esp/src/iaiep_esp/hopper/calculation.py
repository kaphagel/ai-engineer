"""Hopper geometry calculated independently of the CAD model (calculation record, spec §11).

Deliberately a separate implementation from the worker's geometry code (different method: closed
formulas, bisection and numerical integration), so that comparing the two checks the model.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass

from iaiep_esp.hopper.inputs import HopperParameters


@dataclass(frozen=True)
class PanelSize:
    width_mm: float
    height_mm: float  # along the wall (slant height)
    area_m2: float


@dataclass(frozen=True)
class HopperCalculation:
    inner_top_length_mm: float
    inner_top_width_mm: float
    side_wall_slope_deg: float
    end_wall_slope_deg: float
    valley_angle_deg: float
    capacity_m3: float
    panels: dict[str, PanelSize]

    def plate_mass_kg(self, thickness_mm: float, density_kg_m3: float) -> float:
        return sum(p.area_m2 for p in self.panels.values()) * thickness_mm / 1000 * density_kg_m3


def calculate(params: HopperParameters) -> HopperCalculation:
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
        for part, za, zb, slope in (
            ("lower", z_bottom, min(z_top, hv), math.pi / 2),
            ("upper", max(z_bottom, hv), z_top, end),
        ):
            if zb - za <= 1e-9:
                continue
            suffix = "" if (za, zb) == (z_bottom, z_top) else f"-{part}"
            if za == z_bottom:
                za += g * math.sin(slope)
            size = PanelSize(
                2 * half_w(zb),
                (zb - za) / math.sin(slope),
                _integrate(lambda z: 2 * half_w(z), za, zb) / math.sin(slope) / 1e6,
            )
            panels[f"EndOutlet-T{k}{suffix}"] = panels[f"EndInlet-T{k}{suffix}"] = size
        z_bottom = z_top

    return HopperCalculation(
        inner_top_length_mm=lt,
        inner_top_width_mm=wt,
        side_wall_slope_deg=math.degrees(side),
        end_wall_slope_deg=math.degrees(end),
        valley_angle_deg=math.degrees(valley),
        capacity_m3=capacity,
        panels=panels,
    )


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
