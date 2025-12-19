import textwrap

from einstein_wtn.wtn_format import dump_wtn, parse_wtn, rc_to_sq, sq_to_rc


def test_coord_roundtrip():
    for rc in [(0, 0), (4, 4), (2, 2), (0, 2), (3, 1)]:
        sq = rc_to_sq(*rc)
        assert sq_to_rc(sq) == rc


def test_parse_and_dump_roundtrip():
    raw = textwrap.dedent(
        """
        # Friendly match
        R:A1-1;B1-2;C1-3;A2-4;B2-5;A3-6
        B:E5-1;D5-2;C5-3;E4-4;D4-5;E3-6
        1:6;(R6,B4)
        2:1;(B1,D4)
        """
    ).strip()

    game = parse_wtn(raw)
    dumped = dump_wtn(game)
    reparsed = parse_wtn(dumped)

    assert reparsed.comments == game.comments
    assert reparsed.red_layout == game.red_layout
    assert reparsed.blue_layout == game.blue_layout
    assert reparsed.moves == game.moves
