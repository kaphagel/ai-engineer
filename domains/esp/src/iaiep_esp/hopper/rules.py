"""Engineering rules resolved into an explicit stiffening layout (spec §30.2, E-02; ADR-0004).

The CAD worker and the independent calculation only know explicit values (bays, grid lines, beam
extensions). This module turns the rules of an input set into such values for every wall and tier that
has no explicit entry, so that the hopper adapts to a change of size. Explicit entries always win.
Generated stiffener layouts carry a source starting with "rule:"; the checks report them as not
approved until the engineering owner approves the rules.
"""

import itertools
import math

from iaiep_esp.hopper.inputs import HopperCase, SpacingRule, StiffenerLayout, Stiffening, StiffeningRules, Supports

RULE_SOURCE_PREFIX = "rule:"
SYMMETRY_TOL_MM = 0.5


def resolve(case: HopperCase) -> HopperCase:
    """The same input set with explicit values only. Idempotent."""
    st = case.stiffening
    if st is None:
        return case
    joints = len(case.parameters.tier_heights_mm.value) - 1
    supports = _grid(case, st.supports) if st.supports is not None else None
    inner_columns = list(supports.grid_x_mm[1:-1]) if supports is not None and supports.grid_x_mm else []

    tier_beams = st.tier_beams
    if tier_beams is not None:
        tier_beams = tier_beams.model_copy(
            update={
                "side_end_extensions_mm": tier_beams.extensions("side", joints),
                "end_end_extensions_mm": tier_beams.extensions("end", joints),
                "side_end_extension_mm": None,
                "end_end_extension_mm": None,
            }
        )
    top_beams = st.top_beams
    if top_beams is not None and top_beams.split_at_columns:
        top_beams = top_beams.model_copy(update={"side_splits_mm": inner_columns, "split_at_columns": False})

    stiffeners = list(st.stiffeners)
    if st.rules is not None:
        stiffeners += _rule_layouts(case, st.rules, st.stiffeners, inner_columns)
    resolved = Stiffening(
        tier_beams=tier_beams, top_beams=top_beams, supports=supports, stiffeners=stiffeners, rules=st.rules
    )
    return case.model_copy(update={"stiffening": resolved})


def tier_position(tier: int, tiers: int) -> str:
    if tier == 1:
        return "bottom"
    return "top" if tier == tiers else "middle"


def stiffener_positions(half_length: float, columns: list[float], max_spacing: float) -> list[tuple[float, bool]]:
    """Positions along a panel top edge (from its centreline) and whether each is on a column line.

    Each stretch between the panel ends and the column lines is divided into the fewest equal bays not
    longer than `max_spacing`; a stiffener stands at every bay end except the panel ends.
    """
    inside = sorted(c for c in columns if abs(c) < half_length - SYMMETRY_TOL_MM)
    bounds = [-half_length, *inside, half_length]
    result = [(c, True) for c in inside]
    for a, b in itertools.pairwise(bounds):
        bays = max(1, math.ceil((b - a) / max_spacing - 1e-9))
        result += [(a + (b - a) * k / bays, False) for k in range(1, bays)]
    return sorted(result)


def _grid(case: HopperCase, sup: Supports) -> Supports:
    if sup.grid_x_mm is not None and sup.grid_y_mm is not None:
        return sup
    assert sup.column_bays is not None and sup.corner_offset_x_mm is not None and sup.side_offset_y_mm is not None
    x = case.parameters.top_length_outside_mm.value / 2 + sup.corner_offset_x_mm
    y = case.parameters.top_width_outside_mm.value / 2 + sup.side_offset_y_mm
    grid_x = [-x + 2 * x * k / sup.column_bays for k in range(sup.column_bays + 1)]
    return sup.model_copy(
        update={
            "grid_x_mm": [round(v, 3) for v in grid_x],
            "grid_y_mm": [-y, y],
            "column_bays": None,
            "corner_offset_x_mm": None,
            "side_offset_y_mm": None,
        }
    )


def _rule_layouts(
    case: HopperCase, rules: StiffeningRules, explicit: list[StiffenerLayout], inner_columns: list[float]
) -> list[StiffenerLayout]:
    from iaiep_esp.hopper.calculation import calculate  # the panel sizes; no cycle: no stiffening

    panels = calculate(case.model_copy(update={"stiffening": None})).panels
    tiers = len(case.parameters.tier_heights_mm.value)
    given = {(layout.wall, layout.tier) for layout in explicit}
    by_key: dict[tuple[str, str], SpacingRule] = {(r.wall, r.position): r for r in rules.spacing}
    status = "approved" if rules.approved else "NOT APPROVED"
    layouts = []
    for tier in range(1, tiers + 1):
        for wall, prefix in (("side", "SideLeft"), ("end", "EndOutlet")):
            rule = by_key.get((wall, tier_position(tier, tiers)))
            if rule is None or (wall, tier) in given:
                continue
            # The narrowest piece of the wall in this tier (end walls may bend inside a tier).
            half = min(size.width_mm for name, size in panels.items() if name.startswith(f"{prefix}-T{tier}")) / 2
            layout = _layout(rule, tier, half, inner_columns if wall == "side" else [], rules, status)
            if layout is not None:
                layouts.append(layout)
    return layouts


def _layout(
    rule: SpacingRule, tier: int, half: float, columns: list[float], rules: StiffeningRules, status: str
) -> StiffenerLayout | None:
    positions = stiffener_positions(half, columns, rule.max_spacing_mm)
    if not positions:
        return None
    xs = [x for x, _ in positions]
    if any(abs(a + b) > SYMMETRY_TOL_MM for a, b in zip(xs, reversed(xs), strict=True)):
        raise ValueError(
            f"{rule.wall} wall tier {tier}: the rules need support column lines symmetric about the centre"
        )
    profiles = [
        rules.column_profile if on_column and rules.column_profile else rules.standard_profile
        for _, on_column in positions
    ]
    return StiffenerLayout(
        wall=rule.wall,
        tier=tier,
        bays_mm=[round(b - a, 3) for a, b in itertools.pairwise(xs)],
        profiles=profiles,
        bottom_clearance_mm=rule.bottom_clearance_mm,
        top_extension_mm=rule.top_extension_mm,
        source=f"{RULE_SOURCE_PREFIX} {rule.wall} wall, {rule.position} tiers, max spacing "
        f"{rule.max_spacing_mm:g} mm ({rules.source}; {status})",
    )
