from pathlib import Path

import pytest
from pydantic import ValidationError

from iaiep_esp.hopper.calculation import calculate
from iaiep_esp.hopper.cli import build_job
from iaiep_esp.hopper.inputs import HopperCase
from iaiep_worker import hopper_geometry as geo
from iaiep_worker import hopper_profiles as hp

EXAMPLE = Path(__file__).parents[1] / "examples" / "hopper_synthetic.toml"


@pytest.fixture
def case() -> HopperCase:
    return HopperCase.load(EXAMPLE)


def test_calculation_agrees_with_the_independent_worker_geometry(case: HopperCase) -> None:
    calc = calculate(case)
    spec = geo.HopperSpec.from_parameters(case.parameters.values())
    shape = geo.inner_shape(spec)
    assert calc.inner_top_length_mm == pytest.approx(shape.top_length, abs=1e-6)
    assert calc.valley_angle_deg == pytest.approx(shape.valley_angle_deg(), abs=1e-9)
    assert calc.capacity_m3 == pytest.approx(shape.capacity_m3(), rel=1e-6)
    for panel in geo.panels(spec):
        contour = geo.flat_contour(panel)
        assert (calc.panels[panel.name].width_mm, calc.panels[panel.name].height_mm) == pytest.approx(
            geo.flat_size(contour), abs=1e-6
        )
        assert calc.panels[panel.name].area_m2 == pytest.approx(geo.polygon_area(contour) / 1e6, rel=1e-6)


def test_every_value_needs_a_source(case: HopperCase) -> None:
    data = case.model_dump()
    data["parameters"]["height_mm"] = {"value": 4200}
    with pytest.raises(ValidationError, match="source"):
        HopperCase.model_validate(data)


def test_tiers_must_add_up_to_the_height(case: HopperCase) -> None:
    data = case.model_dump()
    data["parameters"]["tier_heights_mm"]["value"] = [1200, 1500]
    with pytest.raises(ValidationError, match="tier heights add up to"):
        HopperCase.model_validate(data)


@pytest.mark.parametrize("vertical_height", [1200, 1800])  # 1800: end walls change slope inside tier 2
def test_beams_and_stiffeners_agree_with_the_independent_worker_placement(
    case: HopperCase, vertical_height: float
) -> None:
    data = case.model_dump()
    data["parameters"]["end_wall_vertical_height_mm"]["value"] = vertical_height
    case = HopperCase.model_validate(data)
    calc = calculate(case)
    job = build_job(case)
    spec = geo.HopperSpec.from_parameters(job["parameters"])
    stiffening = hp.Stiffening.from_job(job["stiffening"])
    panels = geo.panels(spec)
    placed: list[hp.Beam | hp.Stiffener | hp.Stub] = [
        *hp.tier_beams(spec, panels, stiffening),
        *hp.stiffeners(spec, panels, stiffening),
    ]
    stubs, boxes = hp.supports(spec, panels, stiffening)
    tubes, bracing_plates = hp.bracing(spec, stiffening)
    placed += [*hp.top_beams(spec, panels, stiffening), *stubs, *tubes]
    assert {p.name: (p.panel, p.section.name) for p in placed} == {
        n: (p.panel, p.profile) for n, p in calc.profiles.items()
    }
    for part in placed:
        assert part.length == pytest.approx(calc.profiles[part.name].length_mm, abs=1e-6), part.name
    for box in boxes:
        fitting = calc.fittings[box.name]
        assert (box.panel, box.size) == (fitting.panel, fitting.size_mm)
        assert box.centre == pytest.approx((*fitting.position_mm, fitting.z_mm[0]))
    slabs = [*hp.brackets(spec, panels, stiffening), *bracing_plates]
    assert {s.name for s in slabs} == {
        n for n, f in calc.fittings.items() if f.kind.endswith("plate") and n not in [b.name for b in boxes]
    }
    for slab in slabs:
        fitting = calc.fittings[slab.name]
        corners = [*slab.outline, *(tuple(a + b for a, b in zip(p, slab.extrude, strict=True)) for p in slab.outline)]
        low = [min(c[i] for c in corners) for i in range(3)]
        high = [max(c[i] for c in corners) for i in range(3)]
        assert slab.panel == fitting.panel, slab.name
        assert [h - lo for lo, h in zip(low, high, strict=True)] == pytest.approx(fitting.size_mm, abs=1e-6), slab.name
        assert ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2) == pytest.approx(fitting.position_mm, abs=1e-6)
        assert (low[2], high[2]) == pytest.approx(fitting.z_mm, abs=1e-6), slab.name
        assert hp.slab_volume(slab) == pytest.approx(fitting.volume_mm3, rel=1e-9), slab.name


def test_stiffening_must_use_profiles_of_the_right_kind(case: HopperCase) -> None:
    data = case.model_dump()
    data["stiffening"]["rules"]["standard_profile"] = "UPN200"
    with pytest.raises(ValidationError, match="'UPN200' must be a angle"):
        HopperCase.model_validate(data)
