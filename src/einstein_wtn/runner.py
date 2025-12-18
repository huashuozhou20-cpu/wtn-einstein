"""CLI runner for Einstein WTN.

Usage examples:
- Single game: ``python -m einstein_wtn.runner --mode game --red heuristic --blue random --seed 42``
- Match (best of 7): ``python -m einstein_wtn.runner --mode match --red heuristic --blue heuristic``
"""

from __future__ import annotations

import argparse
import random
import time
from typing import Callable, List, Optional, Sequence

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, RandomAgent
from .types import GameState, Player

AgentFactory = Callable[[Optional[int]], RandomAgent]


def _build_agent(name: str, seed: Optional[int]):
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent(seed=seed)
    if name == "expecti":
        return ExpectiminimaxAgent(seed=seed)
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


def _play_game(
    red_agent,
    blue_agent,
    first: Player,
    seed: Optional[int],
    time_limit_seconds: Optional[int],
    verbose: bool,
    red_order: Optional[Sequence[int]],
    blue_order: Optional[Sequence[int]],
) -> Player:
    rng = random.Random(seed)
    time_remaining = {
        Player.RED: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
        Player.BLUE: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
    }

    def _budget(player: Player) -> Optional[int]:
        remaining = time_remaining[player]
        if remaining == float("inf"):
            return None
        return max(0, int(min(remaining * 1000, 100)))

    def _select_order(agent, player: Player, provided: Optional[Sequence[int]]) -> List[int]:
        start = time.monotonic()
        if provided is not None:
            order = list(provided)
        else:
            order = agent.choose_initial_layout(player, time_budget_ms=_budget(player))
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
        if verbose:
            print(f"{timed_out_player.name} exceeded time selecting layout. {timed_out_player.opponent().name} wins by timeout.")
        return timed_out_player.opponent()

    layout_red = arrangement_to_layout(red_order_final, engine.START_RED_CELLS)
    layout_blue = arrangement_to_layout(blue_order_final, engine.START_BLUE_CELLS)
    state = engine.new_game(layout_red, layout_blue, first=first)

    turn_counter = 1
    while True:
        player = state.turn
        dice = rng.randint(1, 6)
        agent = red_agent if player is Player.RED else blue_agent
        budget_ms = None if time_limit_seconds is None else max(0, int(time_remaining[player] * 1000))

        start = time.monotonic()
        move = agent.choose_move(state, dice, time_budget_ms=budget_ms)
        elapsed = time.monotonic() - start
        time_remaining[player] -= elapsed
        if time_remaining[player] < 0:
            if verbose:
                print(f"{player.name} exceeded time. {player.opponent().name} wins by timeout.")
            return player.opponent()

        print(f"Turn {turn_counter}: {player.name} rolled {dice} -> {move}")
        state = engine.apply_move(state, move)
        turn_counter += 1

        if verbose:
            print(_format_board(state.board))
            print()

        victor = engine.winner(state)
        if victor is not None:
            if verbose:
                print(f"Winner: {victor.name}")
            return victor


def _play_match(
    red_agent,
    blue_agent,
    seed: Optional[int],
    time_limit_seconds: Optional[int],
    verbose: bool,
    red_order: Optional[Sequence[int]],
    blue_order: Optional[Sequence[int]],
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
        victor = _play_game(
            red_agent=red_agent,
            blue_agent=blue_agent,
            first=first,
            seed=game_seed,
            time_limit_seconds=time_limit_seconds,
            verbose=verbose,
            red_order=red_order,
            blue_order=blue_order,
        )
        wins[victor] += 1
        print(f"Result: {victor.name} wins (score {wins[Player.RED]}-{wins[Player.BLUE]})")

    overall = Player.RED if wins[Player.RED] > wins[Player.BLUE] else Player.BLUE
    print(f"Match winner: {overall.name}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Einstein WTN runner")
    parser.add_argument("--mode", choices=["game", "match"], required=True)
    parser.add_argument("--red", choices=["random", "heuristic", "expecti"], default="heuristic")
    parser.add_argument("--blue", choices=["random", "heuristic", "expecti"], default="random")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--time-limit-seconds", type=int, default=240)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--red-layout", type=str, default=None, help="Comma-separated permutation like 1,2,3,4,5,6")
    parser.add_argument("--blue-layout", type=str, default=None, help="Comma-separated permutation like 6,5,4,3,2,1")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    try:
        red_order = parse_layout_string(args.red_layout) if args.red_layout else None
        blue_order = parse_layout_string(args.blue_layout) if args.blue_layout else None
    except ValueError as exc:
        print(f"Invalid layout: {exc}")
        raise SystemExit(1)

    red_agent = _build_agent(args.red, seed=args.seed)
    blue_agent = _build_agent(args.blue, seed=None if args.seed is None else args.seed + 1)

    try:
        if args.mode == "game":
            victor = _play_game(
                red_agent=red_agent,
                blue_agent=blue_agent,
                first=Player.RED,
                seed=args.seed,
                time_limit_seconds=args.time_limit_seconds,
                verbose=args.verbose,
                red_order=red_order,
                blue_order=blue_order,
            )
            print(f"Game winner: {victor.name}")
        else:
            _play_match(
                red_agent=red_agent,
                blue_agent=blue_agent,
                seed=args.seed,
                time_limit_seconds=args.time_limit_seconds,
                verbose=args.verbose,
                red_order=red_order,
                blue_order=blue_order,
            )
    except ValueError as exc:
        print(f"Invalid configuration: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
