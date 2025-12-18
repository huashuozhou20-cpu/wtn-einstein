from einstein_wtn import tournament
from einstein_wtn.agents import ExpectiminimaxAgent, HeuristicAgent
from einstein_wtn.types import Player


def test_tournament_smoke():
    red_agent = ExpectiminimaxAgent(max_depth=2, seed=1)
    blue_agent = HeuristicAgent(seed=2)
    result = tournament.run_tournament(
        red_agent=red_agent,
        blue_agent=blue_agent,
        games=4,
        seed=0,
        time_limit_seconds=60,
        quiet=True,
        collect_stats=True,
    )

    assert result.games == 4
    assert result.red_wins + result.blue_wins == 4
    assert result.avg_turns > 0
    assert Player.RED in result.avg_move_time_ms and Player.BLUE in result.avg_move_time_ms
    assert result.side_stats[Player.RED].samples >= 0
