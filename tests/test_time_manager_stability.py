from einstein_wtn import engine
from einstein_wtn.time_manager import TimeManagerConfig, compute_move_budget_ms
from einstein_wtn.types import Player
from tests.test_time_manager import make_state


def test_budget_stable_on_large_clock():
    cfg = TimeManagerConfig()
    layout_red = list(engine.START_RED_CELLS)
    layout_blue = list(engine.START_BLUE_CELLS)
    state = engine.new_game(layout_red, layout_blue, first=Player.RED)
    remaining_ms = 10_000
    budget = compute_move_budget_ms(state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)
    safe_cap = getattr(compute_move_budget_ms, "last_safe_cap", None)

    assert budget < 600
    assert safe_cap is not None
    assert budget <= safe_cap <= cfg.max_ms
    assert budget <= remaining_ms


def test_budget_raises_for_endgame_and_threat():
    cfg = TimeManagerConfig()
    remaining_ms = 10_000
    baseline_state = engine.new_game(list(engine.START_RED_CELLS), list(engine.START_BLUE_CELLS), first=Player.RED)
    baseline = compute_move_budget_ms(baseline_state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)

    # Endgame with two pieces left should increase allocation.
    endgame_state = make_state({1: (2, 2)}, {}, Player.RED)
    end_budget = compute_move_budget_ms(endgame_state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)
    assert end_budget > baseline

    # Immediate win threat also bumps the budget.
    win_state = make_state({1: (3, 3)}, {1: (4, 4)}, Player.RED)
    win_budget = compute_move_budget_ms(win_state, dice=1, remaining_ms=remaining_ms, agent_name="expecti", cfg=cfg)
    assert win_budget > baseline

