from einstein_wtn import engine
from einstein_wtn.time_manager import compute_move_budget_ms, preset_time_manager
from einstein_wtn.types import Player


def make_state():
    return engine.new_game(list(engine.START_RED_CELLS), list(engine.START_BLUE_CELLS), first=Player.RED)


def test_presets_ordering():
    fast = preset_time_manager("fast")
    default = preset_time_manager("default")
    slow = preset_time_manager("slow")

    assert fast.max_ms < default.max_ms < slow.max_ms
    assert slow.safe_cap_frac >= default.safe_cap_frac > fast.safe_cap_frac


def test_presets_affect_budget():
    state = make_state()
    dice = 3

    budget_fast_long = compute_move_budget_ms(
        state, dice=dice, remaining_ms=240_000, agent_name="expecti", cfg=preset_time_manager("fast")
    )
    budget_slow_long = compute_move_budget_ms(
        state, dice=dice, remaining_ms=240_000, agent_name="expecti", cfg=preset_time_manager("slow")
    )
    assert budget_slow_long > budget_fast_long

    budget_fast_short = compute_move_budget_ms(
        state, dice=dice, remaining_ms=10_000, agent_name="expecti", cfg=preset_time_manager("fast")
    )
    budget_slow_short = compute_move_budget_ms(
        state, dice=dice, remaining_ms=10_000, agent_name="expecti", cfg=preset_time_manager("slow")
    )
    assert budget_slow_short > budget_fast_short

