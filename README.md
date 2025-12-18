# Einstein WTN

A minimal, testable implementation of the WTN Einstein board game with simple agents and a CLI runner.

## Project Layout
- `src/einstein_wtn/` — game types, engine logic, agents, and CLI runner.
- `tests/` — pytest suite covering movement candidates, boundary moves, capture handling, terminal detection, RNG determinism, and layout/search behavior.
- `tests/` — pytest suite covering movement candidates, boundary moves, capture handling, terminal detection, and RNG determinism.
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
