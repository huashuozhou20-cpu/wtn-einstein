import pytest

from einstein_wtn import engine, runner
from einstein_wtn.agents import ExpectiminimaxAgent, HeuristicAgent, RandomAgent
from einstein_wtn.types import GameState, Player


def assert_permutation(order):
    assert len(order) == 6
    assert sorted(order) == [1, 2, 3, 4, 5, 6]


def test_initial_layout_permutations():
    rand = RandomAgent(seed=5)
    heur = HeuristicAgent(seed=5)
    expecti = ExpectiminimaxAgent(seed=5)

    for agent in (rand, heur, expecti):
        assert_permutation(agent.choose_initial_layout(Player.RED, time_budget_ms=50))
        assert_permutation(agent.choose_initial_layout(Player.BLUE, time_budget_ms=50))


def _build_state(red_map, blue_map, turn=Player.RED) -> GameState:
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


def test_expectiminimax_immediate_win():
    state = _build_state(red_map={1: (3, 3)}, blue_map={2: (0, 4)}, turn=Player.RED)
    agent = ExpectiminimaxAgent(max_depth=2, seed=7)
    move = agent.choose_move(state, dice=1, time_budget_ms=200)
    assert move.to_rc == engine.TARGET_RED


def test_runner_layout_parse():
    order = runner.parse_layout_string("6,5,4,3,2,1")
    assert order == [6, 5, 4, 3, 2, 1]

    layout = runner.arrangement_to_layout(order, engine.START_RED_CELLS)
    state = engine.new_game(layout, engine.START_BLUE_CELLS, first=Player.RED)
    assert state.pos_red[6] == engine.START_RED_CELLS[0]
    assert state.pos_red[1] == engine.START_RED_CELLS[5]

    with pytest.raises(ValueError):
        runner.parse_layout_string("1,1,2,3,4,5")
