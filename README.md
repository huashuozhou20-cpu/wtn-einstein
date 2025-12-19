# Einstein WTN

A minimal, testable implementation of the WTN Einstein board game with simple agents and a CLI runner.

## Project Layout
- `src/einstein_wtn/` — game types, engine logic, agents, and CLI runner.
- `tests/` — pytest suite covering movement candidates, boundary moves, capture handling, terminal detection, RNG determinism, and layout/search behavior.
- `.github/workflows/ci.yml` — CI for Python 3.11.

## Rules Summary
- Board: 5×5 grid, coordinates `(r, c)` with `r=0` at the top and `c=0` at the left.
- Red starts in six cells `(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)`; Blue starts in `(4,4),(4,3),(4,2),(3,4),(3,3),(2,4)`.
- Each side owns pieces numbered 1–6. Opening placement is any permutation within its start cells.
- Each turn rolls a die (1–6) to pick the piece id to move. If that id is gone, the closest lower and/or closest higher surviving ids may move.
- Red moves one step right, down, or down-right. Blue moves one step left, up, or up-left. Landing on any piece captures it (friendly fire allowed).
- Win: Red reaches `(4,4)` or captures all blue pieces; Blue reaches `(0,0)` or captures all red pieces. Draws do not occur.

## Development
Install dependencies and run tests:

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest -q
```

Run a sample game:

```bash
python -m einstein_wtn.runner --mode game --red heuristic --blue random --seed 42
```

Use the expectiminimax agent and specify layouts explicitly (comma-separated permutations of 1..6) if desired:

```bash
  python -m einstein_wtn.runner --mode game --red expecti --blue heuristic --seed 3 --red-layout "1,2,3,4,5,6" --blue-layout "6,5,4,3,2,1"
  ```

## GUI Human vs AI
- Launch the Tkinter UI:
  ```bash
  python -m einstein_wtn.ui_tk
  ```
- Choose Red/Blue agents (`human`/`heuristic`/`expecti`/`opening-expecti`/`random`) plus mode:
  - **play**: humans move their side, AI moves the other side automatically when you click **AI / Advise move**.
  - **advise**: enter the opponent move manually, then request an advised reply (optionally auto-apply).
- Dice controls: **Roll dice** for a random 1–6 or **Set dice** to enter a specific value (useful for analysis/replay).
- Move input: click a piece belonging to the side to move, then click a highlighted legal destination; the board updates after each move.
- Text move entry: paste WTN-style snippets such as `12:5;(B3,D2)`, `(R5,C3)`, or `B3 D2` into the **Enter move (WTN)** box; dice in the text must match the current die roll.
- Layout controls: optional comma-separated layout orders (e.g., `1,2,3,4,5,6`) let you pin openings; otherwise agents pick their own.
- WTN saving: **Save WTN** writes the current game (layouts + moves) to a timestamped `.wtn.txt` file, embedding the chosen agent names in comments.

## Competition Stdio Adapter
- A line-oriented adapter suitable for on-site events is available via:
  ```bash
  python -m einstein_wtn.adapter_stdio --budget-ms 50
  ```
- Protocol:
  - Input:
    - `INIT <player> <layout_optional>`
    - `STATE <turn> <dice> <board_csv_25>`
    - `GO`
- Output: `MOVE <piece_id> <to_r> <to_c>` on stdout (one line per `GO`).
  - Invalid input produces `ERROR <message>` and exits with a non-zero code.
- The adapter enforces its own deadline (`--budget-ms` defaults to 50 ms) and falls back to the lightweight heuristic agent if the primary search encounters errors or proposes an illegal move. Human-readable logs are printed to stderr for turn/dice/move tracing.

### 现场操作速查
- 快速启动（短时钟、防守性预算）：
  ```bash
  scripts/run_bot_fast.sh
  ```
- 慢速启动（长时钟、更激进搜索）：
  ```bash
  scripts/run_bot_slow.sh
  ```
- 可选参数：
  - `--agent` 切换主力（`random`/`heuristic`/`expecti`/`opening-expecti`）。
  - `--budget-ms` 调整单步搜索预算（脚本默认 `60`/`180`，可通过环境变量 `BUDGET_MS` 覆盖）。
  - `--quiet` 仅在 stderr 打印必要错误，stdout 始终只包含 `MOVE/ERROR` 协议行。
  - `--save-wtn path` 开启落盘，崩溃时也能保留已走棋谱便于复盘。
  - 所有参数可直接改脚本环境变量或追加到命令行，无需修改代码。

## WTN Notation (record & replay)
- Coordinates map columns `A..E` and rows `1..5` to 0-based `(r, c)` (e.g., `A1` = `(0,0)`, `E5` = `(4,4)`).
- A WTN file can include optional `#` comment lines, two layout lines (`R:` then `B:`), and one move per line like `1:5;(R5,C3)`.
- Save a completed game from the runner:
  ```bash
  python -m einstein_wtn.runner --mode game --red heuristic --blue random --seed 1 --save-wtn game.wtn.txt
  ```
- Replay a saved record:
  ```bash
  python -m einstein_wtn.replay --file tests/data/sample.wtn.txt --verbose
  ```

## Opening / Layout Search
- The `layoutsearch` agent selects stronger openings by quickly sampling and evaluating layouts before the game starts.
- Example: play with layoutsearch as Red versus heuristic Blue:
  ```bash
  python -m einstein_wtn.runner --mode game --red layoutsearch --blue heuristic --seed 5
  ```
  Or benchmark it:
  ```bash
  python -m einstein_wtn.tournament --games 200 --red layoutsearch --blue heuristic --seed 0 --stats
  ```

### Hybrid Opening + Expectiminimax
- The `opening-expecti` agent uses layoutsearch for openings and expectiminimax for moves.
- Example benchmarks:
  ```bash
  python -m einstein_wtn.tournament --games 200 --red opening-expecti --blue heuristic --seed 0 --stats
  python -m einstein_wtn.tournament --games 200 --red heuristic --blue opening-expecti --seed 0 --stats
  ```

## Benchmark / Tournament
- Run 200 games expecti vs heuristic (quiet by default):
  ```bash
  python -m einstein_wtn.tournament --games 200 --red expecti --blue heuristic --seed 1
  ```
- Run expecti mirror match with search stats:
  ```bash
  python -m einstein_wtn.tournament --games 200 --red expecti --blue expecti --stats --seed 2
  ```
