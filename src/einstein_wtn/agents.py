"""Agents for playing Einstein WTN."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import List, Optional

from . import engine
from .types import Move, Player


@dataclass
class SearchStats:
    """Aggregated statistics from a single search."""

    nodes: int
    depth_reached: int
    tt_hits: int
    tt_stores: int
    elapsed_ms: float


class Agent:
    """Base class for agents."""

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:  # noqa: D401
        """Return a move for the given state and dice."""

        raise NotImplementedError

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        """Return a permutation of piece ids 1..6 describing start placement order."""

        _ = time_budget_ms  # Unused in the base class.
        return [1, 2, 3, 4, 5, 6]


class RandomAgent(Agent):
    """Agent that selects a random legal move with reproducible seeding."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")
        return self._rng.choice(moves)

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        _ = player, time_budget_ms
        order = [1, 2, 3, 4, 5, 6]
        self._rng.shuffle(order)
        return order


class HeuristicAgent(Agent):
    """Agent using a lightweight heuristic.

    Priority: immediate win > capturing opponent > closer to own target. RNG breaks ties.
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        """Place higher ids closer to the goal corner to maximize early dice hits."""

        _ = time_budget_ms
        # Sort start cells by proximity to the player's goal so larger ids sit deeper.
        target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
        start_cells = engine.START_RED_CELLS if player is Player.RED else engine.START_BLUE_CELLS
        cell_order = sorted(start_cells, key=lambda rc: -(abs(target[0] - rc[0]) + abs(target[1] - rc[1])))
        # Assign largest ids to closest cells.
        placement = {}
        for pid, cell in zip(range(6, 0, -1), cell_order):
            placement[cell] = pid
        return [placement[cell] for cell in start_cells]

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


class ExpectiminimaxAgent(Agent):
    """Agent using expectiminimax with iterative deepening over dice chance nodes."""

    def __init__(self, max_depth: int = 3, seed: Optional[int] = None):
        self.max_depth = max_depth
        self._heuristic = HeuristicAgent(seed=seed)
        self._rng = random.Random(seed)
        self._ttable = {}
        self.last_stats: Optional[SearchStats] = None
        self._nodes = 0
        self._tt_hits = 0
        self._tt_stores = 0
        self._depth_reached = 0

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        """Mirror the heuristic agent placement to prioritize depth toward the goal."""

        return self._heuristic.choose_initial_layout(player, time_budget_ms=time_budget_ms)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        self.last_stats = None
        self._nodes = 0
        self._tt_hits = 0
        self._tt_stores = 0
        self._depth_reached = 0
        start_time = time.monotonic()

        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")

        fallback = self._heuristic.choose_move(state, dice, time_budget_ms=time_budget_ms)
        deadline = None if time_budget_ms is None else time.monotonic() + (time_budget_ms / 1000.0)
        best_move = fallback
        self._ttable = {}

        for depth in range(1, self.max_depth + 1):
            try:
                value, move = self._search_decision(
                    state, dice, depth, maximizing_player=state.turn, deadline=deadline, ply=0
                )
                self._depth_reached = max(self._depth_reached, depth)
            except TimeoutError:
                break
            if move is not None:
                best_move = move
            # If we already found a forced win, stop early.
            if value == float("inf"):
                break

        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        self.last_stats = SearchStats(
            nodes=self._nodes,
            depth_reached=self._depth_reached,
            tt_hits=self._tt_hits,
            tt_stores=self._tt_stores,
            elapsed_ms=elapsed_ms,
        )
        return best_move

    def _time_check(self, deadline: Optional[float]) -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError

    def _evaluate(self, state, maximizing_player: Player) -> float:
        victor = engine.winner(state)
        if victor is maximizing_player:
            return float("inf")
        if victor is maximizing_player.opponent():
            return float("-inf")

        score_red = self._red_score(state)
        return score_red if maximizing_player is Player.RED else -score_red

    def _red_score(self, state) -> float:
        """Heuristic score from Red's perspective (higher favors Red)."""

        score = 0.0
        alive_red = state.alive_red.bit_count()
        alive_blue = state.alive_blue.bit_count()
        score += (alive_red - alive_blue) * 10

        def dist(player: Player, coord) -> int:
            target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
            return abs(target[0] - coord[0]) + abs(target[1] - coord[1])

        for coord in state.pos_red.values():
            if coord is not None:
                score += 5 - dist(Player.RED, coord)
        for coord in state.pos_blue.values():
            if coord is not None:
                score -= 5 - dist(Player.BLUE, coord)
        return score

    def _search_decision(
        self,
        state,
        dice: int,
        depth: int,
        maximizing_player: Player,
        deadline: Optional[float],
        ply: int,
    ) -> tuple[float, Optional[Move]]:
        self._time_check(deadline)
        self._nodes += 1
        self._depth_reached = max(self._depth_reached, ply)
        key = (state.key(), dice, depth, "decision", maximizing_player)
        if key in self._ttable:
            self._tt_hits += 1
            return self._ttable[key]

        moves = engine.generate_legal_moves(state, dice)
        if not moves or depth == 0 or engine.is_terminal(state):
            val = self._evaluate(state, maximizing_player)
            self._ttable[key] = (val, None)
            self._tt_stores += 1
            return val, None

        player = state.turn
        best_value = float("-inf") if player is maximizing_player else float("inf")
        best_move = None

        for move in moves:
            self._time_check(deadline)
            undo = engine.apply_move_inplace(state, move)
            try:
                value = self._search_chance(state, depth - 1, maximizing_player, deadline, ply + 1)
            finally:
                engine.undo_move_inplace(state, undo)
            if player is maximizing_player:
                if value > best_value or (value == best_value and best_move is None):
                    best_value, best_move = value, move
            else:
                if value < best_value or (value == best_value and best_move is None):
                    best_value, best_move = value, move

        self._ttable[key] = (best_value, best_move)
        self._tt_stores += 1
        return best_value, best_move

    def _search_chance(
        self, state, depth: int, maximizing_player: Player, deadline: Optional[float], ply: int
    ) -> float:
        self._time_check(deadline)
        self._nodes += 1
        self._depth_reached = max(self._depth_reached, ply)
        key = (state.key(), depth, "chance", maximizing_player)
        if key in self._ttable:
            self._tt_hits += 1
            return self._ttable[key][0]

        if depth == 0 or engine.is_terminal(state):
            val = self._evaluate(state, maximizing_player)
            self._ttable[key] = (val, None)
            self._tt_stores += 1
            return val

        total = 0.0
        for dice in range(1, 7):
            self._time_check(deadline)
            val, _ = self._search_decision(state, dice, depth, maximizing_player, deadline, ply + 1)
            total += val
        avg = total / 6.0
        self._ttable[key] = (avg, None)
        self._tt_stores += 1
        return avg
