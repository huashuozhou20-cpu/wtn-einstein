"""Agents for playing Einstein WTN."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

from . import engine
from .types import Move, Player

if TYPE_CHECKING:
    from .opening import LayoutSearchAgent


@dataclass
class SearchStats:
    """Aggregated statistics from a single search."""

    nodes: int
    depth_reached: int
    tt_hits: int
    tt_stores: int
    tt_exact_hits: int
    tt_lower_hits: int
    tt_upper_hits: int
    tt_cutoffs: int
    killer_hits: int
    history_hits: int
    killer_size: int
    history_size: int
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

    def _order_moves(self, state, moves: List[Move]) -> List[Move]:
        """Return moves without reordering; subclasses may override."""

        return list(moves)


class RandomAgent(Agent):
    """Agent that selects a random legal move with reproducible seeding."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")
        moves = self._order_moves(state, moves)
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
        moves = self._order_moves(state, moves)
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

    class NodeType(str, Enum):
        """Transposition table node kinds."""

        DECISION = "D"
        CHANCE = "C"

    class Bound(str, Enum):
        EXACT = "EXACT"
        LOWER = "LOWER"
        UPPER = "UPPER"

    @dataclass
    class TTEntry:
        value: float
        depth: int
        bound: "ExpectiminimaxAgent.Bound"
        best_move_sig: Optional[str] = None

    def __init__(self, max_depth: int = 3, seed: Optional[int] = None):
        self.max_depth = max_depth
        self._heuristic = HeuristicAgent(seed=seed)
        self._rng = random.Random(seed)
        self._ttable: dict[tuple, "ExpectiminimaxAgent.TTEntry"] = {}
        self.killer_moves: dict[int, list[str]] = {}
        self.history: dict[tuple[int, str], int] = {}
        self.last_stats: Optional[SearchStats] = None
        self._nodes = 0
        self._tt_hits = 0
        self._tt_stores = 0
        self._tt_exact_hits = 0
        self._tt_lower_hits = 0
        self._tt_upper_hits = 0
        self._tt_cutoffs = 0
        self._depth_reached = 0
        self._killer_hits = 0
        self._history_hits = 0
        self._killer_depth_window = 12

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        """Mirror the heuristic agent placement to prioritize depth toward the goal."""

        return self._heuristic.choose_initial_layout(player, time_budget_ms=time_budget_ms)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        self.last_stats = None
        self._nodes = 0
        self._tt_hits = 0
        self._tt_stores = 0
        self._tt_exact_hits = 0
        self._tt_lower_hits = 0
        self._tt_upper_hits = 0
        self._tt_cutoffs = 0
        self._depth_reached = 0
        self._killer_hits = 0
        self._history_hits = 0
        start_time = time.monotonic()

        self._decay_memory()

        moves = engine.generate_legal_moves(state, dice)
        if not moves:
            raise ValueError("No legal moves available")

        fallback = self._heuristic.choose_move(state, dice, time_budget_ms=time_budget_ms)
        if time_budget_ms is not None and time_budget_ms < 10:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            self.last_stats = SearchStats(
                nodes=0,
                depth_reached=0,
                tt_hits=0,
                tt_stores=0,
                tt_exact_hits=0,
                tt_lower_hits=0,
                tt_upper_hits=0,
                tt_cutoffs=0,
                killer_hits=0,
                history_hits=0,
                killer_size=len(self.killer_moves),
                history_size=len(self.history),
                elapsed_ms=elapsed_ms,
            )
            return fallback
        deadline = None if time_budget_ms is None else time.monotonic() + (time_budget_ms / 1000.0)
        best_move = fallback
        self._ttable = {}

        for depth in range(1, self.max_depth + 1):
            try:
                value, move = self._search_decision(
                    state,
                    dice,
                    depth,
                    maximizing_player=state.turn,
                    deadline=deadline,
                    ply=0,
                    alpha=float("-inf"),
                    beta=float("inf"),
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
            tt_exact_hits=self._tt_exact_hits,
            tt_lower_hits=self._tt_lower_hits,
            tt_upper_hits=self._tt_upper_hits,
            tt_cutoffs=self._tt_cutoffs,
            killer_hits=self._killer_hits,
            history_hits=self._history_hits,
            killer_size=len(self.killer_moves),
            history_size=len(self.history),
            elapsed_ms=elapsed_ms,
        )
        return best_move

    def _decay_memory(self) -> None:
        """Gently decay history scores and prune stale killer depths between moves."""

        if self.history:
            decayed: dict[tuple[int, str], int] = {}
            for key, score in self.history.items():
                player_key, sig = key
                player_id = player_key.value if isinstance(player_key, Player) else int(player_key)
                new_score = int(score * 0.8)
                if new_score > 0:
                    decayed[(player_id, sig)] = new_score
            self.history = decayed

        if self.killer_moves:
            pruned: dict[int, list[str]] = {}
            for depth, killers in self.killer_moves.items():
                if depth <= self._killer_depth_window:
                    pruned[depth] = killers[:2]
            self.killer_moves = pruned

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

        # A) Material: weight higher ids slightly to value surviving power.
        for pid, coord in state.pos_red.items():
            if coord is not None:
                score += 2 + pid * 0.5
        for pid, coord in state.pos_blue.items():
            if coord is not None:
                score -= 2 + pid * 0.5

        # B) Distance: emphasize the two closest runners to stabilize signal.
        def dist(player: Player, coord) -> int:
            target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
            return abs(target[0] - coord[0]) + abs(target[1] - coord[1])

        red_dists = sorted([dist(Player.RED, coord) for coord in state.pos_red.values() if coord is not None])
        blue_dists = sorted([dist(Player.BLUE, coord) for coord in state.pos_blue.values() if coord is not None])
        for d in red_dists[:2]:
            score += max(0, 6 - d)
        for d in blue_dists[:2]:
            score -= max(0, 6 - d)

        # C) Threat/safety: squares an opponent can reach next turn.
        def reachable_squares(player: Player):
            dirs = engine.DIRECTIONS_RED if player is Player.RED else engine.DIRECTIONS_BLUE
            positions = state.pos_red if player is Player.RED else state.pos_blue
            squares = set()
            for coord in positions.values():
                if coord is None:
                    continue
                r, c = coord
                for dr, dc in dirs:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < engine.BOARD_SIZE and 0 <= nc < engine.BOARD_SIZE:
                        squares.add((nr, nc))
            return squares

        red_reach = reachable_squares(Player.RED)
        blue_reach = reachable_squares(Player.BLUE)

        for coord in state.pos_red.values():
            if coord is not None and coord in blue_reach:
                score -= 1.5
        for coord in state.pos_blue.values():
            if coord is not None and coord in red_reach:
                score += 1.5

        return score

    def _move_signature(self, move: Move) -> str:
        """Return a stable string signature for a move."""

        return f"{move.piece_id}:{move.from_rc}->{move.to_rc}"

    def _tt_key_decision(self, state, dice: int, depth: int, maximizing_player: Player) -> tuple:
        """Key transposition entries for decision nodes, including dice."""

        return (
            self.NodeType.DECISION.value,
            state.key(),
            depth,
            maximizing_player,
            dice,
        )

    def _tt_key_chance(self, state, depth: int, maximizing_player: Player) -> tuple:
        """Key transposition entries for chance nodes."""

        return (
            self.NodeType.CHANCE.value,
            state.key(),
            depth,
            maximizing_player,
        )

    def _record_killer(self, depth: int, move: Move) -> None:
        """Track killer moves per depth, keeping the two most recent."""

        sig = self._move_signature(move)
        killers = self.killer_moves.setdefault(depth, [])
        if sig in killers:
            return
        killers.insert(0, sig)
        if len(killers) > 2:
            killers.pop()

    def _record_history(self, player: Player, move: Move, depth: int) -> None:
        """Reward moves that cause beta cutoffs with a depth-weighted score."""

        sig = self._move_signature(move)
        bonus = max(1, depth) * max(1, depth)
        key = (player.value, sig)
        self.history[key] = self.history.get(key, 0) + bonus

    def _order_moves(self, state, moves: List[Move], ply: Optional[int] = None) -> List[Move]:
        """Sort moves using win/killers/history before tactical heuristics."""

        player = state.turn
        target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
        killers = set(self.killer_moves.get(ply, [])) if ply is not None else set()

        def is_capture(move: Move) -> bool:
            r, c = move.to_rc
            occupant = state.board[r][c]
            return (occupant > 0 and player is Player.BLUE) or (occupant < 0 and player is Player.RED)

        def is_self_capture(move: Move) -> bool:
            r, c = move.to_rc
            occupant = state.board[r][c]
            return (occupant > 0 and player is Player.RED) or (occupant < 0 and player is Player.BLUE)

        def distance_gain(move: Move) -> int:
            fr, fc = move.from_rc
            tr, tc = move.to_rc
            before = abs(target[0] - fr) + abs(target[1] - fc)
            after = abs(target[0] - tr) + abs(target[1] - tc)
            return before - after

        def win_move(move: Move) -> bool:
            next_state = engine.apply_move(state, move)
            return engine.winner(next_state) == player

        scored = []
        for idx, mv in enumerate(moves):
            win = win_move(mv)
            sig = self._move_signature(mv)
            killer_hit = sig in killers
            if killer_hit:
                self._killer_hits += 1
            history_score = self.history.get((player.value, sig), 0)
            if history_score > 0:
                self._history_hits += 1
            capture = is_capture(mv)
            self_cap = is_self_capture(mv)
            gain = distance_gain(mv)
            scored.append(
                (
                    -int(win),
                    -int(killer_hit),
                    -history_score,
                    -int(capture),
                    -gain,
                    int(self_cap),
                    idx,
                    mv,
                )
            )

        scored.sort()
        return [item[-1] for item in scored]

    def _sig_to_move(self, sig: Optional[str], state, dice: int) -> Optional[Move]:
        """Find a legal move by signature if possible."""

        if sig is None:
            return None
        for mv in engine.generate_legal_moves(state, dice):
            if self._move_signature(mv) == sig:
                return mv
        return None

    def _search_decision(
        self,
        state,
        dice: int,
        depth: int,
        maximizing_player: Player,
        deadline: Optional[float],
        ply: int,
        alpha: float = float("-inf"),
        beta: float = float("inf"),
    ) -> tuple[float, Optional[Move]]:
        self._time_check(deadline)
        self._nodes += 1
        self._depth_reached = max(self._depth_reached, ply)
        alpha_orig = alpha
        beta_orig = beta
        key = self._tt_key_decision(state, dice, depth, maximizing_player)
        entry = self._ttable.get(key)
        if entry and entry.depth >= depth:
            self._tt_hits += 1
            if entry.bound is self.Bound.EXACT:
                self._tt_exact_hits += 1
                return entry.value, self._sig_to_move(entry.best_move_sig, state, dice)
            if entry.bound is self.Bound.LOWER:
                self._tt_lower_hits += 1
                alpha = max(alpha, entry.value)
                if alpha >= beta:
                    self._tt_cutoffs += 1
                    return entry.value, self._sig_to_move(entry.best_move_sig, state, dice)
            if entry.bound is self.Bound.UPPER:
                self._tt_upper_hits += 1
                beta = min(beta, entry.value)
                if alpha >= beta:
                    self._tt_cutoffs += 1
                    return entry.value, self._sig_to_move(entry.best_move_sig, state, dice)

        moves = engine.generate_legal_moves(state, dice)
        if not moves or depth == 0 or engine.is_terminal(state):
            val = self._evaluate(state, maximizing_player)
            self._store_tt_entry(key, val, depth, self.Bound.EXACT, None)
            return val, None

        player = state.turn
        best_value = float("-inf") if player is maximizing_player else float("inf")
        best_move = None

        ordered_moves = self._order_moves(state, moves, ply=ply)

        for move in ordered_moves:
            self._time_check(deadline)
            undo = engine.apply_move_inplace(state, move)
            try:
                value = self._search_chance(
                    state, depth - 1, maximizing_player, deadline, ply + 1, alpha, beta
                )
            finally:
                engine.undo_move_inplace(state, undo)
            if player is maximizing_player:
                if value > best_value or (value == best_value and best_move is None):
                    best_value, best_move = value, move
                alpha = max(alpha, best_value)
                if alpha >= beta:
                    self._record_killer(ply, move)
                    self._record_history(player, move, depth)
                    break
            else:
                if value < best_value or (value == best_value and best_move is None):
                    best_value, best_move = value, move
                beta = min(beta, best_value)
                if beta <= alpha:
                    self._record_killer(ply, move)
                    self._record_history(player, move, depth)
                    break
        best_sig = self._move_signature(best_move) if best_move is not None else None
        if best_value <= alpha_orig:
            bound = self.Bound.UPPER
        elif best_value >= beta_orig:
            bound = self.Bound.LOWER
        else:
            bound = self.Bound.EXACT
        self._store_tt_entry(key, best_value, depth, bound, best_sig)
        return best_value, best_move

    def _search_chance(
        self,
        state,
        depth: int,
        maximizing_player: Player,
        deadline: Optional[float],
        ply: int,
        alpha: float,
        beta: float,
    ) -> float:
        self._time_check(deadline)
        self._nodes += 1
        self._depth_reached = max(self._depth_reached, ply)
        key = self._tt_key_chance(state, depth, maximizing_player)
        entry = self._ttable.get(key)
        if entry and entry.depth >= depth:
            self._tt_hits += 1
            self._tt_exact_hits += 1
            return entry.value

        if depth == 0 or engine.is_terminal(state):
            val = self._evaluate(state, maximizing_player)
            self._store_tt_entry(key, val, depth, self.Bound.EXACT, None)
            return val

        total = 0.0
        for dice in range(1, 7):
            self._time_check(deadline)
            val, _ = self._search_decision(
                state, dice, depth, maximizing_player, deadline, ply + 1, alpha, beta
            )
            total += val
        avg = total / 6.0
        self._store_tt_entry(key, avg, depth, self.Bound.EXACT, None)
        return avg

    def _store_tt_entry(
        self,
        key: tuple,
        value: float,
        depth: int,
        bound: "ExpectiminimaxAgent.Bound",
        best_move_sig: Optional[str],
    ) -> None:
        existing = self._ttable.get(key)
        if existing and existing.depth > depth:
            return
        self._ttable[key] = self.TTEntry(value=value, depth=depth, bound=bound, best_move_sig=best_move_sig)
        self._tt_stores += 1


class OpeningExpectiAgent(Agent):
    """Hybrid agent: layout search for openings, expectiminimax for moves."""

    def __init__(
        self,
        seed: Optional[int] = None,
        layout_budget_ms: int = 400,
        move_agent_kwargs: Optional[dict] = None,
    ):
        from .opening import LayoutSearchAgent

        self.opening = LayoutSearchAgent(seed=seed)
        kwargs = move_agent_kwargs or {}
        self.move_agent = ExpectiminimaxAgent(seed=seed, **kwargs)
        self.layout_budget_ms = layout_budget_ms
        self.last_stats: Optional[SearchStats] = None

    def choose_initial_layout(self, player: Player, time_budget_ms: Optional[int] = None) -> List[int]:
        budget = self.layout_budget_ms if time_budget_ms is None else time_budget_ms
        return self.opening.choose_initial_layout(player, time_budget_ms=budget)

    def choose_move(self, state, dice: int, time_budget_ms: Optional[int] = None) -> Move:
        move = self.move_agent.choose_move(state, dice, time_budget_ms=time_budget_ms)
        self.last_stats = self.move_agent.last_stats
        return move
