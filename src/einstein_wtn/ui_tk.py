"""Tkinter interface for human play, move entry, and AI advice."""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
from typing import Dict, List, Optional, Set, Tuple

from . import engine
from .agents import ExpectiminimaxAgent, HeuristicAgent, OpeningExpectiAgent, RandomAgent
from .game_controller import GameController
from .i18n import available_langs, t
from .ui_contract import CONTROL_CHILD_WIDGETS, REQUIRED_MAPPED_WIDGETS, REQUIRED_WIDGET_ATTRS
from .types import Move, Player
from .wtn_format import rc_to_sq
from .wtn_layout import parse_layout_line

PHASE_SETUP = "setup"
PHASE_NEED_DICE = "need_dice"
PHASE_NEED_MOVE = "need_move"
PHASE_GAME_OVER = "game_over"

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
        font_family, has_cjk_font, base_size = self._configure_fonts()
        self.root.title(t("window_title", self.lang))
        self._apply_initial_geometry()
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
        self.phase_var = tk.StringVar(value=t("phase_setup", self.lang))
        self.next_step_var = tk.StringVar(value=t("next_step_setup", self.lang))
        self.last_move_var = tk.StringVar(value=t("no_last_move", self.lang))
        self.ai_suggestion_var = tk.StringVar(value=t("no_last_move", self.lang))
        self._ai_suggestion_empty = True
        self.info_can_move_var = tk.StringVar(value="-")
        self._phase = PHASE_SETUP
        self._game_started = False
        self._board_block_reason: Optional[str] = None

        self.red_layout_entry = tk.Entry(self.root, width=24)
        self.red_layout_entry.insert(0, "1,2,3,4,5,6")
        self.blue_layout_entry = tk.Entry(self.root, width=24)
        self.blue_layout_entry.insert(0, "")
        self.red_layout_text = tk.Text(self.root, height=2, width=28)
        self.blue_layout_text = tk.Text(self.root, height=2, width=28)
        self.edit_mode_var = tk.BooleanVar(value=False)
        self.edit_side_var = tk.StringVar(value="R")
        self.edit_piece_var = tk.StringVar(value="1")
        self.auto_fill_red_var = tk.BooleanVar(value=True)
        self.auto_fill_blue_var = tk.BooleanVar(value=True)
        self._parsed_layouts: Dict[str, Optional[Dict[int, Tuple[int, int]]]] = {
            "R": None,
            "B": None,
        }
        self.edit_layouts: Dict[str, Dict[int, Tuple[int, int]]] = {"R": {}, "B": {}}
        self.red_start_cells = set(engine.START_RED_CELLS)
        self.blue_start_cells = set(engine.START_BLUE_CELLS)

        self.turn_var = tk.StringVar(value=t("turn_label", self.lang).format(turn="RED"))

        self.board_buttons: List[List[tk.Button]] = []
        self.selected: Optional[Tuple[int, int]] = None
        self._highlighted: Set[Tuple[int, int]] = set()

        self.log_text = tk.Text(self.root, height=12, width=48, state=tk.DISABLED)
        self.log_text.configure(font=(font_family, base_size - 1))

        self.controller = self._build_controller()
        self._layout_widgets(piece_font)
        self.root.update_idletasks()
        self.root.after(0, lambda: self._request_board_resize(delay=0))
        self._center_window()
        initial_status_key = "status_ready" if self.has_cjk_font else "missing_cjk_fonts"
        initial_level = "info" if self.has_cjk_font else "warning"
        self._set_status_key(initial_status_key, level=initial_level)
        self._refresh_board()
        self._refresh_ui_state()
        self._stabilize_layout()
        contract_errors = self._run_ui_contract_check()
        if contract_errors:
            for err in contract_errors:
                print(f"UI contract error: {err}")
            self._set_status_text(" | ".join(contract_errors), level="error")

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

    def _build_board_area(self, parent: ttk.Frame, piece_font) -> None:
        board_frame = ttk.Frame(parent, padding=6, borderwidth=1, relief=tk.SOLID)
        self.board_frame = board_frame
        board_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=8)
        board_frame.grid_propagate(False)
        board_frame.configure(width=600, height=600)
        self._resize_after: Optional[str] = None
        board_frame.bind("<Configure>", self._on_board_area_resize)
        for idx in range(engine.BOARD_SIZE):
            board_frame.columnconfigure(idx, weight=1, uniform="board")
            board_frame.rowconfigure(idx, weight=1, uniform="board")
        for r in range(engine.BOARD_SIZE):
            row_buttons: List[tk.Button] = []
            for c in range(engine.BOARD_SIZE):
                btn = tk.Button(
                    board_frame,
                    text="",
                    width=1,
                    height=1,
                    font=piece_font,
                    relief=tk.RAISED,
                    command=lambda rr=r, cc=c: self._on_square_click(rr, cc),
                )
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                row_buttons.append(btn)
            self.board_buttons.append(row_buttons)

    def _build_control_panel(self, parent: ttk.Frame, piece_font) -> None:
        control_container = ttk.Frame(parent, padding=(0, 0, 0, 0))
        control_container.grid(row=0, column=1, sticky="nsew", padx=12, pady=8)
        control_container.columnconfigure(0, weight=1, minsize=420)
        control_container.rowconfigure(0, weight=1)

        control_canvas = tk.Canvas(control_container, highlightthickness=0)
        control_canvas.grid(row=0, column=0, sticky="nsew")
        control_scroll = ttk.Scrollbar(control_container, orient="vertical", command=control_canvas.yview)
        control_scroll.grid(row=0, column=1, sticky="ns")
        control_canvas.configure(yscrollcommand=control_scroll.set)

        control_frame = ttk.Frame(control_canvas, padding=(0, 0, 0, 0))
        self.control_frame = control_frame
        control_frame.columnconfigure(0, weight=1, minsize=420)
        window_id = control_canvas.create_window((0, 0), window=control_frame, anchor="nw")

        def _sync_scrollregion(event=None) -> None:
            control_canvas.configure(scrollregion=control_canvas.bbox("all"))
            try:
                control_canvas.itemconfigure(window_id, width=control_canvas.winfo_width())
            except Exception:
                pass

        control_frame.bind("<Configure>", _sync_scrollregion)
        control_canvas.bind("<Configure>", _sync_scrollregion)
        self._bind_mousewheel(control_canvas, control_canvas)
        self._bind_mousewheel(control_frame, control_canvas)

        play_frame = ttk.LabelFrame(control_frame, text=t("play_agents_group", self.lang), padding=10)
        self.play_frame = play_frame
        play_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        play_frame.columnconfigure(1, weight=1)
        self.mode_play_radio = ttk.Radiobutton(
            play_frame, text=t("mode_play", self.lang), variable=self.mode_var, value="play", command=self._refresh_ui_state
        )
        self.mode_play_radio.grid(row=0, column=0, sticky="w", pady=2)
        self.rb_mode_play = self.mode_play_radio
        self.mode_advise_radio = ttk.Radiobutton(
            play_frame, text=t("mode_advise", self.lang), variable=self.mode_var, value="advise", command=self._refresh_ui_state
        )
        self.mode_advise_radio.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=2)
        self.rb_mode_advise = self.mode_advise_radio
        self.auto_apply_check = ttk.Checkbutton(play_frame, text=t("auto_apply", self.lang), variable=self.auto_apply_var)
        self.auto_apply_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.chk_auto_apply = self.auto_apply_check

        agents_frame = ttk.Frame(play_frame)
        agents_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        agents_frame.columnconfigure(1, weight=1)
        self.red_agent_label = ttk.Label(agents_frame, text=t("red_agent", self.lang))
        self.red_agent_label.grid(row=0, column=0, sticky="w")
        self.cb_red_agent = ttk.OptionMenu(
            agents_frame,
            self.agent_var_red,
            self.agent_var_red.get(),
            *[label for label, _ in AGENT_CHOICES],
            command=lambda *_: self._on_agents_changed(),
        )
        self.cb_red_agent.grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        self.blue_agent_label = ttk.Label(agents_frame, text=t("blue_agent", self.lang))
        self.blue_agent_label.grid(row=1, column=0, sticky="w")
        self.cb_blue_agent = ttk.OptionMenu(
            agents_frame,
            self.agent_var_blue,
            self.agent_var_blue.get(),
            *[label for label, _ in AGENT_CHOICES],
            command=lambda *_: self._on_agents_changed(),
        )
        self.cb_blue_agent.grid(row=1, column=1, sticky="ew", padx=6, pady=2)

        dice_frame = ttk.LabelFrame(control_frame, text=t("dice_group", self.lang), padding=10)
        self.dice_frame = dice_frame
        dice_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        dice_frame.columnconfigure(1, weight=1)
        self.roll_button = ttk.Button(dice_frame, text=t("roll_dice", self.lang), command=self._on_roll_dice)
        self.roll_button.grid(row=0, column=0, padx=(0, 6), pady=4, sticky="ew")
        self.btn_roll_dice = self.roll_button
        self.dice_entry = ttk.Entry(dice_frame, width=8)
        self.dice_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.entry_set_dice = self.dice_entry
        self.apply_dice_button = ttk.Button(dice_frame, text=t("apply_dice", self.lang), command=self._on_set_dice)
        self.apply_dice_button.grid(row=0, column=2, padx=(6, 0), pady=4, sticky="ew")
        self.btn_apply_dice = self.apply_dice_button

        # Always-visible move/action controls (must stay mapped)
        action_frame = ttk.LabelFrame(control_frame, text=t("move_group", self.lang), padding=10)
        self.move_frame = action_frame
        action_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        control_frame.rowconfigure(2, weight=1)

        input_row = ttk.Frame(action_frame)
        input_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        input_row.columnconfigure(0, weight=1)
        self.input_label = ttk.Label(input_row, text=t("enter_move", self.lang))
        self.input_label.grid(row=0, column=0, sticky="w")
        self.move_text_entry = ttk.Entry(input_row, width=24)
        self.move_text_entry.grid(row=1, column=0, sticky="ew", pady=4)
        self.move_text_entry.bind("<Return>", lambda _: self._on_text_move())
        self.entry_move_text = self.move_text_entry
        self.apply_text_button = ttk.Button(input_row, text=t("apply", self.lang), command=self._on_text_move)
        self.apply_text_button.grid(row=1, column=1, padx=(6, 0), pady=4, sticky="ew")
        self.btn_apply_move = self.apply_text_button

        actions_buttons = ttk.Frame(action_frame)
        actions_buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        actions_buttons.columnconfigure((0, 1), weight=1)
        self.ai_move_button = ttk.Button(actions_buttons, text=t("ai_move", self.lang), command=self._on_ai_move)
        self.ai_move_button.grid(row=0, column=0, padx=4, sticky="ew")
        self.btn_ai_move = self.ai_move_button
        self.copy_last_button = ttk.Button(
            actions_buttons, text=t("copy_last", self.lang), command=self._on_copy_last_move
        )
        self.copy_last_button.grid(row=0, column=1, padx=4, sticky="ew")
        self.btn_copy_last_move = self.copy_last_button

        game_frame = ttk.LabelFrame(control_frame, text=t("game_group", self.lang), padding=10)
        self.game_frame = game_frame
        game_frame.grid(row=3, column=0, sticky="ew", pady=(8, 8))
        game_frame.columnconfigure(1, weight=1)
        self.new_game_button = ttk.Button(game_frame, text=t("new_game", self.lang), command=self._on_new_game)
        self.new_game_button.grid(row=0, column=0, padx=6, pady=4, sticky="ew")
        self.btn_new_game = self.new_game_button
        self.save_wtn_button = ttk.Button(game_frame, text=t("save_wtn", self.lang), command=self._on_save_wtn)
        self.save_wtn_button.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        self.btn_save_wtn = self.save_wtn_button

        layout_frame = ttk.LabelFrame(control_frame, text=t("layout_group", self.lang), padding=10)
        self.layout_frame = layout_frame
        layout_frame.grid(row=4, column=0, sticky="nsew")
        control_frame.rowconfigure(4, weight=1)
        layout_frame.columnconfigure(1, weight=1)
        layout_entries = ttk.Frame(layout_frame)
        layout_entries.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        layout_entries.columnconfigure(1, weight=1)
        layout_entries.columnconfigure(3, weight=1)
        self.red_layout_label = ttk.Label(layout_entries, text=t("layouts_red", self.lang))
        self.red_layout_label.grid(row=0, column=0, sticky="w", pady=2)
        self.red_layout_entry.grid(in_=layout_entries, row=0, column=1, sticky="ew", padx=(6, 12))
        self.blue_layout_label = ttk.Label(layout_entries, text=t("layouts_blue", self.lang))
        self.blue_layout_label.grid(row=1, column=0, sticky="w", pady=2)
        self.blue_layout_entry.grid(in_=layout_entries, row=1, column=1, sticky="ew", padx=(6, 12))

        self.red_layout_text_label = ttk.Label(layout_frame, text=t("layout_wtn_red", self.lang))
        self.red_layout_text_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.red_layout_text.grid(in_=layout_frame, row=2, column=0, columnspan=3, sticky="ew", pady=2)
        self.blue_layout_text_label = ttk.Label(layout_frame, text=t("layout_wtn_blue", self.lang))
        self.blue_layout_text_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.blue_layout_text.grid(in_=layout_frame, row=4, column=0, columnspan=3, sticky="ew", pady=2)

        layout_buttons = ttk.Frame(layout_frame)
        layout_buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        layout_buttons.columnconfigure((0, 1), weight=1)
        self.apply_layout_button = ttk.Button(
            layout_buttons, text=t("apply_layout", self.lang), command=self._on_apply_layouts
        )
        self.apply_layout_button.grid(row=0, column=0, padx=4, sticky="ew")
        self.new_game_layout_button = ttk.Button(
            layout_buttons, text=t("new_game_layout", self.lang), command=self._on_new_game_from_layout
        )
        self.new_game_layout_button.grid(row=0, column=1, padx=4, sticky="ew")

        edit_tools = ttk.Frame(layout_frame)
        edit_tools.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        edit_tools.columnconfigure(1, weight=1)
        self.edit_toggle = ttk.Checkbutton(
            edit_tools,
            text=t("edit_layout_mode", self.lang),
            variable=self.edit_mode_var,
            command=self._on_toggle_edit_mode,
        )
        self.edit_toggle.grid(row=0, column=0, columnspan=2, sticky="w")
        self.edit_side_label = ttk.Label(edit_tools, text=t("edit_side", self.lang))
        self.edit_side_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.edit_red_radio = ttk.Radiobutton(
            edit_tools, text=t("red_agent", self.lang), variable=self.edit_side_var, value="R", command=self._on_edit_side
        )
        self.edit_red_radio.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.edit_blue_radio = ttk.Radiobutton(
            edit_tools, text=t("blue_agent", self.lang), variable=self.edit_side_var, value="B", command=self._on_edit_side
        )
        self.edit_blue_radio.grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.edit_piece_label = ttk.Label(edit_tools, text=t("edit_piece", self.lang))
        self.edit_piece_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.edit_piece_combo = ttk.Combobox(
            edit_tools,
            textvariable=self.edit_piece_var,
            values=[str(i) for i in range(1, 7)],
            state="readonly",
            width=6,
        )
        self.edit_piece_combo.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.clear_piece_button = ttk.Button(edit_tools, text=t("clear_piece", self.lang), command=self._clear_selected_piece)
        self.clear_piece_button.grid(row=2, column=2, padx=4, pady=(6, 0), sticky="ew")
        self.clear_side_button = ttk.Button(edit_tools, text=t("clear_side", self.lang), command=self._clear_side)
        self.clear_side_button.grid(row=3, column=2, padx=4, pady=4, sticky="ew")
        self.mirror_button = ttk.Button(edit_tools, text=t("mirror_layout", self.lang), command=self._mirror_layout)
        self.mirror_button.grid(row=3, column=1, padx=4, pady=4, sticky="ew")
        fill_frame = ttk.Frame(edit_tools)
        fill_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.auto_fill_red_check = ttk.Checkbutton(
            fill_frame, text=t("auto_fill_red", self.lang), variable=self.auto_fill_red_var
        )
        self.auto_fill_red_check.grid(row=0, column=0, sticky="w")
        self.auto_fill_blue_check = ttk.Checkbutton(
            fill_frame, text=t("auto_fill_blue", self.lang), variable=self.auto_fill_blue_var
        )
        self.auto_fill_blue_check.grid(row=0, column=1, sticky="w", padx=(12, 0))

    def _layout_widgets(self, piece_font) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        nav_frame = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        nav_frame.grid(row=0, column=0, sticky="ew")
        for idx in range(7):
            nav_frame.columnconfigure(idx, weight=0)
        nav_frame.columnconfigure(7, weight=1)
        self.title_label = ttk.Label(nav_frame, text=t("window_title", self.lang), font=("TkDefaultFont", 14, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.nav_buttons = {}
        nav_names = [
            ("home", "Home"),
            ("play", "Play"),
            ("layout", "Layout"),
            ("settings", "Settings"),
            ("help", "Help"),
        ]
        for idx, (name, label) in enumerate(nav_names, start=1):
            btn = ttk.Button(nav_frame, text=label, command=lambda n=name: self.show_screen(n))
            btn.grid(row=0, column=idx, padx=(6, 0))
            self.nav_buttons[name] = btn
        language_wrap = ttk.Frame(nav_frame)
        language_wrap.grid(row=0, column=7, sticky="e")
        language_wrap.columnconfigure(1, weight=1)
        self.language_label = ttk.Label(language_wrap, text=t("language_label", self.lang))
        self.language_label.grid(row=0, column=0, sticky="e", padx=(0, 6))
        self.language_combo = ttk.Combobox(
            language_wrap,
            textvariable=self.lang_var,
            values=available_langs(),
            state="readonly",
            width=10,
        )
        self.language_combo.grid(row=0, column=1, sticky="e")
        self.language_combo.bind("<<ComboboxSelected>>", lambda _: self._on_language_changed())
        self.header_status_label = ttk.Label(nav_frame, textvariable=self.status_var)
        self.header_status_label.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(6, 0))

        self.screen_container = ttk.Frame(self.root)
        self.screen_container.grid(row=1, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self.screen_home = ttk.Frame(self.screen_container, padding=20)
        self.screen_play = ttk.Frame(self.screen_container)
        self.screen_layout = ttk.Frame(self.screen_container)
        self.screen_settings = ttk.Frame(self.screen_container, padding=20)
        self.screen_help = ttk.Frame(self.screen_container, padding=20)
        for frame in (
            self.screen_home,
            self.screen_play,
            self.screen_layout,
            self.screen_settings,
            self.screen_help,
        ):
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_home_screen()
        self._build_play_screen(piece_font)
        self._build_layout_screen()
        self._build_settings_screen()
        self._build_help_screen()
        self.show_screen("home")

    def _build_home_screen(self) -> None:
        self.screen_home.columnconfigure(0, weight=1)
        welcome = ttk.Label(
            self.screen_home,
            text=t("window_title", self.lang),
            font=("TkDefaultFont", 18, "bold"),
        )
        welcome.grid(row=0, column=0, sticky="w", pady=(0, 12))
        blurb = ttk.Label(
            self.screen_home,
            text="Select Play to start a match, Layout to edit starting positions, or Settings to adjust defaults.",
            wraplength=900,
            justify=tk.LEFT,
        )
        blurb.grid(row=1, column=0, sticky="w")
        start_btn = ttk.Button(self.screen_home, text="Start Playing", command=lambda: self.show_screen("play"))
        start_btn.grid(row=2, column=0, sticky="w", pady=(16, 0))

    def _build_play_screen(self, piece_font) -> None:
        self.screen_play.columnconfigure(0, weight=1)
        self.screen_play.rowconfigure(1, weight=1)
        heading = ttk.Label(self.screen_play, text="Play", font=("TkDefaultFont", 14, "bold"))
        heading.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))

        play_area = ttk.Frame(self.screen_play, padding=(12, 6, 12, 6))
        play_area.grid(row=1, column=0, sticky="nsew")
        play_area.rowconfigure(0, weight=1)
        play_area.columnconfigure(0, weight=1)
        play_area.columnconfigure(1, weight=0, minsize=420)

        self._build_board_area(play_area, piece_font)
        self._build_control_panel(play_area, piece_font)

        status_frame = ttk.Frame(self.screen_play, padding=(12, 0, 12, 6))
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.columnconfigure(3, weight=1)
        status_frame.columnconfigure(9, weight=1)
        self.phase_heading = ttk.Label(status_frame, text=t("phase_label", self.lang), font=("TkDefaultFont", 11, "bold"))
        self.phase_heading.grid(row=0, column=0, sticky="w")
        self.phase_value = ttk.Label(status_frame, textvariable=self.phase_var)
        self.phase_value.grid(row=0, column=1, sticky="w", padx=(4, 12))
        self.next_heading = ttk.Label(status_frame, text=t("next_step_label", self.lang), font=("TkDefaultFont", 11, "bold"))
        self.next_heading.grid(row=0, column=2, sticky="w")
        self.next_step_label = ttk.Label(status_frame, textvariable=self.next_step_var)
        self.next_step_label.grid(row=0, column=3, columnspan=7, sticky="w", padx=(4, 0))

        self.turn_heading = ttk.Label(status_frame, text=t("info_turn", self.lang))
        self.turn_heading.grid(row=1, column=0, sticky="w")
        self.turn_label = ttk.Label(status_frame, textvariable=self.turn_var, font=("TkDefaultFont", 11, "bold"))
        self.turn_label.grid(row=1, column=1, sticky="w", padx=(4, 12))
        self.dice_heading = ttk.Label(status_frame, text=t("info_dice", self.lang))
        self.dice_heading.grid(row=1, column=2, sticky="w")
        self.dice_value_var = tk.StringVar(value=t("dice_label", self.lang).format(dice="-"))
        self.dice_label = ttk.Label(status_frame, textvariable=self.dice_value_var)
        self.dice_label.grid(row=1, column=3, sticky="w", padx=(4, 12))
        self.can_move_heading = ttk.Label(status_frame, text=t("info_can_move", self.lang))
        self.can_move_heading.grid(row=1, column=4, sticky="w")
        self.can_move_label = ttk.Label(status_frame, textvariable=self.info_can_move_var)
        self.can_move_label.grid(row=1, column=5, sticky="w", padx=(4, 12))
        self.last_move_heading = ttk.Label(status_frame, text=t("info_last_move", self.lang))
        self.last_move_heading.grid(row=1, column=6, sticky="w")
        self.last_move_label = ttk.Label(status_frame, textvariable=self.last_move_var)
        self.last_move_label.grid(row=1, column=7, sticky="w", padx=(4, 12))
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.grid(row=1, column=8, columnspan=2, sticky="ew")

        self.ai_suggestion_heading = ttk.Label(status_frame, text=t("info_ai_suggestion", self.lang))
        self.ai_suggestion_heading.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.ai_suggestion_label = ttk.Label(status_frame, textvariable=self.ai_suggestion_var)
        self.ai_suggestion_label.grid(row=2, column=1, columnspan=9, sticky="w", pady=(6, 0))

        log_frame = ttk.LabelFrame(self.screen_play, text=t("move_log", self.lang), padding=8)
        self.log_frame = log_frame
        log_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.grid(row=0, column=0, sticky="nsew")
        log_text_frame.columnconfigure(0, weight=1)
        log_text_frame.rowconfigure(0, weight=1)
        scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.log_text.yview)
        self.log_text.grid(in_=log_text_frame, row=0, column=0, sticky="nsew")

    def _build_layout_screen(self) -> None:
        self.screen_layout.columnconfigure(0, weight=1, minsize=1100)
        self.screen_layout.rowconfigure(1, weight=1)
        heading = ttk.Label(self.screen_layout, text="Layout", font=("TkDefaultFont", 14, "bold"))
        heading.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        layout_wrapper = ttk.Frame(self.screen_layout, padding=(12, 6, 12, 12))
        layout_wrapper.grid(row=1, column=0, sticky="nsew")
        layout_wrapper.columnconfigure(0, weight=1)

        layout_frame = ttk.LabelFrame(layout_wrapper, text=t("layout_group", self.lang), padding=10)
        self.layout_frame = layout_frame
        layout_frame.grid(row=0, column=0, sticky="nsew")
        layout_frame.columnconfigure(1, weight=1)
        layout_frame.columnconfigure(3, weight=1)
        layout_entries = ttk.Frame(layout_frame)
        layout_entries.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        layout_entries.columnconfigure(1, weight=1)
        layout_entries.columnconfigure(3, weight=1)
        self.red_layout_label = ttk.Label(layout_entries, text=t("layouts_red", self.lang))
        self.red_layout_label.grid(row=0, column=0, sticky="w", pady=2)
        self.red_layout_entry.grid(in_=layout_entries, row=0, column=1, sticky="ew", padx=(6, 12))
        self.blue_layout_label = ttk.Label(layout_entries, text=t("layouts_blue", self.lang))
        self.blue_layout_label.grid(row=1, column=0, sticky="w", pady=2)
        self.blue_layout_entry.grid(in_=layout_entries, row=1, column=1, sticky="ew", padx=(6, 12))

        self.red_layout_text_label = ttk.Label(layout_frame, text=t("layout_wtn_red", self.lang))
        self.red_layout_text_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.red_layout_text.grid(in_=layout_frame, row=2, column=0, columnspan=3, sticky="ew", pady=2)
        self.blue_layout_text_label = ttk.Label(layout_frame, text=t("layout_wtn_blue", self.lang))
        self.blue_layout_text_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.blue_layout_text.grid(in_=layout_frame, row=4, column=0, columnspan=3, sticky="ew", pady=2)

        layout_buttons = ttk.Frame(layout_frame)
        layout_buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        layout_buttons.columnconfigure((0, 1), weight=1)
        self.apply_layout_button = ttk.Button(
            layout_buttons, text=t("apply_layout", self.lang), command=self._on_apply_layouts
        )
        self.apply_layout_button.grid(row=0, column=0, padx=4, sticky="ew")
        self.new_game_layout_button = ttk.Button(
            layout_buttons, text=t("new_game_layout", self.lang), command=self._on_new_game_from_layout
        )
        self.new_game_layout_button.grid(row=0, column=1, padx=4, sticky="ew")

        edit_tools = ttk.Frame(layout_frame)
        edit_tools.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        edit_tools.columnconfigure(1, weight=1)
        self.edit_toggle = ttk.Checkbutton(
            edit_tools,
            text=t("edit_layout_mode", self.lang),
            variable=self.edit_mode_var,
            command=self._on_toggle_edit_mode,
        )
        self.edit_toggle.grid(row=0, column=0, columnspan=2, sticky="w")
        self.edit_side_label = ttk.Label(edit_tools, text=t("edit_side", self.lang))
        self.edit_side_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.edit_red_radio = ttk.Radiobutton(
            edit_tools, text=t("red_agent", self.lang), variable=self.edit_side_var, value="R", command=self._on_edit_side
        )
        self.edit_red_radio.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.edit_blue_radio = ttk.Radiobutton(
            edit_tools, text=t("blue_agent", self.lang), variable=self.edit_side_var, value="B", command=self._on_edit_side
        )
        self.edit_blue_radio.grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.edit_piece_label = ttk.Label(edit_tools, text=t("edit_piece", self.lang))
        self.edit_piece_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.edit_piece_combo = ttk.Combobox(
            edit_tools,
            textvariable=self.edit_piece_var,
            values=[str(i) for i in range(1, 7)],
            state="readonly",
            width=6,
        )
        self.edit_piece_combo.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.clear_piece_button = ttk.Button(edit_tools, text=t("clear_piece", self.lang), command=self._clear_selected_piece)
        self.clear_piece_button.grid(row=2, column=2, padx=4, pady=(6, 0), sticky="ew")
        self.clear_side_button = ttk.Button(edit_tools, text=t("clear_side", self.lang), command=self._clear_side)
        self.clear_side_button.grid(row=3, column=2, padx=4, pady=4, sticky="ew")
        self.mirror_button = ttk.Button(edit_tools, text=t("mirror_layout", self.lang), command=self._mirror_layout)
        self.mirror_button.grid(row=3, column=1, padx=4, pady=4, sticky="ew")
        fill_frame = ttk.Frame(edit_tools)
        fill_frame.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.auto_fill_red_check = ttk.Checkbutton(
            fill_frame, text=t("auto_fill_red", self.lang), variable=self.auto_fill_red_var
        )
        self.auto_fill_red_check.grid(row=0, column=0, sticky="w")
        self.auto_fill_blue_check = ttk.Checkbutton(
            fill_frame, text=t("auto_fill_blue", self.lang), variable=self.auto_fill_blue_var
        )
        self.auto_fill_blue_check.grid(row=0, column=1, sticky="w", padx=(12, 0))

    def _build_settings_screen(self) -> None:
        self.default_agent_red = tk.StringVar(value=self.agent_var_red.get())
        self.default_agent_blue = tk.StringVar(value=self.agent_var_blue.get())
        heading = ttk.Label(self.screen_settings, text="Settings", font=("TkDefaultFont", 14, "bold"))
        heading.grid(row=0, column=0, sticky="w", pady=(0, 12))
        grid = ttk.Frame(self.screen_settings)
        grid.grid(row=1, column=0, sticky="nsew")
        grid.columnconfigure(1, weight=1)

        size_label = ttk.Label(grid, text="Window size presets")
        size_label.grid(row=0, column=0, sticky="w", pady=4)
        size_buttons = ttk.Frame(grid)
        size_buttons.grid(row=0, column=1, sticky="w", pady=4)
        for text, dims in [("1150x800", (1150, 800)), ("1300x900", (1300, 900)), ("1400x950", (1400, 950))]:
            btn = ttk.Button(size_buttons, text=text, command=lambda d=dims: self._apply_window_preset(*d))
            btn.pack(side=tk.LEFT, padx=4)
        maximize_btn = ttk.Button(size_buttons, text="Maximize", command=self._maximize_window)
        maximize_btn.pack(side=tk.LEFT, padx=4)

        auto_apply = ttk.Checkbutton(grid, text="Auto-apply advice", variable=self.auto_apply_var)
        auto_apply.grid(row=1, column=0, columnspan=2, sticky="w", pady=6)

        agent_defaults = ttk.LabelFrame(grid, text="Default agents", padding=8)
        agent_defaults.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        agent_defaults.columnconfigure(1, weight=1)
        ttk.Label(agent_defaults, text="Red").grid(row=0, column=0, sticky="w")
        ttk.OptionMenu(
            agent_defaults,
            self.default_agent_red,
            self.default_agent_red.get(),
            *[label for label, _ in AGENT_CHOICES],
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(agent_defaults, text="Blue").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.OptionMenu(
            agent_defaults,
            self.default_agent_blue,
            self.default_agent_blue.get(),
            *[label for label, _ in AGENT_CHOICES],
        ).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))

    def _build_help_screen(self) -> None:
        heading = ttk.Label(self.screen_help, text="Help", font=("TkDefaultFont", 14, "bold"))
        heading.grid(row=0, column=0, sticky="w", pady=(0, 12))
        tips_text = tk.Text(self.screen_help, height=16, wrap=tk.WORD)
        tips_text.grid(row=1, column=0, sticky="nsew")
        self.screen_help.rowconfigure(1, weight=1)
        self.screen_help.columnconfigure(0, weight=1)
        help_lines = [
            "Use Play to roll dice, enter moves, and view advice.",
            "Move format: (R1,bc) where color+id goes to coord.",
            "Dice rules: roll selects piece id; nearest surviving id may move if rolled piece is captured.",
            "Layout: switch to Layout screen to edit starting positions and save new WTN layouts.",
        ]
        tips_text.insert("1.0", "\n".join(help_lines))
        tips_text.configure(state=tk.DISABLED)

    def show_screen(self, name: str) -> None:
        screens = {
            "home": self.screen_home,
            "play": self.screen_play,
            "layout": self.screen_layout,
            "settings": self.screen_settings,
            "help": self.screen_help,
        }
        target = screens.get(name, self.screen_home)
        target.tkraise()
        self.current_screen = name
        for nav_name, btn in self.nav_buttons.items():
            try:
                btn.state(["pressed"] if nav_name == name else ["!pressed"])
            except Exception:
                pass

    def _run_ui_contract_check(self, stabilized_size: Optional[Tuple[int, int]] = None) -> List[str]:
        errors: List[str] = []
        previous_screen = getattr(self, "current_screen", "home")
        if previous_screen != "play":
            self.show_screen("play")
        for attr in REQUIRED_WIDGET_ATTRS:
            if not hasattr(self, attr):
                errors.append(f"missing attribute '{attr}'")

        self.root.update_idletasks()
        for attr in REQUIRED_MAPPED_WIDGETS:
            if not hasattr(self, attr):
                continue
            widget = getattr(self, attr)
            try:
                mapped = widget.winfo_ismapped()
            except Exception:
                mapped = 0
            if mapped != 1:
                errors.append(f"widget '{attr}' is not mapped")

        control_widget = getattr(self, "control_frame", None)

        def _is_under_control(widget: tk.Misc, control: tk.Misc) -> bool:
            try:
                root_widget = widget._root()
                parent_name = widget.winfo_parent()
            except Exception:
                return False
            while parent_name:
                try:
                    parent = root_widget.nametowidget(parent_name)
                except Exception:
                    return False
                if parent is control:
                    return True
                parent_name = parent.winfo_parent()
            return False

        if control_widget is not None:
            for attr in CONTROL_CHILD_WIDGETS:
                if not hasattr(self, attr):
                    continue
                widget = getattr(self, attr)
                if not _is_under_control(widget, control_widget):
                    errors.append(f"widget '{attr}' not under control_frame")

        if stabilized_size is not None:
            width, height = stabilized_size
        else:
            for _ in range(2):
                self.root.update_idletasks()
                self.root.update()
            try:
                width = self.board_frame.winfo_width()
                height = self.board_frame.winfo_height()
            except Exception:
                width = height = 0

        try:
            req_width = self.board_frame.winfo_reqwidth()
            req_height = self.board_frame.winfo_reqheight()
        except Exception:
            req_width = req_height = 0

        if width is None or height is None:
            errors.append("board_frame size unavailable")
        else:
            actual_small = width < 300 or height < 300
            req_small = req_width < 300 or req_height < 300
            if actual_small and req_small:
                errors.append(
                    f"board_frame too small ({width}x{height}), req=({req_width}x{req_height})"
                )

        if previous_screen != "play":
            self.show_screen(previous_screen)
        return errors

    def _stabilize_layout(self, attempts: int = 50, sleep: float = 0.0) -> None:
        """Pump the event loop until the board has usable space."""
        previous_screen = getattr(self, "current_screen", "home")
        if previous_screen != "play":
            self.show_screen("play")

        for _ in range(attempts):
            self.root.update_idletasks()
            self.root.update()
            try:
                width = self.board_frame.winfo_width()
                height = self.board_frame.winfo_height()
            except Exception:
                width = height = 0
            if width >= 300 and height >= 300:
                break
            if sleep:
                time.sleep(sleep)
        self._request_board_resize(delay=0)
        if previous_screen != "play":
            self.show_screen(previous_screen)

    def _on_board_area_resize(self, event) -> None:
        self._request_board_resize(width=max(event.width, 0), height=max(event.height, 0))

    def _request_board_resize(self, width: Optional[int] = None, height: Optional[int] = None, delay: int = 50) -> None:
        if self._resize_after:
            self.root.after_cancel(self._resize_after)

        def redraw() -> None:
            frame_w = self.board_frame.winfo_width()
            frame_h = self.board_frame.winfo_height()
            current_width = width if width is not None else frame_w
            current_height = height if height is not None else frame_h
            if current_width < 120 or current_height < 120:
                self._request_board_resize(delay=100)
                return
            self._apply_board_size(current_width, current_height)

        self._resize_after = self.root.after(delay, redraw)

    def _apply_board_size(self, width: int, height: int) -> None:
        self._resize_after = None
        if width < 300 or height < 300:
            self._request_board_resize(delay=50)
            return
        padding = 12
        avail_w = max(width - padding, engine.BOARD_SIZE)
        avail_h = max(height - padding, engine.BOARD_SIZE)
        raw_cell = min(avail_w, avail_h) // engine.BOARD_SIZE
        if raw_cell < 60 and min(avail_w, avail_h) >= 60 * engine.BOARD_SIZE:
            cell = 60
        else:
            cell = max(24, raw_cell)
        board_size = cell * engine.BOARD_SIZE
        self.board_frame.configure(width=board_size, height=board_size)
        self.board_frame.update_idletasks()

    def _center_window(self) -> None:
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        offset_x = max(0, int((screen_w - width) / 2))
        offset_y = max(0, int((screen_h - height) / 3))
        self.root.geometry(f"{width}x{height}+{offset_x}+{offset_y}")

    def _apply_window_preset(self, width: int, height: int) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        clamped_w = min(width, max(900, screen_w - 40))
        clamped_h = min(height, max(700, screen_h - 80))
        self.root.geometry(f"{clamped_w}x{clamped_h}")
        min_w = min(clamped_w, max(900, screen_w - 80))
        min_h = min(clamped_h, max(700, screen_h - 120))
        self.root.minsize(min_w, min_h)
        self._center_window()

    def _apply_initial_geometry(self) -> None:
        presets = [(1300, 900), (1250, 860), (1200, 820), (1150, 800), (1100, 760)]
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        usable_w = max(960, screen_w - 80)
        usable_h = max(720, screen_h - 120)
        selected_w, selected_h = presets[-1]
        for w, h in presets:
            if w <= usable_w and h <= usable_h:
                selected_w, selected_h = w, h
                break
        selected_w = min(selected_w, usable_w)
        selected_h = min(selected_h, usable_h)
        self.root.geometry(f"{selected_w}x{selected_h}")
        self.root.minsize(min(selected_w, usable_w), min(selected_h, usable_h))

    def _maximize_window(self) -> None:
        try:
            self.root.state("zoomed")
        except Exception:
            try:
                self.root.attributes("-zoomed", True)
            except Exception:
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                self.root.geometry(f"{screen_w}x{screen_h}+0+0")
                self.root.update_idletasks()

    def _bind_mousewheel(self, widget: tk.Misc, target_canvas: tk.Canvas) -> None:
        def _on_mousewheel(event):
            if event.delta:
                target_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) in (4, 5):
                target_canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", _on_mousewheel)
        widget.bind("<Button-5>", _on_mousewheel)

    def _refresh_texts(self) -> None:
        self.root.title(t("window_title", self.lang))
        self.title_label.configure(text=t("window_title", self.lang))
        self.language_label.configure(text=t("language_label", self.lang))
        self.language_combo.configure(values=available_langs())
        for frame, label in [
            (self.game_frame, "game_group"),
            (self.play_frame, "play_agents_group"),
            (self.dice_frame, "dice_group"),
            (self.move_frame, "move_group"),
            (self.layout_frame, "layout_group"),
            (self.log_frame, "move_log"),
        ]:
            frame.configure(text=t(label, self.lang))
        self.new_game_button.configure(text=t("new_game", self.lang))
        self.save_wtn_button.configure(text=t("save_wtn", self.lang))
        self.red_agent_label.configure(text=t("red_agent", self.lang))
        self.blue_agent_label.configure(text=t("blue_agent", self.lang))
        self.red_layout_label.configure(text=t("layouts_red", self.lang))
        self.blue_layout_label.configure(text=t("layouts_blue", self.lang))
        self.red_layout_text_label.configure(text=t("layout_wtn_red", self.lang))
        self.blue_layout_text_label.configure(text=t("layout_wtn_blue", self.lang))
        self.apply_layout_button.configure(text=t("apply_layout", self.lang))
        self.new_game_layout_button.configure(text=t("new_game_layout", self.lang))
        self.edit_toggle.configure(text=t("edit_layout_mode", self.lang))
        self.edit_side_label.configure(text=t("edit_side", self.lang))
        self.edit_red_radio.configure(text=t("red_agent", self.lang))
        self.edit_blue_radio.configure(text=t("blue_agent", self.lang))
        self.edit_piece_label.configure(text=t("edit_piece", self.lang))
        self.clear_piece_button.configure(text=t("clear_piece", self.lang))
        self.clear_side_button.configure(text=t("clear_side", self.lang))
        self.mirror_button.configure(text=t("mirror_layout", self.lang))
        self.auto_fill_red_check.configure(text=t("auto_fill_red", self.lang))
        self.auto_fill_blue_check.configure(text=t("auto_fill_blue", self.lang))
        self.mode_play_radio.configure(text=t("mode_play", self.lang))
        self.mode_advise_radio.configure(text=t("mode_advise", self.lang))
        self.auto_apply_check.configure(text=t("auto_apply", self.lang))
        self.roll_button.configure(text=t("roll_dice", self.lang))
        self.apply_dice_button.configure(text=t("apply_dice", self.lang))
        self.input_label.configure(text=t("enter_move", self.lang))
        self.apply_text_button.configure(text=t("apply", self.lang))
        self.ai_move_button.configure(text=t("ai_move", self.lang))
        self.copy_last_button.configure(text=t("copy_last", self.lang))
        self.phase_heading.configure(text=t("phase_label", self.lang))
        self.next_heading.configure(text=t("next_step_label", self.lang))
        self.turn_heading.configure(text=t("info_turn", self.lang))
        self.dice_heading.configure(text=t("info_dice", self.lang))
        self.can_move_heading.configure(text=t("info_can_move", self.lang))
        self.last_move_heading.configure(text=t("info_last_move", self.lang))
        self.ai_suggestion_heading.configure(text=t("info_ai_suggestion", self.lang))
        self.turn_var.set(t("turn_label", self.lang).format(turn=self.controller.state.turn.name))
        self.dice_value_var.set(t("dice_label", self.lang).format(dice=self.dice_var.get()))
        self.phase_var.set(t(f"phase_{self._phase}", self.lang))
        self.next_step_var.set(t(f"next_step_{self._phase}", self.lang))
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
        self._refresh_ui_state()

    def _apply_status(self, text: str, level: str) -> None:
        color_map = {
            "info": "#616161",
            "success": "#2e7d32",
            "error": "#c62828",
            "warning": "#ef6c00",
        }
        color = color_map.get(level, "#616161")
        self.status_label.configure(foreground=color)
        self.header_status_label.configure(foreground=color)
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

    def _on_help(self) -> None:
        tips = [
            t("help_header", self.lang),
            t("help_normal_game", self.lang),
            t("help_set_dice_tip", self.lang),
            t("help_advise_mode", self.lang),
            t("help_custom_layout", self.lang),
        ]
        for line in tips:
            self._log(line)
        self._set_status_text(t("help_written", self.lang), level="info")

    def _set_widget_state(self, widget, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        try:
            widget.configure(state=state)
        except tk.TclError:
            try:
                widget.state(["!disabled"] if enabled else ["disabled"])
            except Exception:
                pass

    def _update_phase(self) -> str:
        if self.edit_mode_var.get():
            phase = PHASE_SETUP
        elif engine.is_terminal(self.controller.state):
            phase = PHASE_GAME_OVER
        elif not self._game_started:
            phase = PHASE_SETUP
        elif self.controller.dice is None:
            phase = PHASE_NEED_DICE
        else:
            phase = PHASE_NEED_MOVE
        self._phase = phase
        self.phase_var.set(t(f"phase_{phase}", self.lang))
        self.next_step_var.set(t(f"next_step_{phase}", self.lang))
        return phase

    def _maybe_hint(self, key: Optional[str], level: str = "warning") -> None:
        if key is None:
            return
        current_level = self._status_state.get("level", "info")
        if current_level == "error" and level == "warning":
            return
        if self._status_state.get("key") == key:
            return
        self._set_status_key(key, level=level)

    def _refresh_ui_state(self) -> None:
        phase = self._update_phase()
        self._board_block_reason = None
        dice_enabled = phase == PHASE_NEED_DICE
        move_enabled = phase == PHASE_NEED_MOVE
        ai_enabled = False
        board_enabled = move_enabled
        reason_key: Optional[str] = None
        dice_reason: Optional[str] = None
        move_reason: Optional[str] = None
        hint_level = "warning"

        if phase == PHASE_SETUP:
            board_enabled = self.edit_mode_var.get()
            move_reason = "status_reason_need_start"
            dice_reason = "status_reason_need_start"
            if self.edit_mode_var.get():
                reason_key = "status_reason_layout_edit"
                hint_level = "info"
        elif phase == PHASE_NEED_DICE:
            move_reason = "status_reason_need_dice"
        elif phase == PHASE_NEED_MOVE:
            dice_reason = "status_reason_need_move"
            agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
            ai_enabled = self.mode_var.get() == "advise" or agent is not None
            if self._is_ai_turn():
                board_enabled = False
                reason_key = "status_reason_ai_turn"
        elif phase == PHASE_GAME_OVER:
            board_enabled = False
            dice_enabled = False
            move_enabled = False
            reason_key = "status_reason_game_over"
            dice_reason = reason_key
            move_reason = reason_key

        if phase == PHASE_NEED_MOVE:
            hint_level = "info"
        block_reason = reason_key or move_reason or dice_reason
        self._board_block_reason = None if board_enabled or self.edit_mode_var.get() else block_reason

        for widget in [self.roll_button, self.apply_dice_button, self.dice_entry]:
            self._set_widget_state(widget, dice_enabled)
        for widget in [self.move_text_entry, self.apply_text_button]:
            self._set_widget_state(widget, move_enabled)
        self._set_widget_state(self.ai_move_button, move_enabled and ai_enabled)
        self._set_widget_state(self.copy_last_button, phase != PHASE_SETUP)

        for row in self.board_buttons:
            for btn in row:
                self._set_widget_state(btn, board_enabled or self.edit_mode_var.get())

        self._maybe_hint(block_reason, level=hint_level)

    def _on_agents_changed(self) -> None:
        self._log(t("agents_changed", self.lang))
        self._set_status_key("agents_changed")
        self._refresh_ui_state()

    def _on_new_game(self) -> None:
        if hasattr(self, "default_agent_red"):
            self.agent_var_red.set(self.default_agent_red.get())
            self.agent_var_blue.set(self.default_agent_blue.get())
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
        self.edit_mode_var.set(False)
        self._refresh_board()
        self.last_move_var.set(t("no_last_move", self.lang))
        self.ai_suggestion_var.set(t("no_last_move", self.lang))
        self._ai_suggestion_empty = True
        self._game_started = True
        self._refresh_ui_state()
        self._set_status_key("new_game_started", level="success")
        self._log(t("new_game_started", self.lang))

    def _on_apply_layouts(self) -> None:
        parsed: Dict[str, Optional[Dict[int, Tuple[int, int]]]] = {"R": None, "B": None}
        for color, widget in (("R", self.red_layout_text), ("B", self.blue_layout_text)):
            raw = widget.get("1.0", tk.END).strip()
            if not raw:
                continue
            try:
                parsed_color, mapping = parse_layout_line(raw)
            except Exception as exc:
                label = t("red_agent", self.lang) if color == "R" else t("blue_agent", self.lang)
                self._set_status_text(
                    t("layout_parse_error", self.lang).format(color=label, error=exc), level="error"
                )
                return
            if parsed_color != color:
                label = t("red_agent", self.lang) if color == "R" else t("blue_agent", self.lang)
                self._set_status_text(
                    t("layout_color_mismatch", self.lang).format(expected=label, found=parsed_color),
                    level="error",
                )
                return
            parsed[color] = mapping
        self._parsed_layouts = parsed
        self._set_status_key("layout_applied", level="success")

    def _collect_layout_for_color(self, color: str) -> Optional[Dict[int, Tuple[int, int]]]:
        source = self.edit_layouts[color]
        if source:
            if len(source) == 6:
                return dict(source)
            auto_fill = self.auto_fill_red_var.get() if color == "R" else self.auto_fill_blue_var.get()
            if not auto_fill:
                raise ValueError(
                    t("layout_missing_pieces", self.lang).format(color=t("red_agent", self.lang) if color == "R" else t("blue_agent", self.lang))
                )
            return None
        return self._parsed_layouts.get(color)

    def _on_new_game_from_layout(self) -> None:
        try:
            red_agent = self._build_agent(self.agent_var_red.get())
            blue_agent = self._build_agent(self.agent_var_blue.get())
            red_layout = self._collect_layout_for_color("R")
            blue_layout = self._collect_layout_for_color("B")
            self.controller.new_game_custom(
                red_layout=red_layout,
                blue_layout=blue_layout,
                red_agent=red_agent,
                blue_agent=blue_agent,
            )
        except Exception as exc:
            self._set_status_text(t("layout_parse_error", self.lang).format(color="", error=exc), level="error")
            return
        self.selected = None
        self._clear_highlights()
        self.edit_mode_var.set(False)
        self._refresh_board()
        self.last_move_var.set(t("no_last_move", self.lang))
        self.ai_suggestion_var.set(t("no_last_move", self.lang))
        self._ai_suggestion_empty = True
        self._game_started = True
        self._refresh_ui_state()
        self._set_status_key("layout_started", level="success")
        self._log(t("layout_started", self.lang))

    def _on_roll_dice(self) -> None:
        self._refresh_ui_state()
        if self._phase != PHASE_NEED_DICE:
            reason = "status_reason_need_start" if self._phase == PHASE_SETUP else "status_reason_need_move"
            if self._phase == PHASE_GAME_OVER:
                reason = "status_reason_game_over"
            self._maybe_hint(reason)
            return
        value = self.controller.roll_dice(random.Random())
        self._update_dice(value)
        self._clear_selection_state()
        self._update_move_hints()
        self._set_status_key("status_dice_set", level="success", value=value)

    def _on_set_dice(self) -> None:
        raw = self.dice_entry.get().strip()
        if not raw:
            self._set_status_key("invalid_dice", level="error")
            return
        self._refresh_ui_state()
        if self._phase != PHASE_NEED_DICE:
            reason = "status_reason_need_start" if self._phase == PHASE_SETUP else "status_reason_need_move"
            if self._phase == PHASE_GAME_OVER:
                reason = "status_reason_game_over"
                self._maybe_hint(reason, level="error")
            else:
                self._maybe_hint(reason)
            return
        try:
            value = int(raw)
            if value < 1 or value > 6:
                raise ValueError(t("invalid_dice", self.lang))
            self.controller.set_dice(value)
            self._update_dice(value)
        except Exception as exc:
            mapped = self._status_for_exception(exc)
            if mapped:
                key, fmt = mapped
                self._set_status_key(key, level="error", **fmt)
            else:
                self._set_status_text(t("invalid_dice", self.lang), level="error")
            return
        self._clear_selection_state()
        self._update_move_hints()
        self._set_status_key("status_dice_set", level="success", value=value)

    def _on_text_move(self) -> None:
        text = self.move_text_entry.get().strip()
        if not text:
            return
        self._refresh_ui_state()
        if self.edit_mode_var.get():
            self._maybe_hint("status_reason_layout_edit")
            return
        if self._phase != PHASE_NEED_MOVE:
            reason = "status_reason_need_dice" if self._phase == PHASE_NEED_DICE else "status_reason_need_start"
            if self._phase == PHASE_GAME_OVER:
                reason = "status_reason_game_over"
            self._maybe_hint(reason)
            return
        if engine.is_terminal(self.controller.state):
            self._log(t("game_over", self.lang))
            return
        if self._is_ai_turn():
            self._log(t("ai_turn_wait", self.lang))
            self._set_status_key("ai_turn_wait", level="warning")
            return
        if self.controller.dice is None:
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
        self._refresh_ui_state()
        if self.edit_mode_var.get():
            self._maybe_hint("status_reason_layout_edit")
            return
        if self._phase != PHASE_NEED_MOVE:
            reason = "status_reason_need_dice" if self._phase == PHASE_NEED_DICE else "status_reason_need_start"
            if self._phase == PHASE_GAME_OVER:
                reason = "status_reason_game_over"
            self._maybe_hint(reason)
            return
        agent = self.controller.red_agent if self.controller.state.turn is Player.RED else self.controller.blue_agent
        apply_move = self.mode_var.get() == "play" or self.auto_apply_var.get()
        if agent is None:
            self._set_status_key("human_turn")
            return
        self._set_status_key("ai_thinking", level="info")
        self.root.update_idletasks()
        self.root.after(10, lambda: self._do_ai_move(apply_move))

    def _do_ai_move(self, apply_move: bool) -> None:
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
        self._refresh_ui_state()
        if self.edit_mode_var.get():
            self._on_edit_square_click(r, c)
            return
        if self._board_block_reason:
            self._maybe_hint(self._board_block_reason)
            return
        if self._phase != PHASE_NEED_MOVE:
            reason = "status_reason_need_dice" if self._phase == PHASE_NEED_DICE else "status_reason_need_start"
            if self._phase == PHASE_GAME_OVER:
                reason = "status_reason_game_over"
            self._maybe_hint(reason)
            return
        if engine.is_terminal(self.controller.state):
            self._log(t("game_over", self.lang))
            self._set_status_key("game_over", level="warning")
            return
        if self._is_ai_turn():
            self._log(t("ai_turn_wait", self.lang))
            self._set_status_key("ai_turn_wait", level="warning")
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

    def _on_toggle_edit_mode(self) -> None:
        self.selected = None
        self._clear_highlights()
        self._refresh_board()
        if self.edit_mode_var.get():
            self._set_status_key("layout_edit_on")
        else:
            self._set_status_key("status_ready")
        self._refresh_ui_state()

    def _on_edit_side(self) -> None:
        """Handle layout edit side changes without disrupting the UI."""
        self.selected = None
        self._clear_highlights()
        self._refresh_board()
        if self.edit_mode_var.get():
            self._set_status_key("layout_edit_on")
        else:
            self._set_status_key("status_ready")

    def _on_edit_square_click(self, r: int, c: int) -> None:
        side = self.edit_side_var.get()
        try:
            piece_id = int(self.edit_piece_var.get())
        except ValueError:
            self._set_status_text(t("layout_piece_invalid", self.lang), level="error")
            return
        allowed = self.red_start_cells if side == "R" else self.blue_start_cells
        opponent = "B" if side == "R" else "R"
        if (r, c) not in allowed:
            self._set_status_text(t("layout_zone_error", self.lang), level="error")
            return
        for color, layout in self.edit_layouts.items():
            for pid, coord in layout.items():
                if coord == (r, c) and (color != side or pid != piece_id):
                    self._set_status_text(
                        t("layout_overlap_error", self.lang).format(square=rc_to_sq(r, c)), level="error"
                    )
                    return
        self.edit_layouts[opponent] = {
            pid: coord for pid, coord in self.edit_layouts[opponent].items() if coord != (r, c)
        }
        self.edit_layouts[side][piece_id] = (r, c)
        self._set_status_text(
            t("layout_piece_set", self.lang).format(color=side, piece=piece_id, square=rc_to_sq(r, c)),
            level="success",
        )
        self._refresh_board()

    def _clear_selected_piece(self) -> None:
        side = self.edit_side_var.get()
        try:
            piece_id = int(self.edit_piece_var.get())
        except ValueError:
            self._set_status_text(t("layout_piece_invalid", self.lang), level="error")
            return
        if piece_id in self.edit_layouts[side]:
            self.edit_layouts[side].pop(piece_id, None)
            self._set_status_text(t("layout_piece_cleared", self.lang), level="info")
            self._refresh_board()

    def _clear_side(self) -> None:
        side = self.edit_side_var.get()
        self.edit_layouts[side].clear()
        self._set_status_text(t("layout_side_cleared", self.lang), level="info")
        self._refresh_board()

    def _mirror_layout(self) -> None:
        if not self.edit_layouts["R"]:
            self._set_status_text(t("layout_mirror_missing", self.lang), level="warning")
            return
        mirrored: Dict[int, Tuple[int, int]] = {}
        for pid, (r, c) in self.edit_layouts["R"].items():
            target = (engine.BOARD_SIZE - 1 - r, engine.BOARD_SIZE - 1 - c)
            if target not in self.blue_start_cells:
                self._set_status_text(t("layout_zone_error", self.lang), level="error")
                return
            mirrored[pid] = target
        if len(set(mirrored.values())) != len(mirrored):
            self._set_status_text(t("layout_overlap_error", self.lang).format(square=""), level="error")
            return
        self.edit_layouts["B"] = mirrored
        self._set_status_key("layout_mirrored", level="success")
        self._refresh_board()

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
        self._refresh_ui_state()
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
        if self.edit_mode_var.get():
            for r in range(engine.BOARD_SIZE):
                for c in range(engine.BOARD_SIZE):
                    self._render_cell(r, c)
            return
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
        btn = self.board_buttons[r][c]
        if self.edit_mode_var.get():
            text = ""
            bg = CELL_COLORS["empty"]
            fg = "#444444"
            if (r, c) in self.red_start_cells:
                bg = CELL_COLORS["red"]
            elif (r, c) in self.blue_start_cells:
                bg = CELL_COLORS["blue"]
            for color, layout in self.edit_layouts.items():
                for pid, coord in layout.items():
                    if coord == (r, c):
                        text = f"{color}{pid}"
                        fg = CELL_COLORS["red_border"] if color == "R" else CELL_COLORS["blue_border"]
                        bg = CELL_COLORS["red"] if color == "R" else CELL_COLORS["blue"]
                        break
            btn.configure(
                text=text,
                background=bg,
                activebackground=bg,
                foreground=fg,
                relief=tk.RAISED,
                highlightthickness=0,
            )
            return
        val = self.controller.state.board[r][c]
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
        self.dice_value_var.set(t("dice_label", self.lang).format(dice=value))
        self._refresh_ui_state()
        self._maybe_auto_step_ai()

    def _update_move_hints(self) -> None:
        if self.edit_mode_var.get():
            self.info_can_move_var.set(t("layout_edit_hint", self.lang))
            return
        if self.controller.dice is None:
            self.info_can_move_var.set("-")
            return
        try:
            legal = self.controller.legal_moves()
        except Exception:
            self.info_can_move_var.set("-")
            return
        pieces = sorted({mv.piece_id for mv in legal})
        if pieces:
            detail = ", ".join(str(p) for p in pieces)
        else:
            detail = "-"
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
    parser.add_argument("--self-check", action="store_true", help="run UI contract self-check and exit")
    args = parser.parse_args()
    if args.self_check and os.environ.get("DISPLAY") is None:
        print("UI_SELF_CHECK_SKIP: DISPLAY not set")
        sys.exit(0)

    app = EinsteinTkApp(lang=args.lang)
    app.show_screen("play")
    if args.self_check:
        app._request_board_resize(delay=0)
        stabilized_width = 0
        stabilized_height = 0
        for _ in range(200):
            app.root.update_idletasks()
            app.root.update()
            try:
                stabilized_width = app.board_frame.winfo_width()
                stabilized_height = app.board_frame.winfo_height()
            except Exception:
                stabilized_width = stabilized_height = 0
            if stabilized_width >= 300 and stabilized_height >= 300:
                break
            time.sleep(0.01)

        if hasattr(app, "_request_board_resize"):
            app._request_board_resize(delay=0)
            app.root.update_idletasks()
            app.root.update()

        errors = []
        if stabilized_width < 200 or stabilized_height < 200:
            errors.append(
                f"board_frame too small after stabilization ({stabilized_width}x{stabilized_height})"
            )

        errors.extend(app._run_ui_contract_check(stabilized_size=(stabilized_width, stabilized_height)))
        if errors:
            print("UI_SELF_CHECK_FAIL")
            try:
                print(
                    "DEBUG board_frame: ismapped=%s size=%sx%s req=%sx%s root_state=%s"
                    % (
                        app.board_frame.winfo_ismapped(),
                        app.board_frame.winfo_width(),
                        app.board_frame.winfo_height(),
                        app.board_frame.winfo_reqwidth(),
                        app.board_frame.winfo_reqheight(),
                        app.root.state(),
                    )
                )
            except Exception:
                pass
            for err in errors:
                print(err)
            app.root.destroy()
            sys.exit(1)
        print("UI_SELF_CHECK_PASS")
        app.root.destroy()
        sys.exit(0)

    app.run()


if __name__ == "__main__":
    main()
