"""Tkinter interface for human play, move entry, and AI advice."""
from __future__ import annotations

import random
import time
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from typing import List, Optional, Tuple

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent
from .game_controller import GameController
from .types import Move, Player

AGENT_CHOICES = [
    ("human", None),
    ("opening-expecti", OpeningExpectiAgent),
    ("expecti", ExpectiminimaxAgent),
    ("heuristic", HeuristicAgent),
    ("random", RandomAgent),
]


class EinsteinTkApp:
    """Simple Tkinter UI supporting play and move advising."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Einstein WTN - Human vs AI")

        self.agent_var_red = tk.StringVar(value="human")
        self.agent_var_blue = tk.StringVar(value="expecti")
        self.mode_var = tk.StringVar(value="play")
        self.auto_apply_var = tk.BooleanVar(value=True)
        self.dice_var = tk.StringVar(value="-")

        self.red_layout_entry = tk.Entry(self.root)
        self.red_layout_entry.insert(0, "1,2,3,4,5,6")
        self.blue_layout_entry = tk.Entry(self.root)
        self.blue_layout_entry.insert(0, "")

        self.turn_label = tk.Label(self.root, text="Turn: RED")
        self.dice_label = tk.Label(self.root, text="Dice: -")

        self.board_buttons: List[List[tk.Button]] = []
        self.selected: Optional[Tuple[int, int]] = None

        self.log_text = tk.Text(self.root, height=12, width=40, state=tk.DISABLED)

        self.controller = self._build_controller()
        self._layout_widgets()
        self._refresh_board()

    def _build_controller(self) -> GameController:
        red_agent = self._build_agent(self.agent_var_red.get())
        blue_agent = self._build_agent(self.agent_var_blue.get())
        red_layout = self._parse_layout_entry(self.red_layout_entry.get())
        blue_layout = self._parse_layout_entry(self.blue_layout_entry.get())
        return GameController(
            red_agent=red_agent,
            blue_agent=blue_agent,
            red_layout=red_layout,
            blue_layout=blue_layout,
        )

    def _parse_layout_entry(self, raw: str) -> Optional[List[int]]:
        stripped = raw.strip()
        if not stripped:
            return None
        return GameController.parse_layout_override(stripped)

    def _build_agent(self, name: str):
        for label, cls in AGENT_CHOICES:
            if label == name:
                return cls(seed=None) if cls is not None else None
        raise ValueError(f"Unknown agent '{name}'")

    def _layout_widgets(self) -> None:
        control_frame = tk.Frame(self.root)
        control_frame.grid(row=0, column=1, sticky="nw", padx=10, pady=10)

        tk.Label(control_frame, text="Mode:").grid(row=0, column=0, sticky="w")
        mode_menu = tk.OptionMenu(control_frame, self.mode_var, "play", "advise")
        mode_menu.grid(row=0, column=1, sticky="w")

        tk.Label(control_frame, text="Auto apply advice").grid(row=1, column=0, sticky="w")
        tk.Checkbutton(control_frame, variable=self.auto_apply_var).grid(row=1, column=1, sticky="w")

        tk.Label(control_frame, text="Red agent").grid(row=2, column=0, sticky="w")
        tk.OptionMenu(
            control_frame,
            self.agent_var_red,
            *[label for label, _ in AGENT_CHOICES],
            command=lambda _: self._on_agents_changed(),
        ).grid(row=2, column=1, sticky="w")

        tk.Label(control_frame, text="Blue agent").grid(row=3, column=0, sticky="w")
        tk.OptionMenu(
            control_frame,
            self.agent_var_blue,
            *[label for label, _ in AGENT_CHOICES],
            command=lambda _: self._on_agents_changed(),
        ).grid(row=3, column=1, sticky="w")

        tk.Label(control_frame, text="Red layout (optional)").grid(row=4, column=0, sticky="w")
        self.red_layout_entry.grid(row=4, column=1, sticky="w")
        tk.Label(control_frame, text="Blue layout (optional)").grid(row=5, column=0, sticky="w")
        self.blue_layout_entry.grid(row=5, column=1, sticky="w")

        tk.Button(control_frame, text="New Game", command=self._on_new_game).grid(
            row=6, column=0, pady=4, sticky="we", columnspan=2
        )

        tk.Button(control_frame, text="Roll dice", command=self._on_roll_dice).grid(
            row=7, column=0, sticky="we", columnspan=2
        )
        tk.Label(control_frame, text="Set dice:").grid(row=8, column=0, sticky="w")
        self.dice_entry = tk.Entry(control_frame, width=5)
        self.dice_entry.grid(row=8, column=1, sticky="w")
        tk.Button(control_frame, text="Apply", command=self._on_set_dice).grid(
            row=9, column=0, sticky="we", columnspan=2
        )

        tk.Button(control_frame, text="AI / Advise move", command=self._on_ai_move).grid(
            row=10, column=0, columnspan=2, sticky="we", pady=4
        )
        tk.Button(control_frame, text="Save WTN", command=self._on_save_wtn).grid(
            row=11, column=0, columnspan=2, sticky="we"
        )

        self.turn_label.grid(row=1, column=1, sticky="w")
        self.dice_label.grid(row=2, column=1, sticky="w")

        board_frame = tk.Frame(self.root)
        board_frame.grid(row=0, column=0, rowspan=12, padx=10, pady=10)
        for r in range(engine.BOARD_SIZE):
            row_buttons: List[tk.Button] = []
            for c in range(engine.BOARD_SIZE):
                btn = tk.Button(
                    board_frame,
                    text="",
                    width=4,
                    height=2,
                    command=lambda rr=r, cc=c: self._on_square_click(rr, cc),
                )
                btn.grid(row=r, column=c)
                row_buttons.append(btn)
            self.board_buttons.append(row_buttons)

        log_frame = tk.Frame(self.root)
        log_frame.grid(row=12, column=0, columnspan=2, pady=8, padx=10, sticky="we")
        tk.Label(log_frame, text="Move log").pack(anchor="w")
        self.log_text.pack(in_=log_frame, fill="both", expand=True)

    def _on_agents_changed(self) -> None:
        self._log("Agents changed; start a new game to apply.")

    def _on_new_game(self) -> None:
        try:
            self.controller = self._build_controller()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to start game: {exc}")
            return
        self.selected = None
        self._refresh_board()
        self._log("New game started")

    def _on_roll_dice(self) -> None:
        value = self.controller.roll_dice(random.Random())
        self._update_dice(value)

    def _on_set_dice(self) -> None:
        raw = self.dice_entry.get().strip()
        if not raw:
            return
        try:
            value = int(raw)
            self.controller.set_dice(value)
            self._update_dice(value)
        except Exception as exc:
            messagebox.showerror("Error", f"Invalid dice: {exc}")

    def _on_ai_move(self) -> None:
        if self.controller.dice is None:
            messagebox.showinfo("Dice required", "Set or roll the dice before asking for a move.")
            return
        agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
        apply_move = self.mode_var.get() == "play" or self.auto_apply_var.get()
        if agent is None:
            messagebox.showinfo("Human turn", "Current player is human; pick a move on the board.")
            return
        move = self.controller.compute_ai_move(time_budget_ms=200)
        if apply_move:
            self.controller._apply_move(move)
            self._after_move(move)
        else:
            self._log(f"Advised move: {self._format_move(move)}")

    def _on_save_wtn(self) -> None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        default_name = f"einstein-{timestamp}.wtn.txt"
        path = filedialog.asksaveasfilename(  # type: ignore[attr-defined]
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("WTN files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        text = self.controller.to_wtn()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self._log(f"Saved WTN to {path}")

    def _on_square_click(self, r: int, c: int) -> None:
        if self.controller.dice is None:
            messagebox.showinfo("Dice required", "Roll or set dice before moving.")
            return
        cell_value = self.controller.state.board[r][c]
        turn = self.controller.state.turn
        if self.selected is None:
            if (turn is Player.RED and cell_value <= 0) or (turn is Player.BLUE and cell_value >= 0):
                return
            agent = self.controller.red_agent if turn is Player.RED else self.controller.blue_agent
            if agent is not None and self.mode_var.get() == "play":
                return
            self.selected = (r, c)
            self._highlight_selection()
            return

        move = self._find_move(self.selected, (r, c))
        if move is None:
            self.selected = None
            self._highlight_selection()
            return
        try:
            self.controller.apply_human_move(move)
            self._after_move(move)
        except Exception as exc:
            messagebox.showerror("Error", f"Illegal move: {exc}")
        finally:
            self.selected = None
            self._highlight_selection()

    def _after_move(self, move: Move) -> None:
        self._log(self._format_move(move))
        self._refresh_board()
        self._update_turn()
        if engine.is_terminal(self.controller.state):
            win = engine.winner(self.controller.state)
            messagebox.showinfo("Game over", f"Winner: {win.name if win else 'Unknown'}")
            return
        self._maybe_auto_step_ai()

    def _maybe_auto_step_ai(self) -> None:
        turn_agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
        if turn_agent is None:
            return
        if self.controller.dice is None:
            return
        if self.mode_var.get() == "play" or self.auto_apply_var.get():
            move = self.controller.step_ai(time_budget_ms=200)
            self._after_move(move)
        else:
            move = self.controller.compute_ai_move(time_budget_ms=200)
            self._log(f"Advised move: {self._format_move(move)}")

    def _find_move(self, from_rc: Tuple[int, int], to_rc: Tuple[int, int]) -> Optional[Move]:
        try:
            moves = self.controller.legal_moves()
        except Exception:
            return None
        for mv in moves:
            if mv.from_rc == from_rc and mv.to_rc == to_rc:
                return mv
        return None

    def _highlight_selection(self) -> None:
        for r, row in enumerate(self.board_buttons):
            for c, btn in enumerate(row):
                if self.selected == (r, c):
                    btn.config(relief=tk.SUNKEN)
                else:
                    btn.config(relief=tk.RAISED)

    def _refresh_board(self) -> None:
        for r in range(engine.BOARD_SIZE):
            for c in range(engine.BOARD_SIZE):
                val = self.controller.state.board[r][c]
                text = ""
                if val > 0:
                    text = f"R{val}"
                elif val < 0:
                    text = f"B{abs(val)}"
                self.board_buttons[r][c].config(text=text)
        self._update_turn()

    def _update_turn(self) -> None:
        self.turn_label.config(text=f"Turn: {self.controller.state.turn.name}")

    def _update_dice(self, value: int) -> None:
        self.dice_var.set(str(value))
        self.dice_label.config(text=f"Dice: {value}")

    def _format_move(self, move: Move) -> str:
        from_r, from_c = move.from_rc
        to_r, to_c = move.to_rc
        dice_value = self.controller.history[-1][0] if self.controller.history else self.controller.dice
        mover = self.controller.state.turn.opponent() if self.controller.history else self.controller._initial_turn
        return f"{mover.name} dice={dice_value}: {move.piece_id} ({from_r},{from_c})->({to_r},{to_c})"

    def _log(self, msg: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = EinsteinTkApp()
    app.run()


if __name__ == "__main__":
    main()
