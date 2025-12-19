"""Dynamic time allocation for move selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from . import engine
from .types import Player


@dataclass
class TimeManagerConfig:
    base_frac: float = 0.06
    min_ms: int = 8
    max_ms: int = 1200
    critical_mult: float = 2.5
    endgame_mult: float = 1.8
    hurry_mult: float = 0.7


def _reachable_squares_for_pieces(positions: Sequence[Tuple[int, int] | None], directions: Iterable[Tuple[int, int]]) -> set[tuple[int, int]]:
    squares: set[tuple[int, int]] = set()
    for coord in positions:
        if coord is None:
            continue
        r, c = coord
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < engine.BOARD_SIZE and 0 <= nc < engine.BOARD_SIZE:
                squares.add((nr, nc))
    return squares


def _has_immediate_win(state, dice: int, player: Player) -> bool:
    moves = engine.generate_legal_moves(state, dice)
    for mv in moves:
        next_state = engine.apply_move(state, mv)
        if engine.winner(next_state) == player:
            return True
    return False


def _opponent_win_threat(state, player: Player) -> bool:
    opponent = player.opponent()
    target = engine.TARGET_BLUE if opponent is Player.BLUE else engine.TARGET_RED
    dirs = engine.DIRECTIONS_BLUE if opponent is Player.BLUE else engine.DIRECTIONS_RED
    for pid, coord in (state.pos_blue.items() if opponent is Player.BLUE else state.pos_red.items()):
        if coord is None:
            continue
        r, c = coord
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if (nr, nc) == target:
                for dice in range(1, 7):
                    candidates = engine.get_movable_piece_ids(state, opponent, dice)
                    if pid in candidates:
                        return True
    return False


def _capture_opportunity(state, dice: int, player: Player) -> bool:
    moves = engine.generate_legal_moves(state, dice)
    for mv in moves:
        r, c = mv.to_rc
        occupant = state.board[r][c]
        if (occupant > 0 and player is Player.BLUE) or (occupant < 0 and player is Player.RED):
            return True
    return False


def _danger_incoming(state, player: Player) -> bool:
    opponent = player.opponent()
    dirs = engine.DIRECTIONS_RED if opponent is Player.RED else engine.DIRECTIONS_BLUE
    positions = state.pos_red.values() if opponent is Player.RED else state.pos_blue.values()
    reach = _reachable_squares_for_pieces(positions, dirs)
    own_positions = state.pos_red.values() if player is Player.RED else state.pos_blue.values()
    return any(coord is not None and coord in reach for coord in own_positions)


def _alive_count(state) -> int:
    return sum(1 for coord in state.pos_red.values() if coord is not None) + sum(
        1 for coord in state.pos_blue.values() if coord is not None
    )


def compute_move_budget_ms(
    state,
    dice: int,
    remaining_ms: float | int,
    agent_name: str,
    cfg: TimeManagerConfig | None = None,
) -> int:
    """Compute a per-move budget based on urgency and remaining time."""

    cfg = cfg or TimeManagerConfig()
    _ = agent_name  # Reserved for future agent-specific tuning.
    if remaining_ms is None or remaining_ms == float("inf"):
        return cfg.max_ms

    baseline = remaining_ms * cfg.base_frac
    player = state.turn
    flags: List[str] = []

    immediate = _has_immediate_win(state, dice, player)
    if immediate:
        flags.append("WIN")
    opponent_threat = _opponent_win_threat(state, player)
    if opponent_threat:
        flags.append("THREAT")
    capture = _capture_opportunity(state, dice, player)
    if capture:
        flags.append("CAP")
    danger = _danger_incoming(state, player)
    if danger:
        flags.append("DANGER")
    endgame = _alive_count(state) <= 4
    if endgame:
        flags.append("ENDGAME")

    multiplier = 1.0
    if immediate or opponent_threat:
        multiplier *= cfg.critical_mult
    if capture:
        multiplier *= 1.2
    if danger:
        multiplier *= 1.2
    if endgame:
        multiplier *= cfg.endgame_mult

    if not flags:
        red_alive = sum(1 for coord in state.pos_red.values() if coord is not None)
        blue_alive = sum(1 for coord in state.pos_blue.values() if coord is not None)
        lead = red_alive - blue_alive if player is Player.RED else blue_alive - red_alive
        if lead >= 2:
            multiplier *= cfg.hurry_mult

    budget = baseline * multiplier
    budget = min(budget, cfg.max_ms)

    safe_cap = max(cfg.min_ms, int(remaining_ms * 0.2))
    budget = min(budget, safe_cap)

    if remaining_ms < cfg.min_ms:
        budget = remaining_ms
    else:
        budget = max(cfg.min_ms, budget)
        budget = min(budget, remaining_ms)

    compute_move_budget_ms.last_flags = flags  # type: ignore[attr-defined]
    compute_move_budget_ms.last_baseline = baseline  # type: ignore[attr-defined]
    return int(max(0, budget))
