import pytest

from einstein_wtn.game_controller import GameController
from einstein_wtn.types import Player


def test_apply_text_move_advances_state():
    controller = GameController(red_agent=None, blue_agent=None)
    controller.set_dice(1)

    move_before = controller.state.turn
    controller.apply_text_move("R1,B2")

    assert controller.state.turn != move_before
    assert controller.history[-1][1].piece_id == 1


def test_apply_text_move_rejects_dice_mismatch():
    controller = GameController(red_agent=None, blue_agent=None)
    controller.set_dice(1)

    with pytest.raises(ValueError):
        controller.apply_text_move("12:2;(R1,B2)")
    assert controller.state.turn is Player.RED
