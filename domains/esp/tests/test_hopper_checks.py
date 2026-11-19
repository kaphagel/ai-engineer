from pathlib import Path
from typing import Any

import pytest

from iaiep.checks import CheckStatus
from iaiep_esp.hopper import checks
from iaiep_esp.hopper.calculation import HopperCalculation, calculate
from iaiep_esp.hopper.inputs import HopperCase

EXAMPLE = Path(__file__).parents[1] / "examples" / "hopper_synthetic.toml"


@pytest.fixture
def case() -> HopperCase:
    return HopperCase.load(EXAMPLE)


def measurements(calc: HopperCalculation) -> dict[str, Any]:
    """Model measurements as the worker reports them, equal to the calculation."""
    return {
        "panels": {n: {"flat_size_mm": [p.width_mm, p.height_mm]} for n, p in calc.panels.items()},
        "side_wall_slope_deg": calc.side_wall_slope_deg,
        "end_wall_slope_deg": calc.end_wall_slope_deg,
        "valley_angle_deg": calc.valley_angle_deg,
        "capacity_m3": calc.capacity_m3,
        "solids_valid": True,
        "interferences": [],
    }


def test_model_matching_the_calculation_passes(case: HopperCase) -> None:
    calc = calculate(case.parameters)
    results = checks._model_against_calculation(calc, measurements(calc))
    assert [r.id for r in results if r.failed] == []


def test_wrong_panel_size_in_the_model_fails(case: HopperCase) -> None:
    calc = calculate(case.parameters)
    m = measurements(calc)
    m["panels"]["SideLeft-T2"]["flat_size_mm"][1] += 1.0
    failed = [r.id for r in checks._model_against_calculation(calc, m) if r.failed]
    assert failed == ["model.panel_size.SideLeft-T2"]


def test_unapproved_criterion_is_never_reported_as_a_plain_pass(case: HopperCase) -> None:
    result = checks._valley_criterion(case, calculate(case.parameters))
    assert result.status is CheckStatus.PASS_UNAPPROVED


def test_valley_angle_below_the_criterion_fails(case: HopperCase) -> None:
    data = case.model_dump()
    data["design_basis"]["min_valley_angle_deg"] = {"value": 70, "source": "test", "approved": True}
    strict = HopperCase.model_validate(data)
    assert checks._valley_criterion(strict, calculate(strict.parameters)).failed
