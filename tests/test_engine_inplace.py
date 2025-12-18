from copy import deepcopy

from einstein_wtn import engine
from einstein_wtn.types import Player


def test_inplace_apply_undo_roundtrip():
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=Player.RED)
    original_key = state.key()
    original_board = deepcopy(state.board)
    original_pos_red = deepcopy(state.pos_red)
    original_pos_blue = deepcopy(state.pos_blue)
    original_alive_red = state.alive_red
    original_alive_blue = state.alive_blue
    original_turn = state.turn

    move = engine.generate_legal_moves(state, dice=1)[0]
    undo = engine.apply_move_inplace(state, move)
    # State should have changed.
    assert state.turn == Player.BLUE
    assert state.key() != original_key

    engine.undo_move_inplace(state, undo)

    assert state.turn == original_turn
    assert state.board == original_board
    assert state.pos_red == original_pos_red
    assert state.pos_blue == original_pos_blue
    assert state.alive_red == original_alive_red
    assert state.alive_blue == original_alive_blue
    assert state.key() == original_key
