from einstein_wtn.agents import HeuristicAgent
from einstein_wtn.game_controller import GameController


def test_legal_destinations_filter_by_piece_id():
    controller = GameController(
        red_agent=HeuristicAgent(seed=0), blue_agent=HeuristicAgent(seed=1)
    )
    controller.set_dice(1)
    moves = controller.legal_moves()
    assert moves

    piece_id = moves[0].piece_id
    destinations = controller.legal_destinations_for_piece(piece_id)
    assert destinations
    assert all(
        mv.to_rc in destinations for mv in moves if mv.piece_id == piece_id
    )

    missing_piece = next(pid for pid in range(1, 7) if pid not in {mv.piece_id for mv in moves})
    assert controller.legal_destinations_for_piece(missing_piece) == set()
