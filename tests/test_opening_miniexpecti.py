import time

from einstein_wtn.opening import LayoutSearchAgent
from einstein_wtn.types import Player


def test_miniexpecti_budget_and_perm():
    agent = LayoutSearchAgent(seed=10, layout_eval_mode="mini-expecti")
    start = time.monotonic()
    layout = agent.choose_initial_layout(Player.RED, time_budget_ms=30)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert sorted(layout) == [1, 2, 3, 4, 5, 6]
    assert elapsed_ms < 200


def test_miniexpecti_deterministic_seed():
    agent1 = LayoutSearchAgent(seed=11, layout_eval_mode="mini-expecti")
    agent2 = LayoutSearchAgent(seed=11, layout_eval_mode="mini-expecti")
    layout1 = agent1.choose_initial_layout(Player.BLUE, time_budget_ms=60)
    layout2 = agent2.choose_initial_layout(Player.BLUE, time_budget_ms=60)
    assert layout1 == layout2
