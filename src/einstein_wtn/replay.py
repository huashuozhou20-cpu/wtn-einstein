"""Replay WTN game records and validate moves."""
from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

from . import engine
from .wtn_format import WTNGame, parse_wtn, rc_to_sq
from .types import Player


def _format_board(board: List[List[int]]) -> str:
    lines: List[str] = []
    for row in board:
        parts: List[str] = []
        for cell in row:
            if cell == 0:
                parts.append(" . ")
            elif cell > 0:
                parts.append(f"R{cell}")
            else:
                parts.append(f"B{abs(cell)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _layout_dict_to_list(layout: dict[int, tuple[int, int]], start_cells: Iterable[tuple[int, int]]) -> List[tuple[int, int]]:
    if len(layout) != 6:
        raise ValueError("layout must contain 6 pieces")
    layout_list: List[tuple[int, int] | None] = [None] * 6
    for pid, coord in layout.items():
        if not 1 <= pid <= 6:
            raise ValueError(f"piece id out of range: {pid}")
        layout_list[pid - 1] = coord
    if any(item is None for item in layout_list):
        missing = [idx + 1 for idx, item in enumerate(layout_list) if item is None]
        raise ValueError(f"layout missing ids {missing}")
    start_set = set(start_cells)
    if set(layout_list) != start_set:
        raise ValueError("layout coordinates must match allowed start cells")
    return layout_list  # type: ignore[return-value]


def replay_game(game: WTNGame, verbose: bool = False) -> Tuple[engine.GameState, Player | None]:
    """Replay a parsed WTN game and return the final state and winner (if any)."""

    first_player = Player.RED
    if game.moves:
        first_player = Player.RED if game.moves[0][2] == "R" else Player.BLUE

    layout_red = _layout_dict_to_list(game.red_layout, engine.START_RED_CELLS)
    layout_blue = _layout_dict_to_list(game.blue_layout, engine.START_BLUE_CELLS)

    state = engine.new_game(layout_red, layout_blue, first=first_player)

    for idx, (ply, dice, color, piece_id, to_r, to_c) in enumerate(game.moves):
        if ply != idx + 1:
            raise ValueError(f"Ply numbering mismatch at move {idx + 1}: expected {idx + 1}, got {ply}")
        player = state.turn
        expected_color = "R" if player is Player.RED else "B"
        if color != expected_color:
            raise ValueError(f"Turn {ply} color mismatch: expected {expected_color}, got {color}")
        legal_moves = engine.generate_legal_moves(state, dice)
        matching = [m for m in legal_moves if m.piece_id == piece_id and m.to_rc == (to_r, to_c)]
        if not matching:
            square = rc_to_sq(to_r, to_c)
            raise ValueError(f"Illegal move at ply {ply}: {color}{piece_id} -> {square} with dice {dice}")
        move = matching[0]
        state = engine.apply_move(state, move)
        if verbose:
            square = rc_to_sq(to_r, to_c)
            print(f"Ply {ply}: {player.name} dice={dice} move={color}{piece_id}->{square}")
            print(_format_board(state.board))
            print()

    return state, engine.winner(state)


def replay_file(path: str, verbose: bool = False) -> Tuple[engine.GameState, Player | None]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    game = parse_wtn(text)
    return replay_game(game, verbose=verbose)


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Replay a WTN game file")
    parser.add_argument("--file", required=True, help="Path to WTN game file")
    parser.add_argument("--verbose", action="store_true", help="Print each board during replay")
    args = parser.parse_args(argv)

    state, winner = replay_file(args.file, verbose=args.verbose)
    if winner:
        print(f"Winner: {winner.name}")
    else:
        print("Winner: None (game not terminal)")
    print("Final board:")
    print(_format_board(state.board))


if __name__ == "__main__":
    main()
