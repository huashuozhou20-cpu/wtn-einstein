import time

from einstein_wtn import engine
from einstein_wtn.time_manager import TimeManagerConfig, compute_move_budget_ms
from einstein_wtn.types import GameState, Player


def make_state(red_pos, blue_pos, turn: Player) -> GameState:
    board = [[0 for _ in range(engine.BOARD_SIZE)] for _ in range(engine.BOARD_SIZE)]
    pos_red = {i: None for i in range(1, 7)}
    pos_blue = {i: None for i in range(1, 7)}
    alive_red = 0
    alive_blue = 0
    for pid, coord in red_pos.items():
        pos_red[pid] = coord
        if coord is not None:
            alive_red |= 1 << (pid - 1)
            r, c = coord
            board[r][c] = pid
    for pid, coord in blue_pos.items():
        pos_blue[pid] = coord
        if coord is not None:
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


def test_budget_increases_on_immediate_win():
    cfg = TimeManagerConfig()
    remaining_ms = 10_000
    baseline_state = make_state({1: (0, 0)}, {1: (4, 4)}, Player.RED)
    base_budget = compute_move_budget_ms(baseline_state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)

    winning_state = make_state({1: (3, 3)}, {1: (4, 4)}, Player.RED)
    win_budget = compute_move_budget_ms(winning_state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)

    assert win_budget > base_budget


def test_budget_respects_bounds():
    cfg = TimeManagerConfig(max_ms=300)
    state = make_state({1: (0, 0)}, {1: (4, 4)}, Player.RED)

    large_budget = compute_move_budget_ms(state, dice=1, remaining_ms=100_000, agent_name="expecti", cfg=cfg)
    assert cfg.min_ms <= large_budget <= cfg.max_ms

    tiny_budget = compute_move_budget_ms(state, dice=1, remaining_ms=5, agent_name="expecti", cfg=cfg)
    assert 0 < tiny_budget <= 5


def test_budget_endgame_multiplier():
    cfg = TimeManagerConfig()
    # Midgame with more material than the endgame threshold.
    state = make_state({1: (1, 1), 2: (0, 0), 3: (0, 1)}, {1: (3, 3), 2: (4, 4)}, Player.BLUE)
    normal = compute_move_budget_ms(state, dice=1, remaining_ms=8_000, agent_name="expecti", cfg=cfg)

    # Two pieces total triggers the endgame multiplier.
    state_endgame = make_state({1: (1, 1)}, {}, Player.BLUE)
    endgame_budget = compute_move_budget_ms(state_endgame, dice=1, remaining_ms=8_000, agent_name="expecti", cfg=cfg)

    assert endgame_budget > normal
