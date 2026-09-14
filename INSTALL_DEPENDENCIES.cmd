@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenFUT20 - Install Dependencies

echo ============================================================
echo  OpenFUT20 Local - Dependency Setup
echo ============================================================
echo.
py -3.13 -c "import sys,struct; assert sys.version_info[:2]==(3,13) and struct.calcsize('P')*8==64" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.13 x64 is required for this parity runtime.
  echo Install Python 3.13 x64 from python.org, including the Python Launcher.
  echo.
  pause
  exit /b 1
)
echo [PASS] Python 3.13 x64

py -3.13 -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

py -3.13 -c "import cryptography,PIL; print('[PASS] cryptography + Pillow')"
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo Dependencies are ready.
pause
