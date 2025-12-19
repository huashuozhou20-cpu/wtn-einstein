"""Simple bilingual strings for the Tkinter UI."""
from __future__ import annotations

from typing import Dict, List

LANG_ZH: Dict[str, str] = {
    "window_title": "爱恩施坦棋 - 人机对战",
    "language_label": "语言",
    "language_en": "English",
    "language_zh": "中文",
    "game_group": "对局",
    "new_game": "新开局",
    "save_wtn": "保存棋谱",
    "mode_group": "模式",
    "mode_play": "对战模式",
    "mode_advise": "建议模式",
    "auto_apply": "自动执行建议",
    "agents_group": "智能体",
    "red_agent": "红方",
    "blue_agent": "蓝方",
    "layouts_red": "红方布局(可选)",
    "layouts_blue": "蓝方布局(可选)",
    "dice_group": "骰子",
    "roll_dice": "掷骰子",
    "set_dice": "设置",
    "dice_value": "当前骰子",
    "input_group": "走法输入",
    "enter_move": "粘贴/输入走法",
    "apply": "应用",
    "ai_group": "AI / 建议",
    "ai_move": "AI / 建议走法",
    "info_turn": "回合",
    "info_dice": "骰子",
    "info_can_move": "可走棋子",
    "info_last_move": "上一步",
    "info_ai_suggestion": "AI 建议",
    "move_log": "走法记录",
    "copy_last": "复制上一步",
    "no_last_move": "暂无走法",
    "turn_label": "回合: {turn}",
    "dice_label": "骰子: {dice}",
    "targets": "可落点: {targets}",
    "piece_blocked": "骰子={dice} 时该棋子无合法落点",
    "select_own_piece": "请选择当前阵营的棋子",
    "illegal_destination": "非法落点",
    "illegal_move": "非法走法: {reason}",
    "text_move_error": "文本走法错误: {error}",
    "game_over": "对局结束",
    "winner": "胜者: {winner}",
    "dice_needed": "请先掷骰或设置骰子",
    "ai_turn_wait": "当前是 AI 回合，等待或切换到建议模式",
    "agents_changed": "更换了 AI，请重新开局生效",
    "new_game_started": "已开始新对局",
    "saved_wtn": "已保存棋谱到 {path}",
    "status_error_prefix": "错误: {msg}",
    "status_ready": "状态正常",
    "human_turn": "当前玩家为人类，请直接在棋盘点击走子",
    "advised_move": "建议: {move}",
    "you_can_move": "可移动棋子: {pieces}",
    "nearest_piece": "骰子棋子缺失，最近可走: {pieces}",
    "copy_done": "已复制到剪贴板",
}

LANG_EN: Dict[str, str] = {
    "window_title": "Einstein WTN - Human vs AI",
    "language_label": "Language",
    "language_en": "English",
    "language_zh": "中文",
    "game_group": "Game",
    "new_game": "New Game",
    "save_wtn": "Save WTN",
    "mode_group": "Mode",
    "mode_play": "Play",
    "mode_advise": "Advise",
    "auto_apply": "Auto apply advice",
    "agents_group": "Agents",
    "red_agent": "Red agent",
    "blue_agent": "Blue agent",
    "layouts_red": "Red layout (optional)",
    "layouts_blue": "Blue layout (optional)",
    "dice_group": "Dice",
    "roll_dice": "Roll dice",
    "set_dice": "Set",
    "dice_value": "Current dice",
    "input_group": "Move input",
    "enter_move": "Enter/Paste move",
    "apply": "Apply",
    "ai_group": "AI / Advice",
    "ai_move": "AI / Advise move",
    "info_turn": "Turn",
    "info_dice": "Dice",
    "info_can_move": "Pieces you can move",
    "info_last_move": "Last move",
    "info_ai_suggestion": "AI Suggestion",
    "move_log": "Move log",
    "copy_last": "Copy last move",
    "no_last_move": "No moves yet",
    "turn_label": "Turn: {turn}",
    "dice_label": "Dice: {dice}",
    "targets": "Targets: {targets}",
    "piece_blocked": "This piece cannot move with dice={dice}",
    "select_own_piece": "Select one of your own pieces",
    "illegal_destination": "Illegal destination",
    "illegal_move": "Illegal move: {reason}",
    "text_move_error": "Text move error: {error}",
    "game_over": "Game over",
    "winner": "Winner: {winner}",
    "dice_needed": "Roll or set the dice first",
    "ai_turn_wait": "AI turn is active; wait or switch to advice mode",
    "agents_changed": "Agents changed; start a new game to apply.",
    "new_game_started": "New game started",
    "saved_wtn": "Saved WTN to {path}",
    "status_error_prefix": "Error: {msg}",
    "status_ready": "Ready",
    "human_turn": "Current player is human; pick a move on the board.",
    "advised_move": "Advised: {move}",
    "you_can_move": "You can move: {pieces}",
    "nearest_piece": "Dice piece missing; nearest available: {pieces}",
    "copy_done": "Copied to clipboard",
}


_LANG_MAP: Dict[str, Dict[str, str]] = {"zh": LANG_ZH, "en": LANG_EN}


def t(key: str, lang: str) -> str:
    """Translate a key for the provided language or raise when missing."""

    if lang not in _LANG_MAP:
        raise ValueError(f"Unsupported language '{lang}'")
    table = _LANG_MAP[lang]
    if key not in table:
        raise ValueError(f"Missing translation for key '{key}'")
    return table[key]


def available_langs() -> List[str]:
    return list(_LANG_MAP.keys())
