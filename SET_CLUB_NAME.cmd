@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenFUT20 - Set Club Name

echo IMPORTANT: Close FIFA 20 and run STOP_LOCAL_FUT.cmd before editing an existing save.
echo.
py -3.13 "%~dp0tools\club_profile.py" --set-club-name
if errorlevel 1 (
  echo.
  echo [ERROR] Club name was not changed.
  pause
  exit /b 1
)
echo.
pause
