import pytest

from iaiep_worker import hopper_geometry as geo
from iaiep_worker import hopper_profiles as hp

PARAMS = {
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
CHANNEL = {
    "kind": "channel",
    "designation": "C",
    "standard": "-",
    "material": "-",
    "depth_mm": 200,
    "width_mm": 75,
    "web_thickness_mm": 8.5,
    "flange_thickness_mm": 11.5,
    "mass_per_m_kg": 25.0,
}
ANGLE = {**CHANNEL, "kind": "angle", "depth_mm": 75, "width_mm": 50, "web_thickness_mm": 6, "mass_per_m_kg": 5.0}


def stiffening(layouts: list[dict[str, object]]) -> hp.Stiffening:
    return hp.Stiffening.from_job(
        {
            "profiles": {"C": CHANNEL, "L": ANGLE},
            "tier_beams": {
                "side_profile": "C",
                "end_profile": "C",
                "side_end_extensions_mm": [10, 10],
                "end_end_extensions_mm": [0, 0],
            },
            "stiffeners": [{"top_extension_mm": 30, **layout} for layout in layouts],
        }
    )


SPEC = geo.HopperSpec.from_parameters(PARAMS)
PANELS = geo.panels(SPEC)


def test_one_beam_per_wall_at_each_tier_joint_carrying_the_upper_plate() -> None:
    beams = hp.tier_beams(SPEC, PANELS, stiffening([]))
    assert sorted(b.name for b in beams if b.name.startswith("Beam-SideLeft")) == [
        "Beam-SideLeft-J1",
        "Beam-SideLeft-J2",
    ]
    assert len(beams) == 8
    side = next(b for b in beams if b.name == "Beam-SideLeft-J2")
    lower = geo.flat_size(geo.flat_contour(next(p for p in PANELS if p.name == "SideLeft-T2")))
    assert side.length == pytest.approx(lower[0] + 2 * 10)
    upper = next(p for p in PANELS if p.name == "SideLeft-T3")
    lowest_outer = min(p[2] for p in upper.points) + 5 * upper.normal[2]
    assert side.origin[2] == pytest.approx(lowest_outer)


def test_stiffeners_symmetric_and_reach_into_the_beam() -> None:
    layout = {
        "wall": "side",
        "tier": 2,
        "bays_mm": [1000, 1200],
        "profiles": ["L", "L", "L"],
        "bottom_clearance_mm": 20,
    }
    found = [s for s in hp.stiffeners(SPEC, PANELS, stiffening([layout])) if s.panel == "SideLeft-T2"]
    slant = geo.flat_size(geo.flat_contour(next(p for p in PANELS if p.name == "SideLeft-T2")))[1]
    assert [s.length for s in found] == pytest.approx([slant - 20 + 30] * 3)
    xs = [s.origin[0] for s in found]
    assert xs[0] + xs[2] == pytest.approx(0) and abs(xs[0] - xs[2]) == pytest.approx(2200)


def test_stiffener_beyond_the_narrow_bottom_starts_on_the_sloped_edge() -> None:
    # End wall tier 1 is vertical: 400 wide at the slot, wider at the top. A stiffener at 300 mm from the
    # centreline starts where the sloped side edge passes 300 mm.
    layout = {"wall": "end", "tier": 1, "bays_mm": [600], "profiles": ["L", "L"], "bottom_clearance_mm": 0}
    found = hp.stiffeners(SPEC, PANELS, stiffening([layout]))
    shape = geo.inner_shape(SPEC)
    z_start = (300 - 200) / ((shape.top_width - 400) / 2) * SPEC.height
    assert found[0].length == pytest.approx(1200 - z_start + 30)
    assert found[0].origin[2] == pytest.approx(z_start)
    assert len(found) == 4


def test_layout_errors() -> None:
    wide = {"wall": "end", "tier": 1, "bays_mm": [3000], "profiles": ["L", "L"], "bottom_clearance_mm": 0}
    with pytest.raises(ValueError, match="outside the panel"):
        hp.stiffeners(SPEC, PANELS, stiffening([wide]))
    with pytest.raises(ValueError, match="need 2 profiles"):
        stiffening([{**wide, "profiles": ["L"]}])
    with pytest.raises(ValueError, match="not an angle"):
        stiffening([{**wide, "profiles": ["C", "C"]}])


def test_bottom_clearance_is_measured_from_the_plate_bottom_not_added_to_the_edge() -> None:
    layout = {"wall": "end", "tier": 1, "bays_mm": [600], "profiles": ["L", "L"], "bottom_clearance_mm": 400}
    found = hp.stiffeners(SPEC, PANELS, stiffening([layout]))
    assert found[0].origin[2] == pytest.approx(400)
    assert found[0].length == pytest.approx(1200 - 400 + 30)


H_SECTION = {**CHANNEL, "kind": "h_section", "depth_mm": 160, "width_mm": 160, "web_thickness_mm": 8}


def with_top(top: dict[str, object], supports: dict[str, object] | None = None) -> hp.Stiffening:
    base = stiffening([])
    data = {
        "profiles": {"C": CHANNEL, "L": ANGLE, "H": H_SECTION},
        "top_beams": top,
        "supports": supports,
    }
    extra = hp.Stiffening.from_job(data)
    return hp.Stiffening(
        extra.sections,
        base.side_beam,
        base.end_beam,
        base.side_beam_extensions,
        (0.0, 0.0),
        (),
        extra.top,
        extra.supports,
    )


TOP = {
    "side_profile": "C",
    "end_profile": "C",
    "side_end_extension_mm": -10,
    "end_end_extension_mm": 0,
    "side_splits_mm": [-1000, 1000],
}


def test_top_beam_is_split_into_segments_resting_on_the_top_edge() -> None:
    beams = [b for b in hp.top_beams(SPEC, PANELS, with_top(TOP)) if b.panel == "SideLeft-T3"]
    top_edge = geo.flat_size(geo.flat_contour(next(p for p in PANELS if p.name == "SideLeft-T3")))[0]
    assert [b.name for b in beams] == ["Beam-SideLeft-Top-1", "Beam-SideLeft-Top-2", "Beam-SideLeft-Top-3"]
    assert sum(b.length for b in beams) == pytest.approx(top_edge - 20)
    assert beams[1].length == pytest.approx(2000)
    assert all(b.origin[2] == pytest.approx(4200 + 8.5) for b in beams)  # web thickness above the top edge


def test_supports_stack_column_plate_stub_and_base_plate_at_each_grid_point() -> None:
    supports = {
        "grid_x_mm": [-4100, 0, 4100],
        "grid_y_mm": [-2000, 2000],
        "stub_profile": "H",
        "stub_length_mm": 700,
        "column_plate_top_above_top_mm": 8.5,
        "corner_column_plate_mm": [220, 220, 15],
        "side_column_plate_mm": [220, 190, 15],
        "base_plate_mm": [280, 280, 20],
        "plate_material": "-",
    }
    stubs, boxes = hp.supports(SPEC, PANELS, with_top(TOP, supports))
    assert len(stubs) == 6 and len(boxes) == 12
    corner = next(s for s in stubs if s.name == "Stub-P4100_P2000")
    side = next(s for s in stubs if s.name == "Stub-P0_M2000")
    assert (corner.panel, side.panel) == ("EndOutlet-T3", "SideRight-T3")
    assert corner.origin == pytest.approx((4100, 2000, 4208.5 - 15 - 700))
    base = next(b for b in boxes if b.name == "BasePlate-P4100_P2000")
    assert base.centre[2] + base.size[2] == pytest.approx(corner.origin[2])


def test_stops_shorten_single_stiffeners_at_the_top() -> None:
    layout = {
        "wall": "side",
        "tier": 3,
        "bays_mm": [1000],
        "profiles": ["L", "L"],
        "bottom_clearance_mm": 0,
        "top_extension_mm": -20,
        "stops_below_top_mm": [0, 500],
    }
    data = {"profiles": {"C": CHANNEL, "L": ANGLE}, "top_beams": TOP, "stiffeners": [layout]}
    found = [s for s in hp.stiffeners(SPEC, PANELS, hp.Stiffening.from_job(data)) if s.panel == "SideLeft-T3"]
    slant = geo.flat_size(geo.flat_contour(next(p for p in PANELS if p.name == "SideLeft-T3")))[1]
    assert [s.length for s in found] == pytest.approx([slant - 20, slant - 520])


def test_clip_to_wall_keeps_only_the_part_outside_the_wall_face() -> None:
    # Wall face n = 100 + 0.5 z: a 200 x 100 rectangle from n = 50 is cut along that line.
    section = hp.clip_to_wall([(50, 0), (250, 0), (250, 100), (50, 100)], lambda z: 100 + 0.5 * z)
    assert sorted((round(n, 9), round(z, 9)) for n, z in section) == [(100, 0), (150, 100), (250, 0), (250, 100)]
    assert hp.clip_to_wall([(0, 0), (10, 0), (10, 10), (0, 10)], lambda z: 100.0) == []
