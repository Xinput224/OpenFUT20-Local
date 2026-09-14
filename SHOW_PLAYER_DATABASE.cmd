@echo off
setlocal
cd /d "%~dp0"
py -3.13 "%~dp0tools\player_database_info.py"
echo.
pause
