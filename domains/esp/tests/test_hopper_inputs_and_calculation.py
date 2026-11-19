from pathlib import Path

import pytest
from pydantic import ValidationError

from iaiep_esp.hopper.calculation import calculate
from iaiep_esp.hopper.inputs import HopperCase
from iaiep_worker import hopper_geometry as geo

EXAMPLE = Path(__file__).parents[1] / "examples" / "hopper_synthetic.toml"


@pytest.fixture
def case() -> HopperCase:
    return HopperCase.load(EXAMPLE)


def test_calculation_agrees_with_the_independent_worker_geometry(case: HopperCase) -> None:
    calc = calculate(case.parameters)
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
