"""Stdio adapter for competition environments.

This adapter consumes a minimal line-oriented protocol over stdin and emits a
single MOVE line for every GO command. It guards search stability by enforcing
its own deadline and falling back to the lightweight ``HeuristicAgent`` if the
primary agent errors or produces an illegal move.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent
from .types import GameState, Move, Player
from .wtn_format import WTNGame, dump_wtn


class AdapterInputError(Exception):
    """Raised when the adapter receives invalid input."""


def _parse_player(token: str) -> Player:
    try:
        return Player[token.upper()]
    except KeyError as exc:  # pragma: no cover - defensive
        raise AdapterInputError(f"Unknown player '{token}'") from exc


def _parse_board(board_csv: str) -> List[List[int]]:
    parts = board_csv.split(",")
    if len(parts) != engine.BOARD_SIZE * engine.BOARD_SIZE:
        raise AdapterInputError("Board must contain 25 comma-separated integers")
    cells: List[int] = []
    try:
        for part in parts:
            cell = int(part)
            if abs(cell) > 6:
                raise AdapterInputError("Piece ids must be within [-6,6]")
            cells.append(cell)
    except ValueError as exc:  # pragma: no cover - defensive
        raise AdapterInputError("Board entries must be integers") from exc
    board = [cells[i : i + engine.BOARD_SIZE] for i in range(0, len(cells), engine.BOARD_SIZE)]
    return board


def _state_from_tokens(turn_token: str, dice_token: str, board_csv: str) -> tuple[GameState, int]:
    turn = _parse_player(turn_token)
    try:
        dice = int(dice_token)
    except ValueError as exc:
        raise AdapterInputError("Dice must be an integer") from exc
    if dice < 1 or dice > 6:
        raise AdapterInputError("Dice must be between 1 and 6")

    board = _parse_board(board_csv)
    pos_red = {pid: None for pid in range(1, 7)}
    pos_blue = {pid: None for pid in range(1, 7)}
    alive_red = 0
    alive_blue = 0
    for r, row in enumerate(board):
        for c, cell in enumerate(row):
            if cell == 0:
                continue
            pid = abs(cell)
            coord = (r, c)
            if cell > 0:
                pos_red[pid] = coord
                alive_red |= 1 << (pid - 1)
            else:
                pos_blue[pid] = coord
                alive_blue |= 1 << (pid - 1)

    state = GameState(
        board=board,
        pos_red=pos_red,
        pos_blue=pos_blue,
        alive_red=alive_red,
        alive_blue=alive_blue,
        turn=turn,
    )
    return state, dice


def _build_agent(name: str):
    if name == "random":
        return RandomAgent()
    if name == "heuristic":
        return HeuristicAgent()
    if name == "expecti":
        return ExpectiminimaxAgent()
    if name in {"opening-expecti", "opening_expecti"}:
        return OpeningExpectiAgent()
    raise AdapterInputError(f"Unknown agent '{name}'")


@dataclass
class AdapterContext:
    player: Optional[Player] = None
    layout: Optional[str] = None
    pending_state: Optional[GameState] = None
    pending_dice: Optional[int] = None


class StdioAdapter:
    """Line-oriented adapter that plays moves via stdin/stdout."""

    def __init__(
        self,
        *,
        budget_ms: int = 50,
        agent=None,
        fallback_agent=None,
        stdin=None,
        stdout=None,
        stderr=None,
        quiet: bool = False,
        save_wtn: Optional[str] = None,
    ) -> None:
        self.budget_ms = budget_ms
        self.agent = agent or ExpectiminimaxAgent()
        self.fallback_agent = fallback_agent or HeuristicAgent()
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.ctx = AdapterContext()
        self.quiet = quiet
        self.save_wtn_path = save_wtn
        self._wtn_game: Optional[WTNGame] = None
        self._wtn_enabled = save_wtn is not None

    def _log(self, message: str, *, force: bool = False) -> None:
        if self.quiet and not force:
            return
        print(message, file=self.stderr)
        self.stderr.flush()

    def _extract_layouts_from_state(self, state: GameState) -> tuple[Dict[int, tuple[int, int]], Dict[int, tuple[int, int]]]:
        red_layout: Dict[int, tuple[int, int]] = {}
        blue_layout: Dict[int, tuple[int, int]] = {}
        for r, row in enumerate(state.board):
            for c, cell in enumerate(row):
                if cell == 0:
                    continue
                pid = abs(cell)
                target = red_layout if cell > 0 else blue_layout
                if pid in target:
                    raise ValueError(f"duplicate piece id {pid} detected")
                target[pid] = (r, c)
        if len(red_layout) != 6 or len(blue_layout) != 6:
            raise ValueError("layout must contain 6 pieces per side to save WTN")
        return red_layout, blue_layout

    def _init_wtn_if_needed(self, state: GameState) -> None:
        if not self._wtn_enabled or self._wtn_game is not None:
            return
        try:
            red_layout, blue_layout = self._extract_layouts_from_state(state)
        except ValueError as exc:
            self._log(f"WTN capture failed: {exc}", force=True)
            self._wtn_enabled = False
            return
        comments = [
            f"# stdio adapter save (budget_ms={self.budget_ms}, agent={self.agent.__class__.__name__})",
        ]
        if self.ctx.layout:
            comments.append(f"# layout_token={self.ctx.layout}")
        self._wtn_game = WTNGame(comments=comments, red_layout=red_layout, blue_layout=blue_layout, moves=[])
        self._persist_wtn()

    def _persist_wtn(self) -> None:
        if not self._wtn_enabled or self._wtn_game is None:
            return
        try:
            with open(self.save_wtn_path, "w", encoding="utf-8") as handle:
                handle.write(dump_wtn(self._wtn_game))
                handle.flush()
        except OSError as exc:  # pragma: no cover - defensive
            self._log(f"WTN save failed: {exc}", force=True)
            self._wtn_enabled = False

    def _record_move_to_wtn(self, move: Move, dice: int, color: Player) -> None:
        if not self._wtn_enabled:
            return
        if self._wtn_game is None:
            self._log("WTN game not initialized; skipping save", force=True)
            return
        ply = len(self._wtn_game.moves) + 1
        move_color = "R" if color == Player.RED else "B"
        self._wtn_game.moves.append((ply, dice, move_color, move.piece_id, move.to_rc[0], move.to_rc[1]))
        self._persist_wtn()

    def _emit_error_and_exit(self, message: str) -> int:
        self._log(f"ERROR {message}", force=True)
        print(f"ERROR {message}", file=self.stdout)
        self.stdout.flush()
        return 1

    def _choose_with_timeout(self, state: GameState, dice: int):
        result: list[Optional[Move]] = [None]
        error: list[Optional[BaseException]] = [None]

        def _run():
            try:
                result[0] = self.agent.choose_move(state, dice, time_budget_ms=self.budget_ms)
            except BaseException as exc:  # noqa: BLE001
                error[0] = exc

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_run)
        try:
            future.result(timeout=self.budget_ms / 1000)
        except TimeoutError:
            executor.shutdown(wait=False, cancel_futures=True)
            return None, TimeoutError("primary agent timed out")
        else:
            executor.shutdown(wait=True)
        return result[0], error[0]

    def _select_move(self, state: GameState, dice: int) -> Move:
        legal_moves = engine.generate_legal_moves(state, dice)
        if not legal_moves:
            raise AdapterInputError("No legal moves available")

        move, error = self._choose_with_timeout(state, dice)
        if error or move is None or move not in legal_moves:
            fallback_reason = "exception" if error else "illegal move"
            if isinstance(error, TimeoutError):
                fallback_reason = "timeout"
            self._log(f"Fallback to heuristic due to {fallback_reason}")
            try:
                move = self.fallback_agent.choose_move(state, dice)
            except Exception as exc:  # pragma: no cover - defensive
                raise AdapterInputError(f"Fallback failed: {exc}") from exc
            if move not in legal_moves:
                raise AdapterInputError("Fallback produced illegal move")
        return move

    def _handle_init(self, tokens: List[str]) -> None:
        if len(tokens) < 2:
            raise AdapterInputError("INIT requires a player token")
        player = _parse_player(tokens[1])
        layout = tokens[2] if len(tokens) > 2 else None
        self.ctx.player = player
        self.ctx.layout = layout

    def _handle_state(self, tokens: List[str]) -> None:
        if len(tokens) < 4:
            raise AdapterInputError("STATE requires turn, dice, and board csv")
        state, dice = _state_from_tokens(tokens[1], tokens[2], tokens[3])
        self.ctx.pending_state = state
        self.ctx.pending_dice = dice
        self._init_wtn_if_needed(state)

    def _handle_go(self) -> Move:
        if self.ctx.pending_state is None or self.ctx.pending_dice is None:
            raise AdapterInputError("GO received before STATE")
        move = self._select_move(self.ctx.pending_state, self.ctx.pending_dice)
        self._log(
            f"turn={self.ctx.pending_state.turn.name} dice={self.ctx.pending_dice} "
            f"move={move.piece_id}@{move.from_rc}->{move.to_rc}",
        )
        self._record_move_to_wtn(move, self.ctx.pending_dice, self.ctx.pending_state.turn)
        print(f"MOVE {move.piece_id} {move.to_rc[0]} {move.to_rc[1]}", file=self.stdout)
        self.stdout.flush()
        return move

    def run(self) -> int:
        try:
            for raw_line in self.stdin:
                line = raw_line.strip()
                if not line:
                    continue
                tokens = line.split()
                cmd = tokens[0].upper()
                if cmd == "INIT":
                    self._handle_init(tokens)
                elif cmd == "STATE":
                    self._handle_state(tokens)
                elif cmd == "GO":
                    self._handle_go()
                else:  # pragma: no cover - defensive
                    raise AdapterInputError(f"Unknown command '{cmd}'")
            return 0
        except AdapterInputError as exc:
            return self._emit_error_and_exit(str(exc))


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Stdio adapter for Einstein WTN")
    parser.add_argument(
        "--budget-ms",
        type=int,
        default=50,
        help="Deadline in milliseconds for primary agent search",
    )
    parser.add_argument(
        "--agent",
        choices=["random", "heuristic", "expecti", "opening-expecti", "opening_expecti"],
        default="expecti",
        help="Primary agent to use for move selection",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose stderr logs (protocol still goes to stdout)",
    )
    parser.add_argument(
        "--save-wtn",
        type=str,
        help="Path to persist WTN moves as they are played",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    adapter = StdioAdapter(
        budget_ms=args.budget_ms,
        agent=_build_agent(args.agent),
        quiet=args.quiet,
        save_wtn=args.save_wtn,
    )
    sys.exit(adapter.run())


if __name__ == "__main__":
    main()
