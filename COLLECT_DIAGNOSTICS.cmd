@echo off
setlocal
cd /d "%~dp0"
py -3.13 "%~dp0tools\collect_diagnostics.py"
pause
