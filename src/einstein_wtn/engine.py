"""Game engine for Einstein WTN.

Rules (see AGENTS.md for authoritative list):
- Board is 5×5 with coordinates (r, c) from top-left.
- Red start cells: (0,0),(0,1),(0,2),(1,0),(1,1),(2,0).
- Blue start cells: (4,4),(4,3),(4,2),(3,4),(3,3),(2,4).
- Red moves one step right, down, or down-right; Blue moves one step left, up, or up-left.
- Landing on any piece captures it (friendly fire allowed).
- Win: reach target corner or eliminate the opponent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .types import GameState, Move, Player

BOARD_SIZE = 5
START_RED_CELLS: Tuple[Tuple[int, int], ...] = (
    (0, 0),
    (0, 1),
    (0, 2),
    (1, 0),
    (1, 1),
    (2, 0),
)
START_BLUE_CELLS: Tuple[Tuple[int, int], ...] = (
    (4, 4),
    (4, 3),
    (4, 2),
    (3, 4),
    (3, 3),
    (2, 4),
)
TARGET_RED = (4, 4)
TARGET_BLUE = (0, 0)
DIRECTIONS_RED: Tuple[Tuple[int, int], ...] = ((0, 1), (1, 0), (1, 1))
DIRECTIONS_BLUE: Tuple[Tuple[int, int], ...] = ((0, -1), (-1, 0), (-1, -1))


def _bit_for(piece_id: int) -> int:
    return 1 << (piece_id - 1)


def _validate_layout(layout: Sequence[Tuple[int, int]], allowed: Iterable[Tuple[int, int]]) -> Tuple[Tuple[int, int], ...]:
    coords = tuple(layout)
    if len(coords) != 6:
        raise ValueError("layout must contain 6 coordinates")
    allowed_set = set(allowed)
    if set(coords) != set(allowed_set):
        missing = allowed_set - set(coords)
        extra = set(coords) - allowed_set
        raise ValueError(f"layout must use each start cell exactly once; missing={missing}, extra={extra}")
    return coords


def new_game(
    layout_red: Sequence[Tuple[int, int]],
    layout_blue: Sequence[Tuple[int, int]],
    first: Player = Player.RED,
) -> GameState:
    """Create a new game with the provided layouts.

    ``layout_red`` and ``layout_blue`` list coordinates for pieces 1..6 in order.
    """

    red_layout = _validate_layout(layout_red, START_RED_CELLS)
    blue_layout = _validate_layout(layout_blue, START_BLUE_CELLS)

    board: List[List[int]] = [[0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

    pos_red = {}
    pos_blue = {}

    for pid, coord in enumerate(red_layout, start=1):
        pos_red[pid] = coord
        r, c = coord
        board[r][c] = pid

    for pid, coord in enumerate(blue_layout, start=1):
        pos_blue[pid] = coord
        r, c = coord
        board[r][c] = -pid

    alive_mask = (1 << 6) - 1
    return GameState(
        board=board,
        pos_red=pos_red,
        pos_blue=pos_blue,
        alive_red=alive_mask,
        alive_blue=alive_mask,
        turn=first,
    )


def get_movable_piece_ids(state: GameState, player: Player, dice: int) -> List[int]:
    """Return candidate piece ids that may move for the given dice roll.

    If the rolled id is captured, the closest surviving lower and/or higher ids are allowed.
    """

    alive_mask = state.alive_red if player is Player.RED else state.alive_blue
    candidates: List[int] = []
    if alive_mask & _bit_for(dice):
        return [dice]

    lower = None
    for pid in range(dice - 1, 0, -1):
        if alive_mask & _bit_for(pid):
            lower = pid
            break
    higher = None
    for pid in range(dice + 1, 7):
        if alive_mask & _bit_for(pid):
            higher = pid
            break
    if lower is not None:
        candidates.append(lower)
    if higher is not None:
        candidates.append(higher)
    return candidates


def _directions_for(player: Player) -> Tuple[Tuple[int, int], ...]:
    return DIRECTIONS_RED if player is Player.RED else DIRECTIONS_BLUE


def _pos_for(state: GameState, player: Player):
    return state.pos_red if player is Player.RED else state.pos_blue


def _alive_for(state: GameState, player: Player) -> int:
    return state.alive_red if player is Player.RED else state.alive_blue


def generate_legal_moves(state: GameState, dice: int) -> List[Move]:
    """Generate all legal one-step moves for the current player given a dice roll."""

    player = state.turn
    candidates = get_movable_piece_ids(state, player, dice)
    moves: List[Move] = []
    positions = _pos_for(state, player)
    for pid in sorted(candidates):
        current = positions.get(pid)
        if current is None:
            continue
        r, c = current
        for dr, dc in _directions_for(player):
            nr, nc = r + dr, c + dc
            if 0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE:
                moves.append(Move(piece_id=pid, from_rc=current, to_rc=(nr, nc)))
    return moves


def _capture(state: GameState, coord: Tuple[int, int]) -> None:
    r, c = coord
    occupant = state.board[r][c]
    if occupant == 0:
        return
    target_player = Player.RED if occupant > 0 else Player.BLUE
    piece_id = abs(occupant)
    if target_player is Player.RED:
        state.pos_red[piece_id] = None
        state.alive_red &= ~_bit_for(piece_id)
    else:
        state.pos_blue[piece_id] = None
        state.alive_blue &= ~_bit_for(piece_id)
    state.board[r][c] = 0
    state._key_cache = None


def apply_move(state: GameState, move: Move) -> GameState:
    """Apply a move and return the resulting state."""

    player = state.turn
    next_state = state.clone()
    r_from, c_from = move.from_rc
    r_to, c_to = move.to_rc

    # Remove moving piece from origin.
    next_state.board[r_from][c_from] = 0

    positions = _pos_for(next_state, player)
    positions[move.piece_id] = move.to_rc

    # Capture if needed.
    _capture(next_state, move.to_rc)

    # Place moving piece.
    sign = move.piece_id if player is Player.RED else -move.piece_id
    next_state.board[r_to][c_to] = sign

    next_state.turn = player.opponent()
    next_state._key_cache = None
    return next_state


@dataclass
class UndoRecord:
    """Information needed to undo an in-place move."""

    prev_turn: Player
    move: Move
    from_value: int
    to_value: int
    moved_prev_pos: Tuple[int, int]
    captured_player: Player | None
    captured_piece_id: int | None
    captured_prev_pos: Tuple[int, int] | None
    alive_red: int
    alive_blue: int
    key_cache: Tuple | None


def apply_move_inplace(state: GameState, move: Move) -> UndoRecord:
    """Apply a move by mutating the state, returning data required for undo."""

    player = state.turn
    from_r, from_c = move.from_rc
    to_r, to_c = move.to_rc
    from_value = state.board[from_r][from_c]
    to_value = state.board[to_r][to_c]
    positions = _pos_for(state, player)
    moved_prev_pos = positions[move.piece_id]

    alive_red_prev = state.alive_red
    alive_blue_prev = state.alive_blue
    captured_player = None
    captured_piece_id = None
    captured_prev_pos = None
    if to_value != 0:
        captured_player = Player.RED if to_value > 0 else Player.BLUE
        captured_piece_id = abs(to_value)
        if captured_player is Player.RED:
            captured_prev_pos = state.pos_red[captured_piece_id]
            state.pos_red[captured_piece_id] = None
            state.alive_red &= ~_bit_for(captured_piece_id)
        else:
            captured_prev_pos = state.pos_blue[captured_piece_id]
            state.pos_blue[captured_piece_id] = None
            state.alive_blue &= ~_bit_for(captured_piece_id)

    positions[move.piece_id] = move.to_rc

    state.board[from_r][from_c] = 0
    state.board[to_r][to_c] = from_value
    state.turn = player.opponent()
    prev_key = state._key_cache
    state._key_cache = None

    return UndoRecord(
        prev_turn=player,
        move=move,
        from_value=from_value,
        to_value=to_value,
        moved_prev_pos=moved_prev_pos,
        captured_player=captured_player,
        captured_piece_id=captured_piece_id,
        captured_prev_pos=captured_prev_pos,
        alive_red=alive_red_prev,
        alive_blue=alive_blue_prev,
        key_cache=prev_key,
    )


def undo_move_inplace(state: GameState, undo: UndoRecord) -> None:
    """Revert a prior call to :func:`apply_move_inplace`."""

    move = undo.move
    from_r, from_c = move.from_rc
    to_r, to_c = move.to_rc

    state.turn = undo.prev_turn
    state.alive_red = undo.alive_red
    state.alive_blue = undo.alive_blue

    # Restore positions.
    mover_positions = _pos_for(state, undo.prev_turn)
    mover_positions[move.piece_id] = undo.moved_prev_pos

    if undo.captured_player is not None and undo.captured_piece_id is not None:
        captured_positions = state.pos_red if undo.captured_player is Player.RED else state.pos_blue
        captured_positions[undo.captured_piece_id] = undo.captured_prev_pos

    # Restore board cells.
    state.board[from_r][from_c] = undo.from_value
    state.board[to_r][to_c] = undo.to_value

    state._key_cache = undo.key_cache


def winner(state: GameState) -> Player | None:
    """Return the winner if the game is terminal."""

    r_goal_r, r_goal_c = TARGET_RED
    b_goal_r, b_goal_c = TARGET_BLUE

    if state.board[r_goal_r][r_goal_c] > 0 or state.alive_blue == 0:
        return Player.RED
    if state.board[b_goal_r][b_goal_c] < 0 or state.alive_red == 0:
        return Player.BLUE
    return None


def is_terminal(state: GameState) -> bool:
    """Whether the state represents a finished game."""

    return winner(state) is not None
