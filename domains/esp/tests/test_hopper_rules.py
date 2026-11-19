from pathlib import Path
from typing import Any

import pytest

from iaiep_esp.hopper.calculation import calculate
from iaiep_esp.hopper.inputs import HopperCase
from iaiep_esp.hopper.rules import RULE_SOURCE_PREFIX, resolve, stiffener_positions

EXAMPLE = Path(__file__).parents[1] / "examples" / "hopper_synthetic.toml"


@pytest.fixture
def data() -> dict[str, Any]:
    return HopperCase.load(EXAMPLE).model_dump()


def case_with(data: dict[str, Any], **parameters: object) -> HopperCase:
    for key, value in parameters.items():
        data["parameters"][key]["value"] = value
    return HopperCase.model_validate(data)


def test_heavy_stiffeners_on_the_column_lines_and_even_bays_between() -> None:
    positions = stiffener_positions(4000, [-1500, 1500], 1000)
    assert [x for x, on_column in positions if on_column] == [-1500, 1500]
    xs = [x for x, _ in positions]
    assert xs == pytest.approx([-3166.667, -2333.333, -1500, -500, 500, 1500, 2333.333, 3166.667], abs=1e-3)
    gaps = [b - a for a, b in zip([-4000, *xs], [*xs, 4000], strict=True)]
    assert max(gaps) <= 1000


@pytest.mark.parametrize(
    "parameters",
    [
        {"top_length_outside_mm": 6000, "slot_length_inside_mm": 4500},
        {"top_length_outside_mm": 3800, "slot_length_inside_mm": 400, "end_wall_vertical_height_mm": 0},
        {"top_width_outside_mm": 4800},
        {"tier_heights_mm": [2000, 2200]},
        {"tier_heights_mm": [1200, 1000, 1000, 1000]},
    ],
    ids=["shorter", "pyramidal", "wider", "two_tiers", "four_tiers"],
)
def test_the_rules_adapt_the_layout_to_a_change_of_size(data: dict[str, Any], parameters: dict[str, object]) -> None:
    case = case_with(data, **parameters)
    calc = calculate(case)  # raises if a stiffener does not fit its panel
    resolved = resolve(case)
    assert resolved.stiffening is not None and resolved.stiffening.supports is not None
    grid_y = resolved.stiffening.supports.grid_y_mm
    assert grid_y is not None and grid_y[1] == pytest.approx(case.parameters.top_width_outside_mm.value / 2 + 100)
    tiers = len(case.parameters.tier_heights_mm.value)
    assert {p.panel.split("-")[1] for p in calc.profiles.values() if p.kind == "stiffener"} == {
        f"T{k}" for k in range(1, tiers + 1)
    }


def test_an_explicit_layout_overrides_the_rule_for_its_wall_and_tier(data: dict[str, Any]) -> None:
    explicit = {
        "wall": "side",
        "tier": 2,
        "bays_mm": [2000],
        "profiles": ["L75x50x6", "L75x50x6"],
        "bottom_clearance_mm": 0,
        "top_extension_mm": 10,
        "source": "drawing",
    }
    data["stiffening"]["stiffeners"] = [explicit]
    layouts = resolve(HopperCase.model_validate(data)).stiffening.stiffeners  # type: ignore[union-attr]
    side_2 = [s for s in layouts if (s.wall, s.tier) == ("side", 2)]
    assert len(side_2) == 1 and side_2[0].source == "drawing"
    assert all(s.source.startswith(RULE_SOURCE_PREFIX) for s in layouts if s is not side_2[0])
    assert resolve(resolve(HopperCase.model_validate(data))) == resolve(HopperCase.model_validate(data))


def test_rules_need_a_symmetric_support_grid(data: dict[str, Any]) -> None:
    supports = data["stiffening"]["supports"]
    supports.update(column_bays=None, corner_offset_x_mm=None, side_offset_y_mm=None)
    supports.update(grid_x_mm=[-4125, -1000, 1375, 4125], grid_y_mm=[-2000, 2000])
    with pytest.raises(ValueError, match="symmetric"):
        calculate(HopperCase.model_validate(data))
