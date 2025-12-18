# Agent Instructions
- Scope: entire repository.
- Implement WTN 爱恩施坦棋 exactly per rules below; keep rule comments near logic and update this file if rules change.
- Preserve clear, concise docstrings/comments that explain movement, capture, win conditions, and timing.
- Testing uses pytest; prefer deterministic behavior when seeding RNG.

## Game Rules (mirror in code comments when relevant)
- Board: 5×5 with coordinates (r, c); r=0 top, c=0 left.
- Red start cells: (0,0),(0,1),(0,2),(1,0),(1,1),(2,0).
- Blue start cells: (4,4),(4,3),(4,2),(3,4),(3,3),(2,4).
- Each side has six pieces numbered 1..6; opening layout is any permutation in its start cells.
- Turn begins with rolling a die (1..6) to choose the piece id to move.
- If that id is captured, allowed movers are the closest lower-id survivor (if any) and/or the closest higher-id survivor (if any).
- Red moves one step per turn to the right, down, or down-right. Blue moves one step left, up, or up-left. Destination may capture any piece present (including friendly).
- Red wins by reaching (4,4) or capturing all blue pieces; Blue wins by reaching (0,0) or capturing all red pieces. Draws do not occur.
- Runner enforces optional time controls (default 240s per side); flag falls lose immediately.
