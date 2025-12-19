"""Game controller utilities for UI-driven or scripted play.

This module keeps UI concerns separate from core game logic so the
underlying sequencing and validation can be tested without driving a GUI.
"""
from __future__ import annotations

import random
from typing import List, Optional, Sequence, Set, Tuple

from . import engine
from .agents import HeuristicAgent
from .runner import arrangement_to_layout, parse_layout_string
from .types import GameState, Move, Player
from .wtn_format import WTNGame, dump_wtn
from .wtn_input import parse_move_text


class GameController:
    """Manage a single Einstein WTN game, including dice, agents, and history."""

    def __init__(
        self,
        red_agent,
        blue_agent,
        red_layout: Optional[Sequence[int]] = None,
        blue_layout: Optional[Sequence[int]] = None,
        first: Player = Player.RED,
    ) -> None:
        self.red_agent = red_agent
        self.blue_agent = blue_agent
        self._initial_turn = first
        self._red_layout_order: List[int] = []
        self._blue_layout_order: List[int] = []
        self.red_layout_coords: List[Tuple[int, int]] = []
        self.blue_layout_coords: List[Tuple[int, int]] = []
        self.state: GameState
        self.dice: Optional[int] = None
        self.history: List[Tuple[int, Move]]
        self.new_game(red_layout=red_layout, blue_layout=blue_layout, first=first)

    def new_game(
        self,
        red_layout: Optional[Sequence[int]] = None,
        blue_layout: Optional[Sequence[int]] = None,
        first: Optional[Player] = None,
    ) -> None:
        """Start a new game with optional provided layout permutations."""

        self._initial_turn = self._initial_turn if first is None else first
        self._red_layout_order = self._select_order(
            red_layout, self.red_agent, default_order=[1, 2, 3, 4, 5, 6]
        )
        self._blue_layout_order = self._select_order(
            blue_layout, self.blue_agent, default_order=[1, 2, 3, 4, 5, 6]
        )
        self.red_layout_coords = arrangement_to_layout(
            self._red_layout_order, engine.START_RED_CELLS
        )
        self.blue_layout_coords = arrangement_to_layout(
            self._blue_layout_order, engine.START_BLUE_CELLS
        )
        self.state = engine.new_game(
            self.red_layout_coords, self.blue_layout_coords, first=self._initial_turn
        )
        self.history = []
        self.dice = None

    def _select_order(self, provided: Optional[Sequence[int]], agent, default_order: Sequence[int]) -> List[int]:
        if provided is not None:
            order = list(provided)
        elif agent is not None:
            order = agent.choose_initial_layout(self._agent_player(agent))
        else:
            order = list(default_order)
        if len(order) != 6 or sorted(order) != [1, 2, 3, 4, 5, 6]:
            raise ValueError("Layout must list each id 1..6 exactly once")
        return order

    def _agent_player(self, agent) -> Player:
        return Player.RED if agent is self.red_agent else Player.BLUE

    def set_dice(self, value: int) -> None:
        if not 1 <= value <= 6:
            raise ValueError("dice must be between 1 and 6")
        self.dice = value

    def roll_dice(self, rng: Optional[random.Random] = None) -> int:
        generator = rng or random.Random()
        value = generator.randint(1, 6)
        self.dice = value
        return value

    def legal_moves(self) -> List[Move]:
        if self.dice is None:
            raise ValueError("dice not set")
        return engine.generate_legal_moves(self.state, self.dice)

    def legal_destinations_for_piece(self, piece_id: int) -> Set[Tuple[int, int]]:
        """Return destination coordinates for the given piece under the current dice."""

        if self.dice is None:
            raise ValueError("dice not set")
        return {mv.to_rc for mv in self.legal_moves() if mv.piece_id == piece_id}

    def apply_human_move(self, move: Move) -> GameState:
        if self.dice is None:
            raise ValueError("dice not set")
        legal = self.legal_moves()
        if move not in legal:
            raise ValueError("illegal move")
        return self._apply_move(move)

    def apply_text_move(self, raw: str) -> Move:
        """Parse and apply a move string against the current state and dice."""

        parsed = parse_move_text(raw)
        if self.dice is None:
            raise ValueError("dice not set")
        expected_color = "R" if self.state.turn is Player.RED else "B"
        if parsed.color != expected_color:
            raise ValueError("Wrong color to move")
        if parsed.dice is not None and parsed.dice != self.dice:
            raise ValueError("Dice in text does not match current dice")

        legal = self.legal_moves()
        target = None
        for mv in legal:
            if mv.piece_id == parsed.piece_id and mv.to_rc == (parsed.to_r, parsed.to_c):
                target = mv
                break
        if target is None:
            raise ValueError("Move is not legal for current dice")
        self._apply_move(target)
        return target

    def _apply_move(self, move: Move) -> GameState:
        applied = engine.apply_move(self.state, move)
        if self.dice is None:
            raise ValueError("dice not set")
        self.history.append((self.dice, move))
        self.state = applied
        self.dice = None
        return applied

    def _current_agent(self):
        return self.red_agent if self.state.turn is Player.RED else self.blue_agent

    def compute_ai_move(self, time_budget_ms: Optional[int] = None) -> Move:
        if self.dice is None:
            raise ValueError("dice not set")
        agent = self._current_agent()
        if agent is None:
            raise ValueError("No agent configured for current player")
        try:
            move = agent.choose_move(self.state, self.dice, time_budget_ms=time_budget_ms)
        except Exception:
            fallback = HeuristicAgent()
            move = fallback.choose_move(self.state, self.dice, time_budget_ms=time_budget_ms)
        if move not in self.legal_moves():
            fallback = HeuristicAgent()
            move = fallback.choose_move(self.state, self.dice, time_budget_ms=time_budget_ms)
        return move

    def step_ai(self, time_budget_ms: Optional[int] = None) -> Move:
        move = self.compute_ai_move(time_budget_ms=time_budget_ms)
        self._apply_move(move)
        return move

    def to_wtn(self) -> str:
        """Serialize the current game to WTN text."""

        red_layout_dict = {pid: coord for pid, coord in enumerate(self.red_layout_coords, start=1)}
        blue_layout_dict = {pid: coord for pid, coord in enumerate(self.blue_layout_coords, start=1)}
        moves_payload = []
        turn = self._initial_turn
        for idx, (dice, move) in enumerate(self.history, start=1):
            color = "R" if turn is Player.RED else "B"
            to_r, to_c = move.to_rc
            moves_payload.append((idx, dice, color, move.piece_id, to_r, to_c))
            turn = turn.opponent()
        comments = [
            f"# red_agent={self.red_agent.__class__.__name__ if self.red_agent else 'Human'}",
            f"# blue_agent={self.blue_agent.__class__.__name__ if self.blue_agent else 'Human'}",
        ]
        game = WTNGame(
            comments=comments,
            red_layout=red_layout_dict,
            blue_layout=blue_layout_dict,
            moves=moves_payload,
        )
        return dump_wtn(game)

    @staticmethod
    def parse_layout_override(raw: str) -> List[int]:
        return parse_layout_string(raw)
