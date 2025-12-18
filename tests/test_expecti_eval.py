from einstein_wtn import engine
from einstein_wtn.agents import ExpectiminimaxAgent
from einstein_wtn.types import GameState, Player


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


def test_expecti_evaluation_perspective():
    state = build_state(red_map={1: (3, 3), 2: (2, 2)}, blue_map={1: (0, 4)}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=1)

    red_score = agent._evaluate(state, Player.RED)
    blue_score = agent._evaluate(state, Player.BLUE)

    assert red_score > 0
    assert blue_score < 0


def test_expecti_blue_picks_immediate_win():
    state = build_state(red_map={1: (4, 4)}, blue_map={1: (1, 0)}, turn=Player.BLUE)
    agent = ExpectiminimaxAgent(max_depth=2, seed=2)

    move = agent.choose_move(state, dice=1, time_budget_ms=200)
    assert move.to_rc == engine.TARGET_BLUE
