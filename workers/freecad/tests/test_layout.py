import pytest

from iaiep_worker import layout as lay

ISO = ((1.0, -1.0, 1.0), (1.0, 1.0, 0.0))


def layout_for(extents: tuple[float, float, float], side_panel: tuple[float, float]) -> lay.Layout:
    x, y, z = extents
    return lay.plan_layout((x, z), (x, y), (y, z), lay.projected_size(extents, *ISO), side_panel)


def test_large_hopper_gets_a_larger_sheet_rather_than_a_smaller_scale() -> None:
    layout = layout_for((11100.0, 4400.0, 4700.0), (162.0, 107.0))
    assert (layout.sheet, layout.scale_label) == ("A1", "1:50")


def test_views_fit_inside_the_frame_and_clear_of_the_title_block() -> None:
    layout = layout_for((6200.0, 4200.0, 4000.0), (162.0, 90.0))
    frame = lay.frame(layout.sheet)
    reserved = lay.title_block(layout.sheet)
    for p in layout.views.values():
        rect = lay.Rect.centred(p.x, p.y, p.width, p.height)
        assert rect.inside(frame)
        assert not rect.overlaps(reserved)


def test_too_large_for_any_sheet_is_an_error() -> None:
    with pytest.raises(ValueError, match="do not fit"):
        layout_for((400000.0, 4000.0, 4000.0), (162.0, 90.0))


def test_views_keep_the_room_their_dimensions_need() -> None:
    x, y, z = 8000.0, 3800.0, 4200.0
    views = ((x, z), (x, y), (y, z), lay.projected_size((x, y, z), *ISO))
    plain = lay.plan_layout(*views, side_panel=(180.0, 150.0))
    wide = lay.plan_layout(*views, side_panel=(180.0, 150.0), margins={"top": 18.0})
    assert (wide.sheet, wide.scale_denominator) == (plain.sheet, plain.scale_denominator)
    # The top view moves down by the extra margin (18 instead of 15 mm).
    assert wide.views["top"].y == pytest.approx(plain.views["top"].y - 3.0)
