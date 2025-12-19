"""CLI runner for Einstein WTN.

Usage examples:
- Single game: ``python -m einstein_wtn.runner --mode game --red heuristic --blue random --seed 42``
- Match (best of 7): ``python -m einstein_wtn.runner --mode match --red heuristic --blue heuristic``
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent, SearchStats
from .opening import LayoutSearchAgent
from .time_manager import TimeManagerConfig, compute_move_budget_ms, preset_time_manager
from .types import GameState, Player

AgentFactory = Callable[[Optional[int]], RandomAgent]


@dataclass
class GameSummary:
    winner: Player
    turns: int
    move_times: Dict[Player, List[float]]
    search_stats: Dict[Player, List[SearchStats]]
    budgets: Dict[Player, List[dict]] = field(default_factory=dict)


def _build_agent(name: str, seed: Optional[int]):
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent(seed=seed)
    if name == "expecti":
        return ExpectiminimaxAgent(seed=seed)
    if name == "layoutsearch":
        return LayoutSearchAgent(seed=seed)
    if name in {"opening-expecti", "opening_expecti"}:
        return OpeningExpectiAgent(seed=seed)
    raise ValueError(f"Unknown agent '{name}'")


def parse_layout_string(raw: str) -> List[int]:
    """Parse a comma-separated permutation of piece ids 1..6."""

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    order = [int(p) for p in parts]
    if len(order) != 6 or sorted(order) != [1, 2, 3, 4, 5, 6]:
        raise ValueError("Layout must list each id 1..6 exactly once")
    return order


def arrangement_to_layout(order: Sequence[int], start_cells: Sequence[tuple[int, int]]) -> List[tuple[int, int]]:
    """Convert a start-cell ordering into layout coordinates for engine.new_game."""

    layout: List[tuple[int, int]] = [None] * 6  # type: ignore[list-item]
    for idx, piece_id in enumerate(order):
        if not 1 <= piece_id <= 6:
            raise ValueError("piece id must be between 1 and 6")
        layout[piece_id - 1] = start_cells[idx]
    if any(cell is None for cell in layout):
        raise ValueError("layout missing coordinates")
    return layout  # type: ignore[return-value]


def _format_board(board: List[List[int]]) -> str:
    lines: List[str] = []
    for row in board:
        cells = []
        for cell in row:
            if cell == 0:
                cells.append(" . ")
            elif cell > 0:
                cells.append(f"R{cell}")
            else:
                cells.append(f"B{abs(cell)}")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def play_game(
    red_agent,
    blue_agent,
    first: Player,
    seed: Optional[int],
    time_limit_seconds: Optional[int],
    time_manager_cfg: Optional[TimeManagerConfig],
    emit_moves: bool,
    show_board: bool,
    show_stats: bool,
    collect_stats: bool,
    red_order: Optional[Sequence[int]],
    blue_order: Optional[Sequence[int]],
) -> GameSummary:
    rng = random.Random(seed)
    time_remaining = {
        Player.RED: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
        Player.BLUE: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
    }
    tm_cfg = time_manager_cfg or TimeManagerConfig()
    move_times: Dict[Player, List[float]] = {Player.RED: [], Player.BLUE: []}
    search_stats: Dict[Player, List[SearchStats]] = {Player.RED: [], Player.BLUE: []}
    budget_records: Dict[Player, List[dict]] = {Player.RED: [], Player.BLUE: []}

    def _layout_budget(player: Player) -> Optional[int]:
        remaining = time_remaining[player]
        if remaining == float("inf"):
            return None
        return max(0, int(min(remaining * 1000, 600)))

    def _select_order(agent, player: Player, provided: Optional[Sequence[int]]) -> List[int]:
        start = time.monotonic()
        if provided is not None:
            order = list(provided)
        else:
            order = agent.choose_initial_layout(player, time_budget_ms=_layout_budget(player))
        elapsed = time.monotonic() - start
        time_remaining[player] -= elapsed
        if time_remaining[player] < 0:
            raise TimeoutError(player)
        if len(order) != 6 or sorted(order) != [1, 2, 3, 4, 5, 6]:
            raise ValueError(f"Invalid layout permutation from {player.name}: {order}")
        return order

    try:
        red_order_final = _select_order(red_agent, Player.RED, red_order)
        blue_order_final = _select_order(blue_agent, Player.BLUE, blue_order)
    except TimeoutError as exc:
        timed_out_player: Player = exc.args[0]
        if emit_moves or show_board:
            print(f"{timed_out_player.name} exceeded time selecting layout. {timed_out_player.opponent().name} wins by timeout.")
        return GameSummary(
            winner=timed_out_player.opponent(),
            turns=0,
            move_times=move_times,
            search_stats=search_stats,
            budgets=budget_records,
        )

    layout_red = arrangement_to_layout(red_order_final, engine.START_RED_CELLS)
    layout_blue = arrangement_to_layout(blue_order_final, engine.START_BLUE_CELLS)
    state = engine.new_game(layout_red, layout_blue, first=first)

    turn_counter = 1
    while True:
        player = state.turn
        dice = rng.randint(1, 6)
        agent = red_agent if player is Player.RED else blue_agent
        remaining_ms = time_remaining[player] * 1000 if time_limit_seconds is not None else None
        budget_flags = []
        if time_limit_seconds is None:
            budget_ms = None
        else:
            budget_ms = compute_move_budget_ms(
                state,
                dice,
                remaining_ms=remaining_ms,
                agent_name=agent.__class__.__name__,
                cfg=tm_cfg,
            )
            budget_flags = getattr(compute_move_budget_ms, "last_flags", [])
            baseline_ms = getattr(compute_move_budget_ms, "last_baseline", None)
            moves_left = getattr(compute_move_budget_ms, "last_moves_left", None)
            safe_cap = getattr(compute_move_budget_ms, "last_safe_cap", None)
            preset = getattr(compute_move_budget_ms, "last_preset", getattr(tm_cfg, "preset", "custom"))
            budget_records[player].append(
                {
                    "budget_ms": budget_ms,
                    "baseline_ms": baseline_ms,
                    "moves_left": moves_left,
                    "safe_cap": safe_cap,
                    "flags": list(budget_flags),
                    "preset": preset,
                }
            )

        start = time.monotonic()
        move = agent.choose_move(state, dice, time_budget_ms=budget_ms)
        elapsed = time.monotonic() - start
        time_remaining[player] -= elapsed
        move_times[player].append(elapsed * 1000.0)
        if time_remaining[player] < 0:
            if emit_moves or show_board:
                print(f"{player.name} exceeded time. {player.opponent().name} wins by timeout.")
            return GameSummary(
                winner=player.opponent(),
                turns=turn_counter,
                move_times=move_times,
                search_stats=search_stats,
                budgets=budget_records,
            )

        if emit_moves:
            print(f"Turn {turn_counter}: {player.name} rolled {dice} -> {move}")
        state = engine.apply_move(state, move)
        turn_counter += 1

        if show_board:
            print(_format_board(state.board))
            print()

        is_search_agent = isinstance(agent, (ExpectiminimaxAgent, OpeningExpectiAgent))
        if collect_stats and is_search_agent and getattr(agent, "last_stats", None) is not None:
            stats = agent.last_stats
            total_tt = stats.tt_hits + stats.tt_stores
            hit_rate = 0.0 if total_tt == 0 else stats.tt_hits / total_tt
            if show_stats:
                flag_str = "[" + ",".join(budget_flags) + "]" if budget_flags else "[]"
                remaining_after = max(0.0, time_remaining[player])
                baseline_ms = getattr(compute_move_budget_ms, "last_baseline", None)
                moves_left = getattr(compute_move_budget_ms, "last_moves_left", None)
                safe_cap = getattr(compute_move_budget_ms, "last_safe_cap", None)
                preset = getattr(compute_move_budget_ms, "last_preset", getattr(tm_cfg, "preset", "custom"))
                baseline_str = f"{baseline_ms:.1f}" if baseline_ms is not None else "-1"
                moves_left_str = str(moves_left) if moves_left is not None else "-1"
                safe_cap_str = f"{safe_cap:.1f}" if safe_cap is not None else "-1"
                print(
                    f"{player.name} expecti stats: depth={stats.depth_reached} nodes={stats.nodes} "
                    f"tt_hit_rate={hit_rate:.3f} elapsed_ms={stats.elapsed_ms:.2f} "
                    f"remaining_ms={remaining_after*1000:.1f} budget_ms={budget_ms if budget_ms is not None else -1} "
                    f"baseline_ms={baseline_str} moves_left={moves_left_str} safe_cap={safe_cap_str} "
                    f"tm_preset={preset} flags={flag_str}"
                )
            search_stats[player].append(stats)
        if show_stats and hasattr(agent, "last_opening_stats") and getattr(agent, "last_opening_stats", None):
            opening = agent.last_opening_stats
            print(
                f"{player.name} opening stats: evaluated={opening.get('evaluated_candidates')} "
                f"top_k={opening.get('top_k')} elapsed_ms={opening.get('elapsed_ms'):.1f} "
                f"best_score={opening.get('best_score')}"
            )

        victor = engine.winner(state)
        if victor is not None:
            if show_board:
                print(f"Winner: {victor.name}")
            return GameSummary(
                winner=victor,
                turns=turn_counter - 1,
                move_times=move_times,
                search_stats=search_stats,
                budgets=budget_records,
            )


def play_match(
    red_agent,
    blue_agent,
    seed: Optional[int],
    time_limit_seconds: Optional[int],
    verbose: bool,
    show_stats: bool,
    red_order: Optional[Sequence[int]],
    blue_order: Optional[Sequence[int]],
    tm_cfg: Optional[TimeManagerConfig],
) -> None:
    base_rng = random.Random(seed)
    wins = {Player.RED: 0, Player.BLUE: 0}
    first_order = [Player.RED, Player.BLUE, Player.BLUE, Player.RED, Player.RED, Player.BLUE, Player.BLUE]

    for game_index, first in enumerate(first_order, start=1):
        if wins[Player.RED] >= 4 or wins[Player.BLUE] >= 4:
            break
        game_seed = base_rng.randint(0, 2**31 - 1)
        if verbose:
            print(f"=== Game {game_index} (first: {first.name}) ===")
        summary = play_game(
            red_agent=red_agent,
            blue_agent=blue_agent,
            first=first,
            seed=game_seed,
            time_limit_seconds=time_limit_seconds,
            time_manager_cfg=tm_cfg,
            emit_moves=True,
            show_board=verbose,
            show_stats=show_stats,
            collect_stats=show_stats,
            red_order=red_order,
            blue_order=blue_order,
        )
        wins[summary.winner] += 1
        print(f"Result: {summary.winner.name} wins (score {wins[Player.RED]}-{wins[Player.BLUE]})")

    overall = Player.RED if wins[Player.RED] > wins[Player.BLUE] else Player.BLUE
    print(f"Match winner: {overall.name}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Einstein WTN runner")
    parser.add_argument("--mode", choices=["game", "match"], required=True)
    parser.add_argument(
        "--red", choices=["random", "heuristic", "expecti", "layoutsearch", "opening-expecti"], default="heuristic"
    )
    parser.add_argument(
        "--blue", choices=["random", "heuristic", "expecti", "layoutsearch", "opening-expecti"], default="random"
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--time-limit-seconds", type=int, default=240)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--red-layout", type=str, default=None, help="Comma-separated permutation like 1,2,3,4,5,6")
    parser.add_argument("--blue-layout", type=str, default=None, help="Comma-separated permutation like 6,5,4,3,2,1")
    parser.add_argument("--stats", action="store_true", help="Print expecti search stats each move")
    parser.add_argument("--tm-preset", type=str, default="default", choices=["fast", "default", "slow"], help="Time manager preset")
    parser.add_argument("--tm-base-frac", type=float, default=None, help="Scale baseline derived from moves-left estimate")
    parser.add_argument("--tm-min-ms", type=int, default=None, help="Minimum per-move budget")
    parser.add_argument("--tm-max-ms", type=int, default=None, help="Maximum per-move budget")
    parser.add_argument("--tm-critical-mult", type=float, default=None, help="Critical turn multiplier")
    parser.add_argument("--tm-endgame-mult", type=float, default=None, help="Endgame multiplier")
    parser.add_argument("--tm-safe-cap-frac", type=float, default=None, help="Cap fraction of remaining time per move")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    def _tm_cfg_from_args() -> TimeManagerConfig:
        cfg = preset_time_manager(args.tm_preset)
        if args.tm_base_frac is not None:
            cfg.base_frac = args.tm_base_frac
        if args.tm_min_ms is not None:
            cfg.min_ms = args.tm_min_ms
        if args.tm_max_ms is not None:
            cfg.max_ms = args.tm_max_ms
        if args.tm_critical_mult is not None:
            cfg.critical_mult = args.tm_critical_mult
        if args.tm_endgame_mult is not None:
            cfg.endgame_mult = args.tm_endgame_mult
        if args.tm_safe_cap_frac is not None:
            cfg.safe_cap_frac = args.tm_safe_cap_frac
        return cfg

    try:
        red_order = parse_layout_string(args.red_layout) if args.red_layout else None
        blue_order = parse_layout_string(args.blue_layout) if args.blue_layout else None
    except ValueError as exc:
        print(f"Invalid layout: {exc}")
        raise SystemExit(1)

    red_agent = _build_agent(args.red, seed=args.seed)
    blue_agent = _build_agent(args.blue, seed=None if args.seed is None else args.seed + 1)

    try:
        tm_cfg = _tm_cfg_from_args()
        if args.mode == "game":
            summary = play_game(
                red_agent=red_agent,
                blue_agent=blue_agent,
                first=Player.RED,
                seed=args.seed,
                time_limit_seconds=args.time_limit_seconds,
                time_manager_cfg=tm_cfg,
                emit_moves=True,
                show_board=args.verbose,
                show_stats=args.stats,
                collect_stats=args.stats,
                red_order=red_order,
                blue_order=blue_order,
            )
            print(f"Game winner: {summary.winner.name}")
        else:
            play_match(
                red_agent=red_agent,
                blue_agent=blue_agent,
                seed=args.seed,
                time_limit_seconds=args.time_limit_seconds,
                verbose=args.verbose,
                show_stats=args.stats,
                red_order=red_order,
                blue_order=blue_order,
                tm_cfg=tm_cfg,
            )
    except ValueError as exc:
        print(f"Invalid configuration: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
