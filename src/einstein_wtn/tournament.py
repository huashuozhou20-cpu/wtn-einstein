"""Tournament/benchmark runner for Einstein WTN.

Usage example:
- python -m einstein_wtn.tournament --games 200 --red expecti --blue heuristic --seed 1
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from .agents import ExpectiminimaxAgent, HeuristicAgent, RandomAgent, SearchStats
from .opening import LayoutSearchAgent
from .runner import parse_layout_string, play_game
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


def _build_agent(name: str, seed: Optional[int]):
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent(seed=seed)
    if name == "expecti":
        return ExpectiminimaxAgent(seed=seed)
    if name == "layoutsearch":
        return LayoutSearchAgent(seed=seed)
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
) -> TournamentResult:
    rng = random.Random(seed)
    red_wins = 0
    blue_wins = 0
    total_turns = 0
    move_times: Dict[Player, list[float]] = {Player.RED: [], Player.BLUE: []}
    search_records: Dict[Player, list[SearchStats]] = {Player.RED: [], Player.BLUE: []}

    for game_index in range(games):
        first = Player.RED if game_index % 2 == 0 else Player.BLUE
        game_seed = rng.randint(0, 2**31 - 1)
        summary = play_game(
            red_agent=red_agent,
            blue_agent=blue_agent,
            first=first,
            seed=game_seed,
            time_limit_seconds=time_limit_seconds,
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

    avg_turns = total_turns / games if games else 0.0
    avg_move_time_ms = {
        Player.RED: _average(move_times[Player.RED]),
        Player.BLUE: _average(move_times[Player.BLUE]),
    }

    side_stats = {
        Player.RED: _summarize_search(search_records[Player.RED]),
        Player.BLUE: _summarize_search(search_records[Player.BLUE]),
    }

    return TournamentResult(
        games=games,
        red_wins=red_wins,
        blue_wins=blue_wins,
        avg_turns=avg_turns,
        avg_move_time_ms=avg_move_time_ms,
        side_stats=side_stats,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Einstein WTN tournament/benchmark runner")
    parser.add_argument("--games", type=int, default=200)
    parser.add_argument("--red", choices=["random", "heuristic", "expecti", "layoutsearch"], default="expecti")
    parser.add_argument("--blue", choices=["random", "heuristic", "expecti", "layoutsearch"], default="heuristic")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit-seconds", type=int, default=240)
    parser.add_argument("--red-layout", type=str, default=None)
    parser.add_argument("--blue-layout", type=str, default=None)
    parser.add_argument("--stats", action="store_true", help="Collect and print expecti search statistics")
    parser.add_argument("--quiet", dest="quiet", action="store_true", help="Suppress per-move logs", default=True)
    parser.add_argument("--no-quiet", dest="quiet", action="store_false", help="Show per-move logs")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    try:
        red_order = parse_layout_string(args.red_layout) if args.red_layout else None
        blue_order = parse_layout_string(args.blue_layout) if args.blue_layout else None
    except ValueError as exc:
        print(f"Invalid layout: {exc}")
        raise SystemExit(1)

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
    )

    print(f"Red wins: {result.red_wins}, Blue wins: {result.blue_wins}")
    print(f"Win rate (Red): {result.red_wins / result.games:.3f}")
    print(f"Average turns: {result.avg_turns:.2f}")
    print(
        f"Average move time ms - Red: {result.avg_move_time_ms[Player.RED]:.2f}, "
        f"Blue: {result.avg_move_time_ms[Player.BLUE]:.2f}"
    )

    if args.stats:
        for side in (Player.RED, Player.BLUE):
            summary = result.side_stats[side]
            if summary.samples == 0:
                print(f"{side.name} expecti stats: (no data)")
                continue
            print(
                f"{side.name} expecti stats: samples={summary.samples} avg_depth={summary.avg_depth:.2f} "
                f"avg_nodes={summary.avg_nodes:.1f} tt_hit_rate={summary.tt_hit_rate:.3f}"
            )


if __name__ == "__main__":
    main()
