import time

from einstein_wtn.opening import LayoutSearchAgent
from einstein_wtn.types import Player


def test_layoutsearch_returns_permutation():
    agent = LayoutSearchAgent(seed=1)
    layout = agent.choose_initial_layout(Player.RED, time_budget_ms=50)
    assert len(layout) == 6
    assert sorted(layout) == [1, 2, 3, 4, 5, 6]


def test_layoutsearch_deterministic_seed():
    agent1 = LayoutSearchAgent(seed=42)
    agent2 = LayoutSearchAgent(seed=42)
    layout1 = agent1.choose_initial_layout(Player.BLUE, time_budget_ms=50)
    layout2 = agent2.choose_initial_layout(Player.BLUE, time_budget_ms=50)
    assert layout1 == layout2


def test_layoutsearch_budget_respected():
    agent = LayoutSearchAgent(seed=7)
    start = time.monotonic()
    layout = agent.choose_initial_layout(Player.RED, time_budget_ms=5)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert len(layout) == 6
    assert elapsed_ms < 100
