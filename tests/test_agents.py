from einstein_wtn.agents import RandomAgent
from einstein_wtn import engine
from einstein_wtn.types import Player


def test_random_agent_seed_reproducible():
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=Player.RED)
    agent1 = RandomAgent(seed=123)
    agent2 = RandomAgent(seed=123)

    move1 = agent1.choose_move(state, dice=1)
    move2 = agent2.choose_move(state, dice=1)

    assert move1 == move2
