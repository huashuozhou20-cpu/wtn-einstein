from einstein_wtn.types import GameState, Move, Player
from einstein_wtn import engine


def build_state(red_map, blue_map, turn=Player.RED) -> GameState:
    board = [[0 for _ in range(engine.BOARD_SIZE)] for _ in range(engine.BOARD_SIZE)]
    pos_red = {i: None for i in range(1, 7)}
    pos_blue = {i: None for i in range(1, 7)}
    alive_red = 0
    alive_blue = 0

    for pid, coord in red_map.items():
        pos_red[pid] = coord
        alive_red |= 1 << (pid - 1)
        r, c = coord
        board[r][c] = pid

    for pid, coord in blue_map.items():
        pos_blue[pid] = coord
        alive_blue |= 1 << (pid - 1)
        r, c = coord
        board[r][c] = -pid

    return GameState(
        board=board,
        pos_red=pos_red,
        pos_blue=pos_blue,
        alive_red=alive_red,
        alive_blue=alive_blue,
        turn=turn,
    )


def test_capture_opponent_piece():
    state = build_state(red_map={1: (1, 1)}, blue_map={2: (2, 2)}, turn=Player.RED)
    move = Move(piece_id=1, from_rc=(1, 1), to_rc=(2, 2))

    new_state = engine.apply_move(state, move)

    assert new_state.board[2][2] == 1
    assert new_state.pos_blue[2] is None
    assert new_state.alive_blue & (1 << 1) == 0


def test_capture_friendly_piece():
    state = build_state(red_map={1: (1, 1), 2: (2, 2)}, blue_map={3: (4, 4)}, turn=Player.RED)
    move = Move(piece_id=1, from_rc=(1, 1), to_rc=(2, 2))

    new_state = engine.apply_move(state, move)

    assert new_state.board[2][2] == 1
    assert new_state.pos_red[2] is None
    assert new_state.alive_red & (1 << 1) == 0
