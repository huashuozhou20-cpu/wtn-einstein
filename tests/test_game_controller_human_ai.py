from einstein_wtn import engine
from einstein_wtn.agents import HeuristicAgent
from einstein_wtn.game_controller import GameController
from einstein_wtn.types import Move, Player
from einstein_wtn.wtn_format import parse_wtn


def test_controller_human_ai_flow():
    controller = GameController(
        red_agent=HeuristicAgent(seed=1), blue_agent=HeuristicAgent(seed=2)
    )

    controller.set_dice(1)
    legal = controller.legal_moves()
    assert legal

    first_move = legal[0]
    assert isinstance(first_move, Move)
    controller.apply_human_move(first_move)
    assert controller.state.turn is Player.BLUE

    controller.set_dice(2)
    legal_blue = engine.generate_legal_moves(controller.state, 2)
    ai_move = controller.step_ai(time_budget_ms=20)
    assert ai_move in legal_blue
    assert controller.state.turn is Player.RED

    wtn_text = controller.to_wtn()
    parsed = parse_wtn(wtn_text)
    assert parsed.moves


def test_to_wtn_roundtrip_parses():
    controller = GameController(
        red_agent=HeuristicAgent(seed=3), blue_agent=HeuristicAgent(seed=4)
    )
    controller.set_dice(1)
    move = controller.legal_moves()[0]
    controller.apply_human_move(move)
    controller.set_dice(2)
    controller.step_ai(time_budget_ms=10)

    text = controller.to_wtn()
    game = parse_wtn(text)
    assert game.red_layout and game.blue_layout
    assert len(game.moves) == 2
