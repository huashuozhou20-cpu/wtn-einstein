import pytest

from einstein_wtn import engine
from einstein_wtn.types import Player


def test_candidates_with_missing_ids():
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=Player.RED)

    # Remove red pieces 4 and 5 to mimic captures.
    for pid in (4, 5):
        r, c = state.pos_red[pid]
        state.board[r][c] = 0
        state.pos_red[pid] = None
        state.alive_red &= ~(1 << (pid - 1))

    candidates = engine.get_movable_piece_ids(state, Player.RED, dice=4)
    assert set(candidates) == {3, 6}
