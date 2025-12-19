"""Opening layout generation and lightweight search."""

from __future__ import annotations

import itertools
import random
import time
from typing import Dict, Iterable, List, Sequence

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent
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


def score_layout(
    layout: Sequence[int],
    player: Player,
    budget_ms: int | None = None,
    seed: int | None = None,
    mode: str = "mini-expecti",
    opponent_layouts: Sequence[Sequence[int]] | None = None,
) -> float:
    """Score a layout with either static or mini-expecti evaluation."""

    start = time.monotonic()
    if budget_ms is not None and budget_ms <= 5 or mode == "static":
        return _static_layout_score(layout, player)

    rng = random.Random(seed or 0)

    # Prepare opponent layouts; include a heuristic placement to avoid overfitting.
    if opponent_layouts is None:
        heuristic_order = HeuristicAgent(seed=seed).choose_initial_layout(player.opponent())
        opponent_layouts = [
            [1, 2, 3, 4, 5, 6],
            [6, 5, 4, 3, 2, 1],
            heuristic_order,
        ]

    expecti = ExpectiminimaxAgent(max_depth=2, seed=rng.randrange(2**31))
    opponent_agent = HeuristicAgent(seed=rng.randrange(2**31))

    layout_cells = engine.START_RED_CELLS if player is Player.RED else engine.START_BLUE_CELLS
    opp_cells = engine.START_BLUE_CELLS if player is Player.RED else engine.START_RED_CELLS

    dice_sequences = [[rng.randrange(6) + 1 for _ in range(6)] for _ in range(10)]
    seqs_to_use = len(dice_sequences)
    if budget_ms is not None:
        seqs_to_use = max(1, min(len(dice_sequences), max(1, budget_ms // 12)))

    scores = []
    for opp_layout in opponent_layouts:
        layout_coords = _arrangement_to_layout(layout, layout_cells)
        opp_coords = _arrangement_to_layout(opp_layout, opp_cells)
        state = engine.new_game(
            layout_coords if player is Player.RED else opp_coords,
            opp_coords if player is Player.RED else layout_coords,
            first=player,
        )

        for seq in dice_sequences[:seqs_to_use]:
            sim_state = state.clone()
            for dice in seq:
                mover = sim_state.turn
                if mover is player:
                    mv = expecti.choose_move(sim_state, dice, time_budget_ms=8)
                else:
                    mv = opponent_agent.choose_move(sim_state, dice, time_budget_ms=4)
                sim_state = engine.apply_move(sim_state, mv)
                if engine.is_terminal(sim_state):
                    break
            victor = engine.winner(sim_state)
            if victor is player:
                scores.append(float("inf"))
            elif victor is player.opponent():
                scores.append(float("-inf"))
            else:
                val = expecti._evaluate(sim_state, player)  # type: ignore[attr-defined]
                scores.append(val)
        if budget_ms is not None and (time.monotonic() - start) * 1000 > budget_ms:
            break

    if not scores:
        return _static_layout_score(layout, player)
    if any(s == float("inf") for s in scores):
        return float("inf")
    if any(s == float("-inf") for s in scores):
        return float("-inf")
    return sum(scores) / len(scores)


class LayoutSearchAgent(HeuristicAgent):
    """Agent that searches opening layouts within a small time budget."""

    def __init__(
        self,
        seed: int | None = None,
        sample_size: int = 90,
        top_k: int = 12,
        layout_eval_mode: str = "mini-expecti",
        layout_eval_budget_ms: int = 300,
    ):
        super().__init__(seed=seed)
        self.sample_size = sample_size
        self.top_k = top_k
        self._seed = seed or 0
        self.layout_eval_mode = layout_eval_mode
        self.layout_eval_budget_ms = layout_eval_budget_ms
        self.last_opening_stats: Dict[str, float | int] | None = None

    def choose_initial_layout(self, player: Player, time_budget_ms: int | None = None) -> List[int]:
        budget_ms = 200 if time_budget_ms is None else time_budget_ms
        start = time.monotonic()
        rng = random.Random(self._seed)

        layouts = list(generate_all_layouts())
        static_scored = [(_static_layout_score(layout, player) + rng.random() * 1e-6, layout) for layout in layouts]
        static_scored.sort(key=lambda item: item[0], reverse=True)
        candidates = [layout for _, layout in static_scored[: min(self.sample_size, len(static_scored))]]
        baseline = [
            [1, 2, 3, 4, 5, 6],
            [6, 5, 4, 3, 2, 1],
            HeuristicAgent(seed=self._seed).choose_initial_layout(player),
        ]
        for layout in baseline:
            if layout not in candidates:
                candidates.append(tuple(layout))
        max_candidates = min(len(candidates), max(1, budget_ms // 90))

        scored = []
        per_candidate_budget = max(25, budget_ms // max(1, max_candidates))
        for layout in candidates[:max_candidates]:
            val = score_layout(
                layout,
                player,
                budget_ms=min(per_candidate_budget, self.layout_eval_budget_ms),
                seed=self._seed,
                mode=self.layout_eval_mode,
            )
            scored.append((val, layout))

        if not scored:
            return super().choose_initial_layout(player, time_budget_ms=budget_ms)

        scored.sort(key=lambda x: x[0], reverse=True)
        finalists = scored[: self.top_k]

        best_score = None
        best_layout = None
        refine_limit = min(3, len(finalists))
        for val, layout in finalists[:refine_limit]:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms > budget_ms:
                break
            # Refine with slightly more budget if available.
            refined = score_layout(
                layout,
                player,
                budget_ms=min(self.layout_eval_budget_ms, max(5, budget_ms // max(2, refine_limit))),
                seed=self._seed + 1,
                mode=self.layout_eval_mode,
            )
            total_score = (val + refined) / 2
            if best_score is None or total_score > best_score:
                best_score = total_score
                best_layout = layout

        if best_layout is None:
            best_layout = finalists[0][1]
            best_score = finalists[0][0]
        elapsed_ms = (time.monotonic() - start) * 1000
        self.last_opening_stats = {
            "evaluated_candidates": len(scored),
            "top_k": len(finalists),
            "elapsed_ms": elapsed_ms,
            "best_score": best_score if best_score is not None else 0.0,
            "mode": self.layout_eval_mode,
        }
        return list(best_layout)
