"""Tournament/benchmark runner for Einstein WTN.

Usage example:
- python -m einstein_wtn.tournament --games 200 --red expecti --blue heuristic --seed 1
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent, SearchStats
from .opening import LayoutSearchAgent
from .runner import parse_layout_string, play_game
from .time_manager import TimeManagerConfig, preset_time_manager
from .types import Player


@dataclass
class SideSearchSummary:
    samples: int
    avg_depth: float
    avg_nodes: float
    tt_hit_rate: float


@dataclass
class TournamentResult:
    games: int
    red_wins: int
    blue_wins: int
    avg_turns: float
    avg_move_time_ms: Dict[Player, float]
    side_stats: Dict[Player, SideSearchSummary]
    budget_stats: Dict[Player, "BudgetSideSummary"]


@dataclass
class BudgetSideSummary:
    samples: int
    avg_budget_ms: float
    avg_baseline_ms: float
    avg_safe_cap_ms: float
    avg_moves_left: float
    preset: str


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


def _average(values):
    return 0.0 if not values else sum(values) / len(values)


def _summarize_search(records) -> SideSearchSummary:
    if not records:
        return SideSearchSummary(samples=0, avg_depth=0.0, avg_nodes=0.0, tt_hit_rate=0.0)
    hits = sum(s.tt_hits for s in records)
    stores = sum(s.tt_stores for s in records)
    total = hits + stores
    hit_rate = 0.0 if total == 0 else hits / total
    return SideSearchSummary(
        samples=len(records),
        avg_depth=_average([s.depth_reached for s in records]),
        avg_nodes=_average([s.nodes for s in records]),
        tt_hit_rate=hit_rate,
    )


def _summarize_budget(records) -> BudgetSideSummary:
    if not records:
        return BudgetSideSummary(
            samples=0,
            avg_budget_ms=0.0,
            avg_baseline_ms=0.0,
            avg_safe_cap_ms=0.0,
            avg_moves_left=0.0,
            preset="",
        )
    return BudgetSideSummary(
        samples=len(records),
        avg_budget_ms=_average([r.get("budget_ms", 0) for r in records]),
        avg_baseline_ms=_average([r.get("baseline_ms", 0) for r in records]),
        avg_safe_cap_ms=_average([r.get("safe_cap", 0) for r in records]),
        avg_moves_left=_average([r.get("moves_left", 0) for r in records]),
        preset=str(records[0].get("preset", "")),
    )


def run_tournament(
    red_agent,
    blue_agent,
    games: int = 200,
    seed: int = 0,
    time_limit_seconds: Optional[int] = 240,
    red_layout: Optional[Sequence[int]] = None,
    blue_layout: Optional[Sequence[int]] = None,
    quiet: bool = True,
    collect_stats: bool = False,
    tm_cfg=None,
) -> TournamentResult:
    rng = random.Random(seed)
    red_wins = 0
    blue_wins = 0
    total_turns = 0
    move_times: Dict[Player, list[float]] = {Player.RED: [], Player.BLUE: []}
    search_records: Dict[Player, list[SearchStats]] = {Player.RED: [], Player.BLUE: []}
    budget_records: Dict[Player, list[dict]] = {Player.RED: [], Player.BLUE: []}

    for game_index in range(games):
        first = Player.RED if game_index % 2 == 0 else Player.BLUE
        game_seed = rng.randint(0, 2**31 - 1)
        summary = play_game(
            red_agent=red_agent,
            blue_agent=blue_agent,
            first=first,
            seed=game_seed,
            time_limit_seconds=time_limit_seconds,
            time_manager_cfg=tm_cfg,
            emit_moves=not quiet,
            show_board=False,
            show_stats=False,
            collect_stats=collect_stats,
            red_order=red_layout,
            blue_order=blue_layout,
        )

        total_turns += summary.turns
        move_times[Player.RED].extend(summary.move_times[Player.RED])
        move_times[Player.BLUE].extend(summary.move_times[Player.BLUE])
        if summary.winner is Player.RED:
            red_wins += 1
        else:
            blue_wins += 1

        if collect_stats:
            search_records[Player.RED].extend(summary.search_stats[Player.RED])
            search_records[Player.BLUE].extend(summary.search_stats[Player.BLUE])
            budget_records[Player.RED].extend(summary.budgets.get(Player.RED, []))
            budget_records[Player.BLUE].extend(summary.budgets.get(Player.BLUE, []))

    avg_turns = total_turns / games if games else 0.0
    avg_move_time_ms = {
        Player.RED: _average(move_times[Player.RED]),
        Player.BLUE: _average(move_times[Player.BLUE]),
    }

    side_stats = {
        Player.RED: _summarize_search(search_records[Player.RED]),
        Player.BLUE: _summarize_search(search_records[Player.BLUE]),
    }
    budget_stats = {
        Player.RED: _summarize_budget(budget_records[Player.RED]),
        Player.BLUE: _summarize_budget(budget_records[Player.BLUE]),
    }

    return TournamentResult(
        games=games,
        red_wins=red_wins,
        blue_wins=blue_wins,
        avg_turns=avg_turns,
        avg_move_time_ms=avg_move_time_ms,
        side_stats=side_stats,
        budget_stats=budget_stats,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Einstein WTN tournament/benchmark runner")
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument(
        "--red", choices=["random", "heuristic", "expecti", "layoutsearch", "opening-expecti"], default="expecti"
    )
    parser.add_argument(
        "--blue", choices=["random", "heuristic", "expecti", "layoutsearch", "opening-expecti"], default="heuristic"
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit-seconds", type=int, default=240)
    parser.add_argument("--red-layout", type=str, default=None)
    parser.add_argument("--blue-layout", type=str, default=None)
    parser.add_argument("--stats", action="store_true", help="Collect and print expecti search statistics")
    parser.add_argument("--quiet", dest="quiet", action="store_true", help="Suppress per-move logs", default=True)
    parser.add_argument("--no-quiet", dest="quiet", action="store_false", help="Show per-move logs")
    parser.add_argument("--tm-preset", type=str, default="default", choices=["fast", "default", "slow"], help="Time manager preset")
    parser.add_argument("--tm-base-frac", type=float, default=None, help="Scale baseline derived from moves-left estimate")
    parser.add_argument("--tm-min-ms", type=int, default=None, help="Minimum per-move budget")
    parser.add_argument("--tm-max-ms", type=int, default=None, help="Maximum per-move budget")
    parser.add_argument("--tm-critical-mult", type=float, default=None, help="Critical turn multiplier")
    parser.add_argument("--tm-endgame-mult", type=float, default=None, help="Endgame multiplier")
    parser.add_argument("--tm-safe-cap-frac", type=float, default=None, help="Cap fraction of remaining time per move")
    return parser.parse_args(argv)


def main(argv=None):
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

    tm_cfg = _tm_cfg_from_args()

    red_agent = _build_agent(args.red, seed=args.seed)
    blue_agent = _build_agent(args.blue, seed=None if args.seed is None else args.seed + 1)

    result = run_tournament(
        red_agent=red_agent,
        blue_agent=blue_agent,
        games=args.games,
        seed=args.seed,
        time_limit_seconds=args.time_limit_seconds,
        red_layout=red_order,
        blue_layout=blue_order,
        quiet=args.quiet,
        collect_stats=args.stats,
        tm_cfg=tm_cfg,
    )

    print(f"Red wins: {result.red_wins}, Blue wins: {result.blue_wins}")
    print(f"Win rate (Red): {result.red_wins / result.games:.3f}")
    print(f"Average turns: {result.avg_turns:.2f}")
    print(
        f"Average move time ms - Red: {result.avg_move_time_ms[Player.RED]:.2f}, "
        f"Blue: {result.avg_move_time_ms[Player.BLUE]:.2f}"
    )

    if args.stats:
        print(f"Time manager preset: {args.tm_preset}")
        for side in (Player.RED, Player.BLUE):
            summary = result.side_stats[side]
            if summary.samples == 0:
                print(f"{side.name} expecti stats: (no data)")
                continue
            print(
                f"{side.name} expecti stats: samples={summary.samples} avg_depth={summary.avg_depth:.2f} "
                f"avg_nodes={summary.avg_nodes:.1f} tt_hit_rate={summary.tt_hit_rate:.3f}"
            )
        for side in (Player.RED, Player.BLUE):
            budget = result.budget_stats[side]
            if budget.samples == 0:
                print(f"{side.name} time stats: (no data)")
                continue
            print(
                f"{side.name} time stats: preset={budget.preset or args.tm_preset} samples={budget.samples} "
                f"avg_budget_ms={budget.avg_budget_ms:.1f} baseline_ms={budget.avg_baseline_ms:.1f} "
                f"safe_cap={budget.avg_safe_cap_ms:.1f} moves_left={budget.avg_moves_left:.1f}"
            )
        # Print opening stats if available.
        for agent, name in ((red_agent, "RED"), (blue_agent, "BLUE")):
            opening_stats = getattr(agent, "last_opening_stats", None)
            if opening_stats:
                print(
                    f"{name} opening stats: evaluated={opening_stats.get('evaluated_candidates')} "
                    f"top_k={opening_stats.get('top_k')} elapsed_ms={opening_stats.get('elapsed_ms'):.1f} "
                    f"best_score={opening_stats.get('best_score')}"
                )


if __name__ == "__main__":
    main()
