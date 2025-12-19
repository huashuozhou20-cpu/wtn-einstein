"""Utilities for parsing user-entered WTN move snippets."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .wtn_format import sq_to_rc


@dataclass
class ParsedInputMove:
    """Result of parsing a user-supplied move string."""

    color: str
    piece_id: int
    to_r: int
    to_c: int
    dice: Optional[int]


def parse_move_text(raw: str) -> ParsedInputMove:
    """Parse a move string supporting several WTN-inspired shortcuts.

    Accepted examples (case-insensitive):
    - "12:5;(B3,D2)"  # full WTN line with ply + dice
    - "5;(B3,D2)"     # dice present, no ply
    - "(B3,D2)"       # piece + square only
    - "B3,D2" or "B3 D2"  # comma or space separated

    Raises:
        ValueError: if the text cannot be parsed or contains invalid fields.
    """

    text = raw.strip().upper()
    if not text:
        raise ValueError("Move text is empty")

    # Primary pattern covers optional ply, optional dice, and optional parentheses.
    pattern = r"^(?:(?P<ply>\d+):)?(?:(?P<dice>\d+);)?\(?([RB])([1-6])\s*,\s*([A-E][1-5])\)?$"
    match = re.match(pattern, text)
    if not match:
        # Fallback: allow whitespace instead of a comma between piece and square.
        fallback = r"^(?:(?P<ply>\d+):)?(?:(?P<dice>\d+);)?\(?([RB])([1-6])\s+([A-E][1-5])\)?$"
        match = re.match(fallback, text)
    if not match:
        raise ValueError("Could not parse move; use formats like 'B3,D2' or '5;(R5,C3)'")

    dice = match.group("dice")
    parsed_dice: Optional[int] = None
    if dice is not None:
        parsed_dice = int(dice)
        if not 1 <= parsed_dice <= 6:
            raise ValueError("Dice must be between 1 and 6")

    color = match.group(3)
    piece_id = int(match.group(4))
    dest_sq = match.group(5)

    if piece_id < 1 or piece_id > 6:
        raise ValueError("Piece id must be between 1 and 6")

    to_r, to_c = sq_to_rc(dest_sq)
    return ParsedInputMove(color=color, piece_id=piece_id, to_r=to_r, to_c=to_c, dice=parsed_dice)
