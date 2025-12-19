#!/usr/bin/env bash
# Fast (conservative) competition launcher for short clocks.
set -euo pipefail
BUDGET_MS=${BUDGET_MS:-60}
AGENT=${AGENT:-opening-expecti}
exec python -m einstein_wtn.adapter_stdio --agent "$AGENT" --budget-ms "$BUDGET_MS" "$@"
