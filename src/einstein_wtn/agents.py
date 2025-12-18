"""Agents for playing Einstein WTN."""

from __future__ import annotations

import random
from typing import Optional

from . import engine
from .types import Move, Player


class Agent:
    """Base class for agents."""

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:  # noqa: D401
        """Return a move for the given state and dice."""

        raise NotImplementedError


class RandomAgent(Agent):
    """Agent that selects a random legal move with reproducible seeding."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")
        return self._rng.choice(moves)


class HeuristicAgent(Agent):
    """Agent using a lightweight heuristic.

    Priority: immediate win > capturing opponent > closer to own target. RNG breaks ties.
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def _distance_to_goal(self, player: Player, coord) -> int:
        target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
        r, c = coord
        tr, tc = target
        return abs(tr - r) + abs(tc - c)

    def _is_capture(self, state, move: Move, player: Player) -> bool:
        r, c = move.to_rc
        occupant = state.board[r][c]
        return (occupant > 0 and player is Player.BLUE) or (occupant < 0 and player is Player.RED)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        player = state.turn
        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")

        scored = []
        for mv in moves:
            new_state = engine.apply_move(state, mv)
            win = engine.winner(new_state) == player
            capture = self._is_capture(state, mv, player)
            distance = self._distance_to_goal(player, mv.to_rc)
            scored.append((win, capture, -distance, mv))

        best_score = max(score[:3] for score in scored)
        best_moves = [mv for score in scored if score[:3] == best_score for mv in [score[3]]]
        return self._rng.choice(best_moves)
