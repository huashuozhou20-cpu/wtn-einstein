from einstein_wtn import engine
from einstein_wtn.agents import OpeningExpectiAgent
from einstein_wtn.types import Player


def test_opening_expecti_layout_is_permutation():
    agent = OpeningExpectiAgent(seed=1, layout_budget_ms=50)
    layout = agent.choose_initial_layout(Player.RED, time_budget_ms=50)
    assert len(layout) == 6
    assert sorted(layout) == [1, 2, 3, 4, 5, 6]


def test_opening_expecti_move_is_legal():
    agent = OpeningExpectiAgent(seed=2)
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=Player.RED)
    moves = engine.generate_legal_moves(state, dice=1)
    move = agent.choose_move(state, dice=1, time_budget_ms=200)
    assert move in moves


def test_opening_expecti_deterministic_seed():
    agent1 = OpeningExpectiAgent(seed=3, layout_budget_ms=30)
    agent2 = OpeningExpectiAgent(seed=3, layout_budget_ms=30)
    layout1 = agent1.choose_initial_layout(Player.BLUE, time_budget_ms=30)
    layout2 = agent2.choose_initial_layout(Player.BLUE, time_budget_ms=30)
    assert layout1 == layout2
