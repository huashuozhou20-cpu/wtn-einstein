"""Opening layout generation and lightweight search."""

from __future__ import annotations

import itertools
import time
from typing import Iterable, List, Sequence

from . import engine
from .agents import HeuristicAgent
from .types import Player


def generate_all_layouts() -> Iterable[List[int]]:
    """Yield all permutations of piece ids 1..6."""

    return itertools.permutations([1, 2, 3, 4, 5, 6])


def _static_layout_score(layout: Sequence[int], player: Player) -> float:
    """Fast heuristic score for a layout from the given player's perspective."""

    cells = engine.START_RED_CELLS if player is Player.RED else engine.START_BLUE_CELLS
    target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
    score = 0.0
    for pid, cell in zip(layout, cells):
        # Prefer higher ids closer to target.
        dist = abs(target[0] - cell[0]) + abs(target[1] - cell[1])
        score += pid * 2 - dist
    return score


def _red_position_score(state) -> float:
    """Red-centric positional heuristic mirrored from expectiminimax."""

    score = 0.0
    for pid, coord in state.pos_red.items():
        if coord is not None:
            score += 2 + pid * 0.5
    for pid, coord in state.pos_blue.items():
        if coord is not None:
            score -= 2 + pid * 0.5

    def dist(player: Player, coord) -> int:
        target = engine.TARGET_RED if player is Player.RED else engine.TARGET_BLUE
        return abs(target[0] - coord[0]) + abs(target[1] - coord[1])

    red_dists = sorted([dist(Player.RED, coord) for coord in state.pos_red.values() if coord is not None])
    blue_dists = sorted([dist(Player.BLUE, coord) for coord in state.pos_blue.values() if coord is not None])
    for d in red_dists[:2]:
        score += max(0, 6 - d)
    for d in blue_dists[:2]:
        score -= max(0, 6 - d)

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


def _arrangement_to_layout(order: Sequence[int], start_cells: Sequence[tuple[int, int]]) -> List[tuple[int, int]]:
    layout: List[tuple[int, int]] = [None] * 6  # type: ignore[list-item]
    for idx, piece_id in enumerate(order):
        layout[piece_id - 1] = start_cells[idx]
    return layout  # type: ignore[return-value]


def score_layout(layout: Sequence[int], player: Player, budget_ms: int | None = None, seed: int | None = None) -> float:
    """Score a layout; may include a short playout within budget.

    Falls back to a static score if time is short.
    """

    start = time.monotonic()
    if budget_ms is not None and budget_ms <= 5:
        return _static_layout_score(layout, player)

    rng_seed = seed or 0
    rng = iter((rng_seed * 1103515245 + 12345 + i) % (2**31) for i in itertools.count())

    base_agent = HeuristicAgent(seed=next(rng))
    opponent_agent = HeuristicAgent(seed=next(rng))
    opp_layout = opponent_agent.choose_initial_layout(player.opponent())

    layout_cells = engine.START_RED_CELLS if player is Player.RED else engine.START_BLUE_CELLS
    opp_cells = engine.START_BLUE_CELLS if player is Player.RED else engine.START_RED_CELLS

    layout_coords = _arrangement_to_layout(layout, layout_cells)
    opp_coords = _arrangement_to_layout(opp_layout, opp_cells)

    first = player
    state = engine.new_game(layout_coords if player is Player.RED else opp_coords,
                            opp_coords if player is Player.RED else layout_coords,
                            first=first)

    max_turns = 8
    dice_sequence = [(next(rng) % 6) + 1 for _ in range(max_turns)]

    for idx in range(max_turns):
        if budget_ms is not None and (time.monotonic() - start) * 1000 > budget_ms:
            break
        dice = dice_sequence[idx]
        current = state.turn
        agent = base_agent if current is player else opponent_agent
        move = agent.choose_move(state, dice)
        state = engine.apply_move(state, move)
        if engine.is_terminal(state):
            break

    # Use Red perspective eval and flip if player is Blue.
    red_score = _red_position_score(state)
    return red_score if player is Player.RED else -red_score


class LayoutSearchAgent(HeuristicAgent):
    """Agent that searches opening layouts within a small time budget."""

    def __init__(self, seed: int | None = None, sample_size: int = 100, top_k: int = 15):
        super().__init__(seed=seed)
        self.sample_size = sample_size
        self.top_k = top_k
        self._seed = seed or 0

    def choose_initial_layout(self, player: Player, time_budget_ms: int | None = None) -> List[int]:
        budget_ms = 200 if time_budget_ms is None else time_budget_ms
        start = time.monotonic()
        rng = self._rng

        layouts = list(generate_all_layouts())
        rng.shuffle(layouts)
        candidates = layouts[: min(self.sample_size, len(layouts))]

        scored = []
        per_candidate_budget = max(5, budget_ms // max(1, len(candidates)))
        for layout in candidates:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > budget_ms * 0.9:
                break
            val = score_layout(layout, player, budget_ms=per_candidate_budget, seed=self._seed)
            scored.append((val, layout))

        if not scored:
            return super().choose_initial_layout(player, time_budget_ms=budget_ms)

        scored.sort(key=lambda x: x[0], reverse=True)
        finalists = scored[: self.top_k]

        best_score = None
        best_layout = None
        for val, layout in finalists:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > budget_ms:
                break
            # Refine with slightly more budget if available.
            refined = score_layout(layout, player, budget_ms=min(50, max(5, budget_ms // 2)), seed=self._seed + 1)
            total_score = (val + refined) / 2
            if best_score is None or total_score > best_score:
                best_score = total_score
                best_layout = layout

        if best_layout is None:
            best_layout = finalists[0][1]
        return list(best_layout)
