@echo off
set BUDGET_MS=%BUDGET_MS%
if "%BUDGET_MS%"=="" set BUDGET_MS=180
set AGENT=%AGENT%
if "%AGENT%"=="" set AGENT=opening-expecti
python -m einstein_wtn.adapter_stdio --agent %AGENT% --budget-ms %BUDGET_MS% %*
