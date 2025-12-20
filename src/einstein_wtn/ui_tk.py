"""Tkinter interface for human play, move entry, and AI advice."""
from __future__ import annotations

import argparse
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
from typing import List, Optional, Set, Tuple

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent
from .game_controller import GameController
from .i18n import available_langs, t
from .types import Move, Player
from .wtn_format import rc_to_sq

AGENT_CHOICES = [
    ("human", None),
    ("opening-expecti", OpeningExpectiAgent),
    ("expecti", ExpectiminimaxAgent),
    ("heuristic", HeuristicAgent),
    ("random", RandomAgent),
]

CELL_COLORS = {
    "empty": "#f5f5f5",
    "red": "#fce4ec",
    "blue": "#e3f2fd",
    "red_border": "#c62828",
    "blue_border": "#1565c0",
    "highlight": "#ffb74d",
    "legal": "#81c784",
}

FONT_CANDIDATES = [
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "WenQuanYi Micro Hei",
    "Microsoft YaHei",
    "DejaVu Sans",
]
CJK_FONT_CANDIDATES = FONT_CANDIDATES[:-1]


class EinsteinTkApp:
    """Tkinter UI supporting play and move advising with bilingual text."""

    def __init__(self, lang: str = "zh") -> None:
        self.lang = lang if lang in available_langs() else "zh"

        self.root = tk.Tk()
        self.root.title(t("window_title", self.lang))
        font_family, has_cjk_font, base_size = self._configure_fonts()
        self.has_cjk_font = has_cjk_font
        piece_font = (font_family, base_size + 5, "bold")

        self.agent_var_red = tk.StringVar(value="human")
        self.agent_var_blue = tk.StringVar(value="expecti")
        self.mode_var = tk.StringVar(value="play")
        self.lang_var = tk.StringVar(value=self.lang)
        self.auto_apply_var = tk.BooleanVar(value=True)
        self.dice_var = tk.StringVar(value="-")
        self.status_var = tk.StringVar(value="")
        self._status_state = {"key": None, "fmt": {}, "level": "info"}
        self.last_move_var = tk.StringVar(value=t("no_last_move", self.lang))
        self.ai_suggestion_var = tk.StringVar(value=t("no_last_move", self.lang))
        self._ai_suggestion_empty = True
        self.info_can_move_var = tk.StringVar(value="-")

        self.red_layout_entry = tk.Entry(self.root, width=24)
        self.red_layout_entry.insert(0, "1,2,3,4,5,6")
        self.blue_layout_entry = tk.Entry(self.root, width=24)
        self.blue_layout_entry.insert(0, "")

        self.turn_var = tk.StringVar(value=t("turn_label", self.lang).format(turn="RED"))

        self.board_buttons: List[List[tk.Button]] = []
        self.selected: Optional[Tuple[int, int]] = None
        self._highlighted: Set[Tuple[int, int]] = set()

        self.log_text = tk.Text(self.root, height=12, width=48, state=tk.DISABLED)
        self.log_text.configure(font=(font_family, base_size - 1))

        self.controller = self._build_controller()
        self._layout_widgets(piece_font)
        initial_status_key = "status_ready" if self.has_cjk_font else "missing_cjk_fonts"
        initial_level = "info" if self.has_cjk_font else "warning"
        self._set_status_key(initial_status_key, level=initial_level)
        self._refresh_board()

    def _configure_fonts(self) -> Tuple[str, bool, int]:
        available_fonts = set(tkfont.families(self.root))
        selected_family = next(
            (family for family in FONT_CANDIDATES if family in available_fonts),
            tkfont.nametofont("TkDefaultFont").actual().get("family", "TkDefaultFont"),
        )
        has_cjk_font = selected_family in CJK_FONT_CANDIDATES

        default_font = tkfont.nametofont("TkDefaultFont")
        base_size = default_font.actual().get("size", 11)
        tkfont.nametofont("TkDefaultFont").configure(family=selected_family, size=base_size)
        tkfont.nametofont("TkTextFont").configure(family=selected_family, size=base_size)
        tkfont.nametofont("TkFixedFont").configure(family=selected_family, size=base_size)

        style = ttk.Style(self.root)
        style.configure(".", font=(selected_family, base_size))

        return selected_family, has_cjk_font, base_size

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

    def _layout_widgets(self, piece_font) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        board_frame = ttk.Frame(main)
        self.board_frame = board_frame
        board_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        for idx in range(engine.BOARD_SIZE):
            board_frame.columnconfigure(idx, weight=1)
            board_frame.rowconfigure(idx, weight=1)
        for r in range(engine.BOARD_SIZE):
            row_buttons: List[tk.Button] = []
            for c in range(engine.BOARD_SIZE):
                btn = tk.Button(
                    board_frame,
                    text="",
                    width=6,
                    height=3,
                    font=piece_font,
                    relief=tk.RAISED,
                    command=lambda rr=r, cc=c: self._on_square_click(rr, cc),
                )
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                row_buttons.append(btn)
            self.board_buttons.append(row_buttons)

        control_frame = ttk.Frame(main, padding=(6, 0, 0, 0))
        control_frame.grid(row=0, column=1, sticky="nsew")
        control_frame.columnconfigure(0, weight=1)

        language_frame = ttk.Frame(control_frame)
        language_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        language_frame.columnconfigure(1, weight=1)
        self.language_label = ttk.Label(language_frame, text=t("language_label", self.lang))
        self.language_label.grid(row=0, column=0, sticky="w")
        self.language_combo = ttk.Combobox(
            language_frame,
            textvariable=self.lang_var,
            values=available_langs(),
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=0, column=1, padx=6, sticky="ew")
        self.language_combo.bind("<<ComboboxSelected>>", lambda _: self._on_language_changed())

        self.status_label = ttk.Label(control_frame, textvariable=self.status_var)
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        game_frame = ttk.LabelFrame(control_frame, text=t("game_group", self.lang), padding=8)
        self.game_frame = game_frame
        game_frame.grid(row=2, column=0, sticky="ew", pady=4)
        game_frame.columnconfigure((0, 1), weight=1)
        self.new_game_button = ttk.Button(game_frame, text=t("new_game", self.lang), command=self._on_new_game)
        self.new_game_button.grid(row=0, column=0, padx=6, pady=4, sticky="ew")
        self.save_wtn_button = ttk.Button(game_frame, text=t("save_wtn", self.lang), command=self._on_save_wtn)
        self.save_wtn_button.grid(row=0, column=1, padx=6, pady=4, sticky="ew")

        agents_frame = ttk.LabelFrame(control_frame, text=t("agents_group", self.lang), padding=8)
        self.agents_frame = agents_frame
        agents_frame.grid(row=3, column=0, sticky="ew", pady=4)
        agents_frame.columnconfigure(1, weight=1)
        self.red_agent_label = ttk.Label(agents_frame, text=t("red_agent", self.lang))
        self.red_agent_label.grid(row=0, column=0, sticky="w")
        ttk.OptionMenu(
            agents_frame,
            self.agent_var_red,
            self.agent_var_red.get(),
            *[label for label, _ in AGENT_CHOICES],
            command=lambda *_: self._on_agents_changed(),
        ).grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        self.blue_agent_label = ttk.Label(agents_frame, text=t("blue_agent", self.lang))
        self.blue_agent_label.grid(row=1, column=0, sticky="w")
        ttk.OptionMenu(
            agents_frame,
            self.agent_var_blue,
            self.agent_var_blue.get(),
            *[label for label, _ in AGENT_CHOICES],
            command=lambda *_: self._on_agents_changed(),
        ).grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        self.red_layout_label = ttk.Label(agents_frame, text=t("layouts_red", self.lang))
        self.red_layout_label.grid(row=2, column=0, sticky="w")
        self.red_layout_entry.grid(in_=agents_frame, row=2, column=1, sticky="ew", padx=6, pady=2)
        self.blue_layout_label = ttk.Label(agents_frame, text=t("layouts_blue", self.lang))
        self.blue_layout_label.grid(row=3, column=0, sticky="w")
        self.blue_layout_entry.grid(in_=agents_frame, row=3, column=1, sticky="ew", padx=6, pady=2)

        mode_frame = ttk.LabelFrame(control_frame, text=t("mode_group", self.lang), padding=8)
        self.mode_frame = mode_frame
        mode_frame.grid(row=4, column=0, sticky="ew", pady=4)
        mode_frame.columnconfigure((0, 1), weight=1)
        self.mode_play_radio = ttk.Radiobutton(
            mode_frame, text=t("mode_play", self.lang), variable=self.mode_var, value="play"
        )
        self.mode_play_radio.grid(row=0, column=0, sticky="w", pady=2)
        self.mode_advise_radio = ttk.Radiobutton(
            mode_frame, text=t("mode_advise", self.lang), variable=self.mode_var, value="advise"
        )
        self.mode_advise_radio.grid(row=0, column=1, sticky="w", padx=6, pady=2)
        self.auto_apply_check = ttk.Checkbutton(mode_frame, text=t("auto_apply", self.lang), variable=self.auto_apply_var)
        self.auto_apply_check.grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        dice_frame = ttk.LabelFrame(control_frame, text=t("dice_group", self.lang), padding=8)
        self.dice_frame = dice_frame
        dice_frame.grid(row=5, column=0, sticky="ew", pady=4)
        dice_frame.columnconfigure((0, 1, 2, 3), weight=1)
        self.roll_button = ttk.Button(dice_frame, text=t("roll_dice", self.lang), command=self._on_roll_dice)
        self.roll_button.grid(row=0, column=0, padx=6, pady=4, sticky="ew")
        self.set_dice_label = ttk.Label(dice_frame, text=t("set_dice", self.lang))
        self.set_dice_label.grid(row=0, column=1, sticky="e")
        self.dice_entry = ttk.Entry(dice_frame, width=10)
        self.dice_entry.grid(row=0, column=2, sticky="ew", padx=4)
        self.apply_dice_button = ttk.Button(dice_frame, text=t("apply", self.lang), command=self._on_set_dice)
        self.apply_dice_button.grid(row=0, column=3, padx=6, sticky="ew")

        input_frame = ttk.LabelFrame(control_frame, text=t("input_group", self.lang), padding=8)
        self.input_frame = input_frame
        input_frame.grid(row=6, column=0, sticky="ew", pady=4)
        input_frame.columnconfigure(0, weight=1)
        self.input_label = ttk.Label(input_frame, text=t("enter_move", self.lang))
        self.input_label.grid(row=0, column=0, sticky="w")
        self.move_text_entry = ttk.Entry(input_frame, width=24)
        self.move_text_entry.grid(row=1, column=0, sticky="ew", pady=4)
        self.move_text_entry.bind("<Return>", lambda _: self._on_text_move())
        self.apply_text_button = ttk.Button(input_frame, text=t("apply", self.lang), command=self._on_text_move)
        self.apply_text_button.grid(row=1, column=1, padx=6, pady=4, sticky="ew")

        ai_frame = ttk.LabelFrame(control_frame, text=t("ai_group", self.lang), padding=8)
        self.ai_frame = ai_frame
        ai_frame.grid(row=7, column=0, sticky="ew", pady=4)
        ai_frame.columnconfigure(0, weight=1)
        self.ai_move_button = ttk.Button(ai_frame, text=t("ai_move", self.lang), command=self._on_ai_move)
        self.ai_move_button.grid(row=0, column=0, padx=6, pady=4, sticky="ew")

        info_frame = ttk.Frame(main, padding=(0, 8, 0, 0))
        info_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(2, weight=1)

        summary_frame = ttk.Frame(info_frame)
        summary_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(summary_frame, textvariable=self.turn_var, font=("DejaVu Sans", 12, "bold")).grid(
            row=0, column=0, padx=(0, 12), sticky="w"
        )
        self.dice_label = ttk.Label(summary_frame, text=t("dice_label", self.lang).format(dice="-"))
        self.dice_label.grid(row=0, column=1, padx=(0, 12), sticky="w")
        self.can_move_label = ttk.Label(summary_frame, textvariable=self.info_can_move_var)
        self.can_move_label.grid(row=0, column=2, sticky="w")

        recent_frame = ttk.Frame(info_frame)
        recent_frame.grid(row=1, column=0, sticky="ew", pady=4)
        recent_frame.columnconfigure(1, weight=1)
        self.last_move_label = ttk.Label(recent_frame, text=t("info_last_move", self.lang))
        self.last_move_label.grid(row=0, column=0, sticky="w")
        ttk.Label(recent_frame, textvariable=self.last_move_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(recent_frame, text=t("copy_last", self.lang), command=self._on_copy_last_move).grid(
            row=0, column=2, padx=6, sticky="e"
        )
        self.ai_suggestion_label = ttk.Label(recent_frame, text=t("info_ai_suggestion", self.lang))
        self.ai_suggestion_label.grid(row=1, column=0, sticky="w")
        ttk.Label(recent_frame, textvariable=self.ai_suggestion_var).grid(row=1, column=1, sticky="ew")

        log_frame = ttk.LabelFrame(info_frame, text=t("move_log", self.lang), padding=8)
        self.log_frame = log_frame
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        log_frame.columnconfigure(0, weight=1)
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.grid(row=0, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.log_text.yview)
        self.log_text.grid(in_=log_text_frame, row=0, column=0, sticky="nsew")
        log_text_frame.columnconfigure(0, weight=1)
        log_text_frame.rowconfigure(0, weight=1)

    def _refresh_texts(self) -> None:
        self.root.title(t("window_title", self.lang))
        self.language_label.configure(text=t("language_label", self.lang))
        self.language_combo.configure(values=available_langs())
        for frame, label in [
            (self.game_frame, "game_group"),
            (self.agents_frame, "agents_group"),
            (self.mode_frame, "mode_group"),
            (self.dice_frame, "dice_group"),
            (self.input_frame, "input_group"),
            (self.ai_frame, "ai_group"),
            (self.log_frame, "move_log"),
        ]:
            frame.configure(text=t(label, self.lang))
        self.new_game_button.configure(text=t("new_game", self.lang))
        self.save_wtn_button.configure(text=t("save_wtn", self.lang))
        self.red_agent_label.configure(text=t("red_agent", self.lang))
        self.blue_agent_label.configure(text=t("blue_agent", self.lang))
        self.red_layout_label.configure(text=t("layouts_red", self.lang))
        self.blue_layout_label.configure(text=t("layouts_blue", self.lang))
        self.mode_play_radio.configure(text=t("mode_play", self.lang))
        self.mode_advise_radio.configure(text=t("mode_advise", self.lang))
        self.auto_apply_check.configure(text=t("auto_apply", self.lang))
        self.roll_button.configure(text=t("roll_dice", self.lang))
        self.set_dice_label.configure(text=t("set_dice", self.lang))
        self.apply_dice_button.configure(text=t("apply", self.lang))
        self.input_label.configure(text=t("enter_move", self.lang))
        self.apply_text_button.configure(text=t("apply", self.lang))
        self.ai_move_button.configure(text=t("ai_move", self.lang))
        self.last_move_label.configure(text=t("info_last_move", self.lang))
        self.ai_suggestion_label.configure(text=t("info_ai_suggestion", self.lang))
        self.turn_var.set(t("turn_label", self.lang).format(turn=self.controller.state.turn.name))
        self.dice_label.configure(text=t("dice_label", self.lang).format(dice=self.dice_var.get()))
        self.log_frame.configure(text=t("move_log", self.lang))
        if not self.controller.history:
            self.last_move_var.set(t("no_last_move", self.lang))
        else:
            _, move = self.controller.history[-1]
            last_mover = self.controller.state.turn.opponent()
            color_label = "R" if last_mover is Player.RED else "B"
            self.last_move_var.set(
                t("info_last_move_value", self.lang).format(
                    color=color_label, piece=move.piece_id, dest=rc_to_sq(move.to_rc[0], move.to_rc[1])
                )
            )
        if self._ai_suggestion_empty:
            self.ai_suggestion_var.set(t("no_last_move", self.lang))
        self._reapply_status()
        self._update_move_hints()

    def _on_language_changed(self) -> None:
        self.lang = self.lang_var.get()
        self._refresh_texts()
        self._refresh_board()

    def _apply_status(self, text: str, level: str) -> None:
        color_map = {
            "info": "#616161",
            "success": "#2e7d32",
            "error": "#c62828",
            "warning": "#ef6c00",
        }
        self.status_label.configure(foreground=color_map.get(level, "#616161"))
        self.status_var.set(text)

    def _set_status_key(self, key: str, level: str = "info", **fmt) -> None:
        message = t(key, self.lang).format(**fmt)
        self._status_state = {"key": key, "fmt": fmt, "level": level}
        self._apply_status(message, level)

    def _set_status_text(self, msg: str, level: str = "info") -> None:
        self._status_state = {"key": None, "fmt": {}, "level": level, "text": msg}
        self._apply_status(msg, level)

    def _reapply_status(self) -> None:
        key = self._status_state.get("key")
        level = self._status_state.get("level", "info")
        if key:
            fmt = self._status_state.get("fmt", {})
            self._apply_status(t(key, self.lang).format(**fmt), level)
        else:
            text = self._status_state.get("text") or t("status_ready", self.lang)
            self._apply_status(text, level)

    def _status_for_exception(self, exc: Exception):
        lookup = {
            "dice not set": ("status_need_dice", {}),
            "dice must be between 1 and 6": ("status_need_dice", {}),
            "wrong color to move": ("status_wrong_turn", {"turn": self.controller.state.turn.name}),
            "dice in text does not match current dice": ("status_dice_mismatch", {}),
            "move is not legal for current dice": ("status_illegal_move", {}),
            "illegal move": ("status_illegal_move", {}),
        }
        key = lookup.get(str(exc).lower())
        if key is None:
            return None
        return key

    def _on_agents_changed(self) -> None:
        self._log(t("agents_changed", self.lang))
        self._set_status_key("agents_changed")

    def _on_new_game(self) -> None:
        try:
            self.controller = self._build_controller()
        except Exception as exc:
            messagebox.showerror(t("game_over", self.lang), str(exc))
            mapped = self._status_for_exception(exc)
            if mapped:
                key, fmt = mapped
                self._set_status_key(key, level="error", **fmt)
            else:
                self._set_status_text(t("status_error_prefix", self.lang).format(msg=exc), level="error")
            return
        self.selected = None
        self._clear_highlights()
        self._refresh_board()
        self.last_move_var.set(t("no_last_move", self.lang))
        self.ai_suggestion_var.set(t("no_last_move", self.lang))
        self._ai_suggestion_empty = True
        self._set_status_key("new_game_started", level="success")
        self._log(t("new_game_started", self.lang))

    def _on_roll_dice(self) -> None:
        value = self.controller.roll_dice(random.Random())
        self._update_dice(value)
        self._clear_selection_state()
        self._update_move_hints()
        self._set_status_key("status_dice_set", level="success", value=value)

    def _on_set_dice(self) -> None:
        raw = self.dice_entry.get().strip()
        if not raw:
            return
        try:
            value = int(raw)
            self.controller.set_dice(value)
            self._update_dice(value)
        except Exception as exc:
            messagebox.showerror(t("dice_group", self.lang), t("illegal_move", self.lang).format(reason=exc))
            mapped = self._status_for_exception(exc)
            if mapped:
                key, fmt = mapped
                self._set_status_key(key, level="error", **fmt)
            else:
                self._set_status_text(t("status_error_prefix", self.lang).format(msg=exc), level="error")
            return
        self._clear_selection_state()
        self._update_move_hints()
        self._set_status_key("status_dice_set", level="success", value=value)

    def _on_text_move(self) -> None:
        text = self.move_text_entry.get().strip()
        if not text:
            return
        if engine.is_terminal(self.controller.state):
            self._log(t("game_over", self.lang))
            return
        if self._is_ai_turn():
            self._log(t("ai_turn_wait", self.lang))
            self._set_status_key("ai_turn_wait", level="warning")
            return
        if self.controller.dice is None:
            messagebox.showinfo(t("dice_group", self.lang), t("dice_needed", self.lang))
            self._set_status_key("status_need_dice", level="warning")
            return
        try:
            move = self.controller.apply_text_move(text)
        except Exception as exc:
            error = t("text_move_error", self.lang).format(error=exc)
            self._log(error)
            mapped = self._status_for_exception(exc)
            if mapped:
                key, fmt = mapped
                self._set_status_key(key, level="error", **fmt)
            else:
                self._set_status_text(t("status_error_prefix", self.lang).format(msg=exc), level="error")
            return
        finally:
            self._clear_selection_state()

        self.move_text_entry.delete(0, tk.END)
        self._after_move(move)
        self._set_status_key("status_move_applied", level="success")

    def _on_ai_move(self) -> None:
        if self.controller.dice is None:
            messagebox.showinfo(t("dice_group", self.lang), t("dice_needed", self.lang))
            self._set_status_key("status_need_dice", level="warning")
            return
        agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
        apply_move = self.mode_var.get() == "play" or self.auto_apply_var.get()
        if agent is None:
            messagebox.showinfo(t("mode_group", self.lang), t("human_turn", self.lang))
            self._set_status_key("human_turn")
            return
        move = self.controller.compute_ai_move(time_budget_ms=200)
        if apply_move:
            self.controller._apply_move(move)
            self._after_move(move)
            self._set_status_key("status_applied_advice", level="success")
        else:
            text = t("advised_move", self.lang).format(move=self._format_move(move))
            self.ai_suggestion_var.set(text)
            self._ai_suggestion_empty = False
            self._log(text)
            self._set_status_text(text)

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
        msg = t("saved_wtn", self.lang).format(path=path)
        self._log(msg)
        self._set_status_text(msg, level="success")

    def _on_copy_last_move(self) -> None:
        if not self.controller.history:
            self._set_status_key("no_last_move", level="warning")
            return
        _, move = self.controller.history[-1]
        payload = self._format_compact_move(move)
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self._set_status_key("copy_done", level="success")

    def _on_square_click(self, r: int, c: int) -> None:
        if engine.is_terminal(self.controller.state):
            self._log(t("game_over", self.lang))
            self._set_status_key("game_over", level="warning")
            return
        if self._is_ai_turn():
            self._log(t("ai_turn_wait", self.lang))
            self._set_status_key("ai_turn_wait", level="warning")
            return
        if self.controller.dice is None:
            messagebox.showinfo(t("dice_group", self.lang), t("dice_needed", self.lang))
            self._set_status_key("status_need_dice", level="warning")
            return
        cell_value = self.controller.state.board[r][c]
        turn = self.controller.state.turn
        if self.selected is None:
            if (turn is Player.RED and cell_value <= 0) or (turn is Player.BLUE and cell_value >= 0):
                self._log(t("select_own_piece", self.lang))
                self._set_status_key("select_own_piece", level="warning")
                return
            agent = self.controller.red_agent if turn is Player.RED else self.controller.blue_agent
            if agent is not None and self.mode_var.get() == "play":
                return
            try:
                destinations = self._legal_destinations_for_cell(r, c)
            except ValueError as exc:
                messagebox.showerror(t("game_group", self.lang), str(exc))
                mapped = self._status_for_exception(exc)
                if mapped:
                    key, fmt = mapped
                    self._set_status_key(key, level="error", **fmt)
                else:
                    self._set_status_text(t("status_error_prefix", self.lang).format(msg=exc), level="error")
                return
            if not destinations:
                self._log(t("piece_blocked", self.lang).format(dice=self.controller.dice))
                self._set_status_text(t("piece_blocked", self.lang).format(dice=self.controller.dice), level="warning")
                return
            self.selected = (r, c)
            self._highlight_selection(destinations, origin=(r, c))
            self._log(
                t("targets", self.lang).format(
                    targets=", ".join(sorted(rc_to_sq(dest[0], dest[1]) for dest in destinations))
                )
            )
            return

        move = self._find_move(self.selected, (r, c))
        if move is None:
            self._log(t("illegal_destination", self.lang))
            self._set_status_key("status_illegal_move", level="error")
            return
        try:
            self.controller.apply_human_move(move)
            self._after_move(move)
        except Exception as exc:
            messagebox.showerror(t("game_group", self.lang), t("illegal_move", self.lang).format(reason=exc))
            mapped = self._status_for_exception(exc)
            if mapped:
                key, fmt = mapped
                self._set_status_key(key, level="error", **fmt)
            else:
                self._set_status_text(t("status_error_prefix", self.lang).format(msg=exc), level="error")
        finally:
            self.selected = None
            self._clear_highlights()

    def _after_move(self, move: Move) -> None:
        move_text = self._format_move(move)
        last_mover = self.controller.state.turn.opponent()
        color_label = "R" if last_mover is Player.RED else "B"
        self.last_move_var.set(
            t("info_last_move_value", self.lang).format(
                color=color_label, piece=move.piece_id, dest=rc_to_sq(move.to_rc[0], move.to_rc[1])
            )
        )
        self._log(move_text)
        self._refresh_board()
        self._update_turn()
        self._clear_highlights()
        self._set_status_key("status_move_applied", level="success")
        if engine.is_terminal(self.controller.state):
            win = engine.winner(self.controller.state)
            winner_text = win.name if win else "-"
            messagebox.showinfo(t("game_over", self.lang), t("winner", self.lang).format(winner=winner_text))
            self._set_status_text(t("winner", self.lang).format(winner=winner_text), level="success")
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
            self._set_status_key("status_applied_advice", level="success")
        else:
            move = self.controller.compute_ai_move(time_budget_ms=200)
            text = t("advised_move", self.lang).format(move=self._format_move(move))
            self.ai_suggestion_var.set(text)
            self._ai_suggestion_empty = False
            self._log(text)
            self._set_status_text(text)

    def _find_move(self, from_rc: Tuple[int, int], to_rc: Tuple[int, int]) -> Optional[Move]:
        try:
            moves = self.controller.legal_moves()
        except Exception:
            return None
        for mv in moves:
            if mv.from_rc == from_rc and mv.to_rc == to_rc:
                return mv
        return None

    def _clear_selection_state(self) -> None:
        self.selected = None
        self._clear_highlights()

    def _clear_highlights(self) -> None:
        self._highlighted.clear()
        self._reapply_highlights()

    def _highlight_selection(
        self, destinations: Set[Tuple[int, int]], origin: Tuple[int, int]
    ) -> None:
        self._highlighted = set(destinations)
        self.selected = origin
        self._reapply_highlights()

    def _reapply_highlights(self) -> None:
        for r in range(engine.BOARD_SIZE):
            for c in range(engine.BOARD_SIZE):
                self._render_cell(r, c)
                btn = self.board_buttons[r][c]
                if self.selected == (r, c):
                    btn.configure(
                        relief=tk.SUNKEN,
                        highlightthickness=3,
                        highlightbackground=CELL_COLORS["highlight"],
                        highlightcolor=CELL_COLORS["highlight"],
                    )
                elif (r, c) in self._highlighted:
                    btn.configure(
                        highlightthickness=3,
                        highlightbackground=CELL_COLORS["legal"],
                        highlightcolor=CELL_COLORS["legal"],
                    )

    def _render_cell(self, r: int, c: int) -> None:
        val = self.controller.state.board[r][c]
        btn = self.board_buttons[r][c]
        text = ""
        bg = CELL_COLORS["empty"]
        fg = "#444444"
        if val > 0:
            text = f"R{val}"
            bg = CELL_COLORS["red"]
            fg = CELL_COLORS["red_border"]
        elif val < 0:
            text = f"B{abs(val)}"
            bg = CELL_COLORS["blue"]
            fg = CELL_COLORS["blue_border"]
        btn.configure(text=text, background=bg, activebackground=bg, foreground=fg, relief=tk.RAISED, highlightthickness=0)

    def _refresh_board(self) -> None:
        for r in range(engine.BOARD_SIZE):
            for c in range(engine.BOARD_SIZE):
                self._render_cell(r, c)
        self._reapply_highlights()
        self._update_turn()
        self._update_move_hints()

    def _update_turn(self) -> None:
        self.turn_var.set(t("turn_label", self.lang).format(turn=self.controller.state.turn.name))

    def _update_dice(self, value: int) -> None:
        self.dice_var.set(str(value))
        self.dice_label.config(text=t("dice_label", self.lang).format(dice=value))
        self._maybe_auto_step_ai()

    def _update_move_hints(self) -> None:
        if self.controller.dice is None:
            self.info_can_move_var.set(t("info_can_move", self.lang) + ": -")
            return
        try:
            legal = self.controller.legal_moves()
        except Exception:
            self.info_can_move_var.set(t("info_can_move", self.lang) + ": -")
            return
        pieces = sorted({mv.piece_id for mv in legal})
        if pieces:
            detail = t("you_can_move", self.lang).format(pieces=", ".join(str(p) for p in pieces))
        else:
            detail = t("info_can_move", self.lang) + ": -"
        dice_value = self.controller.dice
        if dice_value is not None and dice_value not in pieces and pieces:
            nearest = min(pieces, key=lambda p: abs(p - dice_value))
            alt = [p for p in pieces if abs(p - dice_value) == abs(nearest - dice_value)]
            detail += " | " + t("nearest_piece", self.lang).format(pieces=", ".join(str(p) for p in sorted(alt)))
        self.info_can_move_var.set(detail)

    def _last_mover(self) -> Optional[Player]:
        if not self.controller.history:
            return None
        return self.controller._initial_turn if len(self.controller.history) % 2 == 1 else self.controller._initial_turn.opponent()

    def _format_compact_move(self, move: Move) -> str:
        dest_sq = rc_to_sq(move.to_rc[0], move.to_rc[1])
        mover = self._last_mover() or self.controller.state.turn
        color_prefix = "R" if mover is Player.RED else "B"
        return f"({color_prefix}{move.piece_id},{dest_sq})"

    def _format_move(self, move: Move) -> str:
        from_r, from_c = move.from_rc
        to_r, to_c = move.to_rc
        dice_value = self.controller.history[-1][0] if self.controller.history else self.controller.dice
        mover = self.controller.state.turn.opponent() if self.controller.history else self.controller._initial_turn
        return f"{mover.name} dice={dice_value}: {move.piece_id} {rc_to_sq(from_r, from_c)}->{rc_to_sq(to_r, to_c)}"

    def _log(self, msg: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _is_ai_turn(self) -> bool:
        agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
        return agent is not None and self.mode_var.get() == "play"

    def _legal_destinations_for_cell(self, r: int, c: int) -> Set[Tuple[int, int]]:
        val = self.controller.state.board[r][c]
        if val == 0:
            return set()
        piece_id = abs(val)
        try:
            return self.controller.legal_destinations_for_piece(piece_id)
        except ValueError:
            return set()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Einstein WTN Tkinter UI")
    parser.add_argument("--lang", choices=available_langs(), default="zh")
    args = parser.parse_args()
    app = EinsteinTkApp(lang=args.lang)
    app.run()


if __name__ == "__main__":
    main()
