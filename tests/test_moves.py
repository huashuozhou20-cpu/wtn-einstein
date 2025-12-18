from einstein_wtn import engine
from einstein_wtn.types import Player


def test_moves_stay_inside_board():
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=Player.RED)

    # Place red piece 1 at the top-right corner to block moves going out of bounds.
    original = state.pos_red[1]
    state.board[original[0]][original[1]] = 0
    state.pos_red[1] = (0, 4)
    state.board[0][4] = 1

    moves = engine.generate_legal_moves(state, dice=1)
    assert all(0 <= mv.to_rc[0] < engine.BOARD_SIZE and 0 <= mv.to_rc[1] < engine.BOARD_SIZE for mv in moves)
    assert any(mv.to_rc == (1, 4) for mv in moves)
    assert all(mv.to_rc != (0, 5) for mv in moves)
