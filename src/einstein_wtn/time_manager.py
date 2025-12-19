"""Dynamic time allocation for move selection."""
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set, Tuple, Union

from . import engine
from .types import Player


@dataclass
class TimeManagerConfig:
    base_frac: float = 1.0
    min_ms: int = 8
    max_ms: int = 1200
    critical_mult: float = 2.5
    endgame_mult: float = 1.8
    hurry_mult: float = 0.7
    safe_cap_frac: float = 0.12
    moves_left_buffer: int = 8
    preset: str = "custom"


def preset_time_manager(name: str) -> TimeManagerConfig:
    preset = name.lower()
    if preset == "fast":
        return TimeManagerConfig(
            base_frac=1.0,
            min_ms=8,
            max_ms=350,
            critical_mult=2.5,
            endgame_mult=1.8,
            hurry_mult=0.7,
            safe_cap_frac=0.08,
            moves_left_buffer=8,
            preset="fast",
        )
    if preset == "slow":
        return TimeManagerConfig(
            base_frac=1.0,
            min_ms=10,
            max_ms=3200,
            critical_mult=3.0,
            endgame_mult=2.0,
            hurry_mult=0.7,
            safe_cap_frac=0.18,
            moves_left_buffer=8,
            preset="slow",
        )
    if preset == "default":
        return TimeManagerConfig(
            base_frac=1.0,
            min_ms=8,
            max_ms=1200,
            critical_mult=2.5,
            endgame_mult=1.8,
            hurry_mult=0.7,
            safe_cap_frac=0.12,
            moves_left_buffer=8,
            preset="default",
        )
    raise ValueError(f"Unknown time manager preset '{name}'")


def _reachable_squares_for_pieces(
    positions: Sequence[Optional[Tuple[int, int]]], directions: Iterable[Tuple[int, int]]
) -> Set[Tuple[int, int]]:
    squares: Set[Tuple[int, int]] = set()
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


def estimate_moves_left(state) -> int:
    """Crude estimate of how many plies remain.

    Uses the closest piece distance to the target corner plus surviving material
    to avoid over-allocating early and starving the clock late.
    """

    def _min_steps_to_target(
        target: Tuple[int, int], positions: Sequence[Optional[Tuple[int, int]]]
    ) -> int:
        steps = []
        tr, tc = target
        for coord in positions:
            if coord is None:
                continue
            r, c = coord
            dr = abs(tr - r)
            dc = abs(tc - c)
            steps.append(max(dr, dc))
        return min(steps) if steps else 12

    red_steps = _min_steps_to_target(engine.TARGET_RED, state.pos_red.values())
    blue_steps = _min_steps_to_target(engine.TARGET_BLUE, state.pos_blue.values())
    material = _alive_count(state)
    guess = red_steps + blue_steps + material
    return max(8, min(60, guess))


def compute_move_budget_ms(
    state,
    dice: int,
    remaining_ms: Union[float, int],
    agent_name: str,
    cfg: Optional[TimeManagerConfig] = None,
) -> int:
    """Compute a per-move budget based on urgency and remaining time."""

    cfg = cfg or TimeManagerConfig()
    _ = agent_name  # Reserved for future agent-specific tuning.
    if remaining_ms is None or remaining_ms == float("inf"):
        return cfg.max_ms

    moves_left = estimate_moves_left(state)
    baseline = (remaining_ms / float(moves_left + cfg.moves_left_buffer)) * cfg.base_frac
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
    safe_cap = min(cfg.max_ms, remaining_ms * cfg.safe_cap_frac)
    budget = min(budget, safe_cap)

    if remaining_ms < cfg.min_ms:
        budget = remaining_ms
    else:
        budget = max(cfg.min_ms, budget)
        budget = min(budget, remaining_ms)

    compute_move_budget_ms.last_flags = flags  # type: ignore[attr-defined]
    compute_move_budget_ms.last_baseline = baseline  # type: ignore[attr-defined]
    compute_move_budget_ms.last_moves_left = moves_left  # type: ignore[attr-defined]
    compute_move_budget_ms.last_safe_cap = safe_cap  # type: ignore[attr-defined]
    compute_move_budget_ms.last_preset = getattr(cfg, "preset", "custom")  # type: ignore[attr-defined]
    return int(max(0, budget))
