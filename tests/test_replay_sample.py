from pathlib import Path

from einstein_wtn import engine
from einstein_wtn import replay
from einstein_wtn.types import Player


def test_replay_sample_file():
    path = Path(__file__).parent / "data" / "sample.wtn.txt"
    state, winner = replay.replay_file(str(path))

    assert winner == Player.RED
    assert engine.winner(state) == winner
