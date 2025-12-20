import pytest

from einstein_wtn import engine
from einstein_wtn.wtn_layout import parse_layout_line


def test_parse_red_layout_line():
    color, mapping = parse_layout_line("R:A1-1;B1-2;C1-3;A2-4;B2-5;A3-6")
    assert color == "R"
    assert mapping[1] == (0, 0)
    assert set(mapping.values()) == set(engine.START_RED_CELLS)


def test_parse_blue_layout_line():
    color, mapping = parse_layout_line("B:E5-1;D5-2;C5-3;E4-4;D4-5;E3-6")
    assert color == "B"
    assert mapping[6] == (2, 4)
    assert set(mapping.values()) == set(engine.START_BLUE_CELLS)


def test_parse_invalid_coordinate_raises():
    with pytest.raises(ValueError):
        parse_layout_line("R:Z1-1;B1-2;C1-3;A2-4;B2-5;A3-6")


def test_parse_invalid_piece_id():
    with pytest.raises(ValueError):
        parse_layout_line("R:A1-7;B1-2;C1-3;A2-4;B2-5;A3-6")


def test_parse_duplicate_cell():
    with pytest.raises(ValueError):
        parse_layout_line("R:A1-1;A1-2;C1-3;A2-4;B2-5;A3-6")


def test_parse_out_of_start_zone():
    with pytest.raises(ValueError):
        parse_layout_line("R:D1-1;B1-2;C1-3;A2-4;B2-5;A3-6")
