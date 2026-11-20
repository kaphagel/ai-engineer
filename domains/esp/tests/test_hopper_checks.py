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
        "profiles": {
            n: {
                "kind": p.kind,
                "panel": p.panel,
                "profile": p.profile,
                "length_mm": p.length_mm,
                "position_mm": p.position_mm,
                "top_z_mm": p.top_z_mm,
            }
            for n, p in calc.profiles.items()
        },
        "fittings": {
            n: {
                "kind": f.kind,
                "panel": f.panel,
                "size_mm": f.size_mm,
                "position_mm": f.position_mm,
                "z_mm": f.z_mm,
                "volume_mm3": f.volume_mm3,
            }
            for n, f in calc.fittings.items()
        },
        "solids_valid": True,
        "interferences": [],
    }


def test_model_matching_the_calculation_passes(case: HopperCase) -> None:
    calc = calculate(case)
    results = checks._model_against_calculation(calc, measurements(calc))
    assert [r.id for r in results if r.failed] == []


def test_wrong_panel_size_in_the_model_fails(case: HopperCase) -> None:
    calc = calculate(case)
    m = measurements(calc)
    m["panels"]["SideLeft-T2"]["flat_size_mm"][1] += 1.0
    failed = [r.id for r in checks._model_against_calculation(calc, m) if r.failed]
    assert failed == ["model.panel_size.SideLeft-T2"]


def test_wrong_stiffener_length_or_missing_beam_fails(case: HopperCase) -> None:
    calc = calculate(case)
    m = measurements(calc)
    m["profiles"]["Stiff-SideLeft-T1-03"]["length_mm"] += 1.0
    del m["profiles"]["Beam-EndInlet-J2"]
    failed = [r.id for r in checks._model_against_calculation(calc, m) if r.failed]
    assert failed == ["model.profile_set", "model.stiffeners"]


def test_misplaced_support_stub_or_plate_fails(case: HopperCase) -> None:
    calc = calculate(case)
    m = measurements(calc)
    m["profiles"]["Stub-P1375_P2000"]["position_mm"] = (1376.0, 1975.0)
    m["fittings"]["BasePlate-M4125_M2000"]["z_mm"] = (3463.5, 3483.5)
    failed = [r.id for r in checks._model_against_calculation(calc, m) if r.failed]
    assert failed == ["model.stubs", "model.fittings"]


def test_unapproved_criterion_is_never_reported_as_a_plain_pass(case: HopperCase) -> None:
    result = checks._valley_criterion(case, calculate(case))
    assert result.status is CheckStatus.PASS_UNAPPROVED


def test_valley_angle_below_the_criterion_fails(case: HopperCase) -> None:
    data = case.model_dump()
    data["design_basis"]["min_valley_angle_deg"] = {"value": 70, "source": "test", "approved": True}
    strict = HopperCase.model_validate(data)
    assert checks._valley_criterion(strict, calculate(strict)).failed
