"""Core data structures for Einstein WTN.

Rule reminders (see AGENTS.md):
- Board is 5x5 with coordinates (r, c) from top-left.
- Red moves toward (4,4); Blue moves toward (0,0).
- Capturing any piece on the destination is allowed, including friendly fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


Coord = Tuple[int, int]


class Player(Enum):
    """Players in the game."""

    RED = auto()
    BLUE = auto()

    def opponent(self) -> "Player":
        """Return the opposing player."""

        return Player.RED if self is Player.BLUE else Player.BLUE


@dataclass(frozen=True)
class Move:
    """A single step move for a piece."""

    piece_id: int
    from_rc: Coord
    to_rc: Coord


@dataclass
class GameState:
    """Complete game state for Einstein WTN.

    The board is a 5x5 matrix of ints: 0 for empty, +k for Red piece k, -k for Blue piece k.
    Position dictionaries map piece ids to their coordinates or ``None`` if captured.
    Alive masks are six-bit integers (bit 0 for id 1, ... bit 5 for id 6).
    """

    board: List[List[int]]
    pos_red: Dict[int, Optional[Coord]]
    pos_blue: Dict[int, Optional[Coord]]
    alive_red: int
    alive_blue: int
    turn: Player
    _key_cache: Optional[Tuple] = field(default=None, init=False, repr=False, compare=False)

    def clone(self) -> "GameState":
        """Return a deep copy of the state."""

        clone_state = GameState(
            board=[row[:] for row in self.board],
            pos_red={k: v for k, v in self.pos_red.items()},
            pos_blue={k: v for k, v in self.pos_blue.items()},
            alive_red=self.alive_red,
            alive_blue=self.alive_blue,
            turn=self.turn,
        )
        clone_state._key_cache = None if self._key_cache is None else self._key_cache
        return clone_state

    def key(self) -> Tuple:
        """Return a hashable key capturing board layout and turn."""

        if self._key_cache is None:
            flattened = tuple(cell for row in self.board for cell in row)
            self._key_cache = (self.turn, flattened, self.alive_red, self.alive_blue)
        return self._key_cache
