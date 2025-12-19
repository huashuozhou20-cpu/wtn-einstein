"""WTN notation parsing and serialization.

This module supports reading and writing the simple text-based WTN game notation
used for recording layouts and move sequences.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

COLUMNS = "ABCDE"
ROWS = "12345"


def rc_to_sq(r: int, c: int) -> str:
    """Convert 0-based row/col to WTN square string (e.g., 0,0 -> "A1")."""

    if not (0 <= r < len(ROWS) and 0 <= c < len(COLUMNS)):
        raise ValueError(f"row/col out of bounds: {(r, c)}")
    return f"{COLUMNS[c]}{ROWS[r]}"


def sq_to_rc(sq: str) -> Tuple[int, int]:
    """Convert WTN square string (e.g., "C3") to 0-based row/col."""

    if not sq or len(sq) < 2:
        raise ValueError(f"Invalid square '{sq}'")
    col_char = sq[0].upper()
    row_part = sq[1:]
    if col_char not in COLUMNS:
        raise ValueError(f"Invalid column in square '{sq}'")
    if row_part not in ROWS:
        raise ValueError(f"Invalid row in square '{sq}'")
    c = COLUMNS.index(col_char)
    r = ROWS.index(row_part)
    return r, c


@dataclass
class WTNGame:
    comments: List[str]
    red_layout: Dict[int, Tuple[int, int]]
    blue_layout: Dict[int, Tuple[int, int]]
    moves: List[Tuple[int, int, str, int, int, int]]


def _parse_layout_line(line: str, color: str) -> Dict[int, Tuple[int, int]]:
    if not line.startswith(f"{color}:"):
        raise ValueError(f"Layout line must start with '{color}:'")
    body = line.split(":", 1)[1]
    entries = [part for part in body.split(";") if part]
    layout: Dict[int, Tuple[int, int]] = {}
    for entry in entries:
        if "-" not in entry:
            raise ValueError(f"Invalid layout entry '{entry}'")
        sq, piece_str = entry.split("-", 1)
        piece_id = int(piece_str)
        if not 1 <= piece_id <= 6:
            raise ValueError("piece_id must be between 1 and 6")
        coord = sq_to_rc(sq)
        if piece_id in layout:
            raise ValueError(f"duplicate piece_id {piece_id} in {color} layout")
        layout[piece_id] = coord
    if len(layout) != 6:
        raise ValueError(f"{color} layout must contain exactly 6 pieces")
    missing = {pid for pid in range(1, 7) if pid not in layout}
    if missing:
        raise ValueError(f"{color} layout missing piece_ids: {sorted(missing)}")
    return layout


def _parse_move_line(line: str) -> Tuple[int, int, str, int, int, int]:
    if ":" not in line or ";" not in line:
        raise ValueError(f"Invalid move line '{line}'")
    ply_str, rest = line.split(":", 1)
    dice_str, move_part = rest.split(";", 1)
    ply = int(ply_str)
    dice = int(dice_str)
    move_part = move_part.strip()
    if not move_part.startswith("(") or not move_part.endswith(")"):
        raise ValueError(f"Invalid move tuple '{move_part}'")
    inside = move_part[1:-1]
    if "," not in inside:
        raise ValueError(f"Invalid move payload '{inside}'")
    piece_part, coord_part = inside.split(",", 1)
    if not piece_part:
        raise ValueError(f"Invalid piece segment '{piece_part}'")
    color = piece_part[0].upper()
    if color not in {"R", "B"}:
        raise ValueError(f"Invalid color '{color}'")
    piece_id = int(piece_part[1:])
    if not 1 <= piece_id <= 6:
        raise ValueError("piece_id must be between 1 and 6")
    to_r, to_c = sq_to_rc(coord_part.strip())
    if not 1 <= dice <= 6:
        raise ValueError("dice must be between 1 and 6")
    return ply, dice, color, piece_id, to_r, to_c


def parse_wtn(text: str) -> WTNGame:
    """Parse WTN text into a structured ``WTNGame``."""

    comments: List[str] = []
    red_layout: Dict[int, Tuple[int, int]] | None = None
    blue_layout: Dict[int, Tuple[int, int]] | None = None
    moves: List[Tuple[int, int, str, int, int, int]] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            comments.append(line)
            continue
        if stripped.startswith("R:"):
            red_layout = _parse_layout_line(stripped, "R")
            continue
        if stripped.startswith("B:"):
            blue_layout = _parse_layout_line(stripped, "B")
            continue
        ply, dice, color, pid, to_r, to_c = _parse_move_line(stripped)
        moves.append((ply, dice, color, pid, to_r, to_c))

    if red_layout is None or blue_layout is None:
        raise ValueError("Missing R: or B: layout lines")

    return WTNGame(comments=comments, red_layout=red_layout, blue_layout=blue_layout, moves=moves)


def _dump_layout(layout: Dict[int, Tuple[int, int]], color: str) -> str:
    parts: List[str] = []
    for pid in sorted(layout):
        r, c = layout[pid]
        parts.append(f"{rc_to_sq(r, c)}-{pid}")
    return f"{color}:{';'.join(parts)}"


def dump_wtn(game: WTNGame) -> str:
    """Serialize a ``WTNGame`` to text."""

    lines: List[str] = []
    lines.extend(game.comments)
    lines.append(_dump_layout(game.red_layout, "R"))
    lines.append(_dump_layout(game.blue_layout, "B"))
    for ply, dice, color, pid, to_r, to_c in game.moves:
        lines.append(f"{ply}:{dice};({color}{pid},{rc_to_sq(to_r, to_c)})")
    return "\n".join(lines) + "\n"
