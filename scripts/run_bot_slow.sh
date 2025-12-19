#!/usr/bin/env bash
# Slow (aggressive) competition launcher for longer time controls.
set -euo pipefail
BUDGET_MS=${BUDGET_MS:-180}
AGENT=${AGENT:-opening-expecti}
exec python -m einstein_wtn.adapter_stdio --agent "$AGENT" --budget-ms "$BUDGET_MS" "$@"
