@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenFUT20 Local

py -3.13 -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')*8==64" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.13 x64 is required.
  echo Run INSTALL_DEPENDENCIES.cmd first.
  pause
  exit /b 1
)

py -3.13 -c "import cryptography,PIL" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python dependencies are missing.
  echo Run INSTALL_DEPENDENCIES.cmd first.
  pause
  exit /b 1
)

py -3.13 "%~dp0open_runner.py" --verify
if errorlevel 1 (
  echo [ERROR] Open runtime verification failed.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-LocalFUT.ps1" -LegitimateEA
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [ERROR] OpenFUT20 failed to start. Run COLLECT_DIAGNOSTICS.cmd and send the ZIP.
  pause
)
exit /b %RC%
