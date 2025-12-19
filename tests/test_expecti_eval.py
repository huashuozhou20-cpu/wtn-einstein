from einstein_wtn import engine
from einstein_wtn.agents import ExpectiminimaxAgent
from einstein_wtn.types import GameState, Move, Player


def build_state(red_map, blue_map, turn=Player.RED) -> GameState:
    board = [[0 for _ in range(engine.BOARD_SIZE)] for _ in range(engine.BOARD_SIZE)]
    pos_red = {i: None for i in range(1, 7)}
    pos_blue = {i: None for i in range(1, 7)}
    alive_red = 0
    alive_blue = 0

    for pid, coord in red_map.items():
        pos_red[pid] = coord
        alive_red |= 1 << (pid - 1)
        r, c = coord
        board[r][c] = pid

    for pid, coord in blue_map.items():
        pos_blue[pid] = coord
        alive_blue |= 1 << (pid - 1)
        r, c = coord
        board[r][c] = -pid

    return GameState(
        board=board,
        pos_red=pos_red,
        pos_blue=pos_blue,
        alive_red=alive_red,
        alive_blue=alive_blue,
        turn=turn,
    )


def test_expecti_evaluation_perspective():
    state = build_state(red_map={1: (3, 3), 2: (2, 2)}, blue_map={1: (0, 4)}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=1)

    red_score = agent._evaluate(state, Player.RED)
    blue_score = agent._evaluate(state, Player.BLUE)

    assert red_score > 0
    assert blue_score < 0


def test_expecti_blue_picks_immediate_win():
    state = build_state(red_map={1: (4, 4)}, blue_map={1: (1, 0)}, turn=Player.BLUE)
    agent = ExpectiminimaxAgent(max_depth=2, seed=2)

    move = agent.choose_move(state, dice=1, time_budget_ms=200)
    assert move.to_rc == engine.TARGET_BLUE

def test_ordering_prioritizes_immediate_win():
    state = build_state(red_map={1: (3, 3)}, blue_map={2: (0, 0)}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=3)
    moves = engine.generate_legal_moves(state, dice=1)
    ordered = agent._order_moves(state, moves)
    assert ordered, "Expected moves to order"
    first_move = ordered[0]
    assert engine.winner(engine.apply_move(state, first_move)) == Player.RED


def test_killer_moves_prioritized():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=4)
    moves = engine.generate_legal_moves(state, dice=1)
    killer_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(1, 1))
    agent.killer_moves[1] = [agent._move_signature(killer_move)]

    ordered = agent._order_moves(state, moves, ply=1)
    assert ordered[0] == killer_move


def test_history_influences_order():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=5)
    moves = engine.generate_legal_moves(state, dice=1)
    target_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(0, 1))
    other_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(1, 0))
    agent.history[(Player.RED.value, agent._move_signature(target_move))] = 25
    agent.history[(Player.RED.value, agent._move_signature(other_move))] = 1

    ordered = agent._order_moves(state, moves, ply=1)
    assert ordered[0] == target_move


def test_killer_history_persist_across_moves():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=6)
    moves = engine.generate_legal_moves(state, dice=1)
    favored_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(0, 1))
    other_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(1, 0))

    # First search (or manual credit) seeds history that should persist with decay.
    agent.choose_move(state, dice=1, time_budget_ms=20)
    agent._record_history(Player.RED, favored_move, depth=3)

    # Second move selection should still leverage the decayed history scores.
    agent.choose_move(state, dice=1, time_budget_ms=20)
    ordered = agent._order_moves(state, moves, ply=1)

    assert ordered[0] == favored_move


def test_tt_key_includes_dice_for_decision():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=7)

    key_one = agent._tt_key_decision(state, dice=1, depth=2, maximizing_player=Player.RED)
    key_two = agent._tt_key_decision(state, dice=2, depth=2, maximizing_player=Player.RED)

    assert key_one != key_two
    assert key_one[-1] == 1
    assert key_two[-1] == 2


def test_tt_key_distinguishes_node_type():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=8)

    decision_key = agent._tt_key_decision(state, dice=1, depth=3, maximizing_player=Player.RED)
    chance_key = agent._tt_key_chance(state, depth=3, maximizing_player=Player.RED)

    assert decision_key != chance_key
    assert decision_key[0] != chance_key[0]


def test_tt_bestmove_prioritized():
    state = build_state(red_map={1: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=9)
    moves = engine.generate_legal_moves(state, dice=1)

    pv_move = Move(piece_id=1, from_rc=(0, 0), to_rc=(1, 1))
    pv_sig = agent._move_signature(pv_move)
    key = agent._tt_key_decision(state, dice=1, depth=2, maximizing_player=Player.RED)
    agent._ttable[key] = agent.TTEntry(value=0.0, depth=2, bound=agent.Bound.EXACT, best_move_sig=pv_sig)

    tt_pv_sig = agent._tt_best_move_sig(agent._ttable[key], moves)
    ordered = agent._order_moves(state, moves, ply=0, pv_sig=tt_pv_sig)

    assert ordered[0] == pv_move


def test_tt_bestmove_promoted_in_child_decision():
    state = build_state(red_map={2: (0, 0)}, blue_map={}, turn=Player.RED)
    agent = ExpectiminimaxAgent(seed=10)
    moves = engine.generate_legal_moves(state, dice=2)

    pv_move = Move(piece_id=2, from_rc=(0, 0), to_rc=(1, 1))
    pv_sig = agent._move_signature(pv_move)
    key = agent._tt_key_decision(state, dice=2, depth=3, maximizing_player=Player.RED)
    agent._ttable[key] = agent.TTEntry(value=0.0, depth=3, bound=agent.Bound.EXACT, best_move_sig=pv_sig)

    promoted = agent._promote_tt_best_move_first(moves, agent._ttable[key])
    assert promoted[0] == pv_move
