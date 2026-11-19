import math

import pytest

from iaiep_worker import hopper_geometry as geo

TROUGH = {
    "top_length_outside_mm": 8000,
    "top_width_outside_mm": 3800,
    "slot_length_inside_mm": 6500,
    "slot_width_inside_mm": 400,
    "height_mm": 4200,
    "end_wall_vertical_height_mm": 1200,
    "tier_heights_mm": [1200, 1500, 1500],
    "plate_thickness_mm": 5,
    "panel_gap_mm": 20,
}


def spec(**changes: object) -> geo.HopperSpec:
    return geo.HopperSpec.from_parameters({**TROUGH, **changes})


def test_outside_top_is_inside_plus_plate_offset() -> None:
    s = spec()
    shape = geo.inner_shape(s)
    side = math.radians(shape.side_wall_slope_deg())
    assert shape.top_width + 2 * 5 / math.sin(side) == pytest.approx(3800, abs=1e-6)


def test_upper_panels_are_shortened_by_the_gap_along_the_wall() -> None:
    no_gap = {p.name: geo.flat_size(geo.flat_contour(p)) for p in geo.panels(spec(panel_gap_mm=0))}
    gap = {p.name: geo.flat_size(geo.flat_contour(p)) for p in geo.panels(spec())}
    assert gap["SideLeft-T1"] == pytest.approx(no_gap["SideLeft-T1"])
    assert no_gap["SideLeft-T2"][1] - gap["SideLeft-T2"][1] == pytest.approx(20)
    assert no_gap["EndOutlet-T3"][1] - gap["EndOutlet-T3"][1] == pytest.approx(20)


def test_lower_tier_has_vertical_rectangular_end_and_side_panels() -> None:
    panels = {p.name: p for p in geo.panels(spec())}
    assert len(panels) == 12
    assert panels["EndOutlet-T1"].normal == pytest.approx((1.0, 0.0, 0.0))
    width, height = geo.flat_size(geo.flat_contour(panels["SideLeft-T1"]))
    assert width == pytest.approx(6500)
    assert geo.polygon_area(geo.flat_contour(panels["SideLeft-T1"])) == pytest.approx(width * height)


def test_end_wall_is_split_where_it_changes_slope_inside_a_tier() -> None:
    names = {p.name for p in geo.panels(spec(end_wall_vertical_height_mm=600))}
    assert {"EndOutlet-T1-lower", "EndOutlet-T1-upper"} <= names
    assert "SideLeft-T1" in names  # side walls stay one panel per tier


def test_pyramid_is_the_case_without_vertical_end_walls() -> None:
    s = spec(slot_length_inside_mm=400, end_wall_vertical_height_mm=0, panel_gap_mm=0)
    shape = geo.inner_shape(s)
    dx = (shape.top_length - 400) / 2
    dy = (shape.top_width - 400) / 2
    assert shape.valley_angle_deg() == pytest.approx(math.degrees(math.atan2(4200, math.hypot(dx, dy))))
    # Prismoidal formula, exact for a frustum with planar faces.
    mid = ((shape.top_length + 400) / 2) * ((shape.top_width + 400) / 2)
    volume = 4200 / 6 * (shape.top_length * shape.top_width + 400 * 400 + 4 * mid) / 1e9
    assert shape.capacity_m3() == pytest.approx(volume)


def test_inconsistent_tiers_are_rejected() -> None:
    with pytest.raises(ValueError, match="tier heights add up to"):
        spec(tier_heights_mm=[1200, 1500])


def test_top_gap_shortens_only_the_top_panels_along_the_wall() -> None:
    plain = {p.name: geo.flat_size(geo.flat_contour(p)) for p in geo.panels(spec())}
    gapped = {p.name: geo.flat_size(geo.flat_contour(p)) for p in geo.panels(spec(top_gap_mm=5))}
    assert gapped["SideLeft-T3"][1] == pytest.approx(plain["SideLeft-T3"][1] - 5)
    assert gapped["EndOutlet-T3"][1] == pytest.approx(plain["EndOutlet-T3"][1] - 5)
    assert gapped["SideLeft-T2"] == pytest.approx(plain["SideLeft-T2"])


def test_plates_at_a_bend_inside_a_tier_are_mitred_on_the_bisector() -> None:
    s = spec(end_wall_vertical_height_mm=1800)  # bend inside tier 2
    panels = geo.panels(s)
    cuts = geo.mitre_cuts(s, panels)
    assert sorted(cuts) == ["EndInlet-T2-lower", "EndInlet-T2-upper", "EndOutlet-T2-lower", "EndOutlet-T2-upper"]
    by_name = {p.name: p for p in panels}
    lower, upper = by_name["EndOutlet-T2-lower"], by_name["EndOutlet-T2-upper"]
    ((point, normal),) = cuts[lower.name]

    def side(q: tuple[float, ...]) -> float:
        return sum(n * (a - b) for n, a, b in zip(normal, q, point, strict=True))

    # The plane holds the inner bend line and the point where both outer faces meet.
    bend = [p for p in lower.points if p[2] == pytest.approx(1800)]
    assert [side(p) for p in bend] == pytest.approx([0, 0], abs=1e-9)
    n1, n2 = lower.normal, upper.normal
    k = 5 / (1 + sum(a * b for a, b in zip(n1, n2, strict=True)))
    outer = tuple(p + k * (a + b) for p, a, b in zip(bend[0], n1, n2, strict=True))
    assert side(outer) == pytest.approx(0, abs=1e-9)
    # Each plate keeps its own side.
    assert all(side(p) <= 1e-9 for p in lower.points) and all(side(p) >= -1e-9 for p in upper.points)
    assert cuts[upper.name][0][1] == pytest.approx(tuple(-n for n in normal))
