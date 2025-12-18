"""CLI runner for Einstein WTN.

Usage examples:
- Single game: ``python -m einstein_wtn.runner --mode game --red heuristic --blue random --seed 42``
- Match (best of 7): ``python -m einstein_wtn.runner --mode match --red heuristic --blue heuristic``
"""

from __future__ import annotations

import argparse
import random
import time
from typing import Callable, List, Optional

from . import engine
from .agents import HeuristicAgent, RandomAgent
from .types import GameState, Player

AgentFactory = Callable[[Optional[int]], RandomAgent]


def _build_agent(name: str, seed: Optional[int]) -> RandomAgent:
    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent(seed=seed)
    raise ValueError(f"Unknown agent '{name}'")


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
) -> Player:
    rng = random.Random(seed)
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=first)
    time_remaining = {
        Player.RED: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
        Player.BLUE: float("inf") if time_limit_seconds is None else float(time_limit_seconds),
    }

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
        )
        wins[victor] += 1
        print(f"Result: {victor.name} wins (score {wins[Player.RED]}-{wins[Player.BLUE]})")

    overall = Player.RED if wins[Player.RED] > wins[Player.BLUE] else Player.BLUE
    print(f"Match winner: {overall.name}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Einstein WTN runner")
    parser.add_argument("--mode", choices=["game", "match"], required=True)
    parser.add_argument("--red", choices=["random", "heuristic"], default="heuristic")
    parser.add_argument("--blue", choices=["random", "heuristic"], default="random")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--time-limit-seconds", type=int, default=240)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    red_agent = _build_agent(args.red, seed=args.seed)
    blue_agent = _build_agent(args.blue, seed=None if args.seed is None else args.seed + 1)

    if args.mode == "game":
        victor = _play_game(
            red_agent=red_agent,
            blue_agent=blue_agent,
            first=Player.RED,
            seed=args.seed,
            time_limit_seconds=args.time_limit_seconds,
            verbose=args.verbose,
        )
        print(f"Game winner: {victor.name}")
    else:
        _play_match(
            red_agent=red_agent,
            blue_agent=blue_agent,
            seed=args.seed,
            time_limit_seconds=args.time_limit_seconds,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
