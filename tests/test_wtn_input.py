import pytest

from einstein_wtn.wtn_input import parse_move_text


def test_parse_full_wtn_line():
    parsed = parse_move_text("12:5;(B3,D2)")
    assert parsed.color == "B"
    assert parsed.piece_id == 3
    assert parsed.dice == 5
    assert (parsed.to_r, parsed.to_c) == (1, 3)


def test_parse_short_forms():
    samples = [
        "(R5,C3)",
        "R5 C3",
        "B3,D2",
    ]
    for sample in samples:
        parsed = parse_move_text(sample)
        assert parsed.piece_id in {3, 5}
        assert parsed.dice is None


def test_parse_invalid_inputs():
    for sample in ["", "Z5,D2", "R9,C3", "5;(R1,Z9)"]:
        with pytest.raises(ValueError):
            parse_move_text(sample)
