"""UI contract constants to ensure essential widgets remain available."""

from __future__ import annotations

from typing import List

REQUIRED_WIDGET_ATTRS: List[str] = [
    "board_frame",
    "control_frame",
    "btn_new_game",
    "btn_save_wtn",
    "cb_red_agent",
    "cb_blue_agent",
    "rb_mode_play",
    "rb_mode_advise",
    "chk_auto_apply",
    "btn_roll_dice",
    "entry_set_dice",
    "btn_apply_dice",
    "entry_move_text",
    "btn_apply_move",
    "btn_ai_move",
    "btn_copy_last_move",
]

REQUIRED_MAPPED_WIDGETS: List[str] = [
    "board_frame",
    "control_frame",
    "btn_new_game",
    "cb_red_agent",
    "btn_roll_dice",
    "entry_set_dice",
    "entry_move_text",
    "btn_ai_move",
]
