import io

import pytest

from einstein_wtn import engine
from einstein_wtn.adapter_stdio import StdioAdapter
from einstein_wtn.types import Move, Player


def _board_csv(state) -> str:
    return ",".join(str(cell) for row in state.board for cell in row)


def _starter_state(turn: Player = Player.RED):
    state = engine.new_game(engine.START_RED_CELLS, engine.START_BLUE_CELLS, first=turn)
    dice = 1
    return state, dice


def _run_adapter_with_lines(lines, adapter: StdioAdapter):
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    stderr = io.StringIO()
    adapter.stdin = stdin
    adapter.stdout = stdout
    adapter.stderr = stderr
    exit_code = adapter.run()
    return exit_code, stdout.getvalue().strip(), stderr.getvalue().strip()


def test_normal_input_produces_move():
    state, dice = _starter_state()
    csv = _board_csv(state)
    adapter = StdioAdapter(budget_ms=100)
    lines = [f"INIT RED", f"STATE RED {dice} {csv}", "GO"]
    code, out, err = _run_adapter_with_lines(lines, adapter)
    assert code == 0
    assert out.startswith("MOVE ")
    parts = out.split()
    pid, r, c = int(parts[1]), int(parts[2]), int(parts[3])
    from_rc = state.pos_red[pid]
    chosen = Move(piece_id=pid, from_rc=from_rc, to_rc=(r, c))
    legal_moves = engine.generate_legal_moves(state, dice)
    assert chosen in legal_moves
    assert "turn=RED" in err


def test_exception_triggers_fallback(monkeypatch):
    class BoomAgent:
        def choose_move(self, *args, **kwargs):
            raise RuntimeError("boom")

    state, dice = _starter_state()
    csv = _board_csv(state)
    adapter = StdioAdapter(budget_ms=100, agent=BoomAgent())
    lines = ["INIT RED", f"STATE RED {dice} {csv}", "GO"]
    code, out, err = _run_adapter_with_lines(lines, adapter)
    assert code == 0
    assert out.startswith("MOVE ")
    assert "Fallback" in err


def test_illegal_input_reports_error():
    state, _ = _starter_state()
    csv = _board_csv(state)
    adapter = StdioAdapter(budget_ms=100)
    lines = ["STATE RED X " + csv, "GO"]
    code, out, err = _run_adapter_with_lines(lines, adapter)
    assert code == 1
    assert out.startswith("ERROR ")
    assert err == ""
