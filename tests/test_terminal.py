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


def test_red_reaches_goal():
    state = build_state(red_map={1: engine.TARGET_RED}, blue_map={2: (3, 3)}, turn=Player.BLUE)
    assert engine.winner(state) == Player.RED
    assert engine.is_terminal(state)


def test_blue_reaches_goal():
    state = build_state(red_map={1: (4, 3)}, blue_map={1: engine.TARGET_BLUE}, turn=Player.RED)
    assert engine.winner(state) == Player.BLUE
    assert engine.is_terminal(state)


def test_elimination_win():
    state = build_state(red_map={1: (1, 1)}, blue_map={}, turn=Player.RED)
    # Blue has no alive pieces.
    assert engine.winner(state) == Player.RED
