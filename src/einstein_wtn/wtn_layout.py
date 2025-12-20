"""Helpers for parsing and validating custom WTN opening layouts."""
from __future__ import annotations

from typing import Dict, Tuple

from . import engine
from .wtn_format import sq_to_rc

START_ZONES = {
    "R": set(engine.START_RED_CELLS),
    "B": set(engine.START_BLUE_CELLS),
}


def _validate_color_prefix(raw: str) -> tuple[str, str]:
    stripped = raw.strip()
    if not stripped:
        raise ValueError("Layout line is empty")
    if ":" not in stripped:
        raise ValueError("Layout line must start with 'R:' or 'B:'")
    prefix, body = stripped.split(":", 1)
    color = prefix.strip().upper()
    if color not in {"R", "B"}:
        raise ValueError("Layout line must start with 'R:' or 'B:'")
    return color, body


def parse_layout_line(line: str) -> tuple[str, Dict[int, Tuple[int, int]]]:
    """Parse a layout line such as ``R:A1-1;B1-2;C1-3;A2-4;B2-5;A3-6``.

    Returns a tuple ``(color, mapping)`` where ``color`` is ``"R"`` or ``"B"``
    and ``mapping`` maps each piece id (1..6) to an (r, c) coordinate tuple.
    The mapping must place each id exactly once inside the respective start zone.
    """

    color, body = _validate_color_prefix(line)
    allowed_cells = START_ZONES[color]

    entries = [part.strip() for part in body.split(";") if part.strip()]
    if len(entries) != 6:
        raise ValueError(f"{color} layout must contain exactly 6 entries")

    layout: Dict[int, Tuple[int, int]] = {}
    used_cells = set()
    for entry in entries:
        if "-" not in entry:
            raise ValueError(f"Invalid layout entry '{entry}'")
        sq_part, pid_part = entry.split("-", 1)
        sq = sq_part.strip()
        try:
            coord = sq_to_rc(sq)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        try:
            piece_id = int(pid_part.strip())
        except ValueError as exc:
            raise ValueError("piece_id must be between 1 and 6") from exc
        if not 1 <= piece_id <= 6:
            raise ValueError("piece_id must be between 1 and 6")
        if coord not in allowed_cells:
            raise ValueError(f"Cell {sq} not in {color} start zone")
        if piece_id in layout:
            raise ValueError(f"Duplicate piece_id {piece_id} in {color} layout")
        if coord in used_cells:
            raise ValueError(f"Cell {sq} used more than once")
        layout[piece_id] = coord
        used_cells.add(coord)

    missing = [pid for pid in range(1, 7) if pid not in layout]
    if missing:
        raise ValueError(f"{color} layout missing piece_ids: {missing}")

    return color, layout
