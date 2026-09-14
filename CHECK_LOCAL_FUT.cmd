@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenFUT20 - Package Check

py -3.13 -c "import sys; assert sys.version_info[:2]==(3,13)" >nul 2>&1
if errorlevel 1 (
  echo [FAIL] Python 3.13 is required. Run INSTALL_DEPENDENCIES.cmd.
  pause
  exit /b 1
)

py -3.13 "%~dp0tools\check_package.py"
if errorlevel 1 (
  echo.
  echo PACKAGE CHECK FAILED
  pause
  exit /b 1
)

echo.
powershell.exe -NoProfile -Command "$bad=$false; Get-ChildItem -LiteralPath '%~dp0' -Filter *.ps1 -File | ForEach-Object { $e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$e)|Out-Null; if($e.Count){$bad=$true;Write-Host ('[FAIL] PowerShell syntax: '+$_.Name) -ForegroundColor Red;$e|ForEach-Object{Write-Host $_.Message}} else {Write-Host ('[PASS] PowerShell syntax: '+$_.Name) -ForegroundColor Green} }; if($bad){exit 1}"
if errorlevel 1 (
  echo PACKAGE CHECK FAILED
  pause
  exit /b 1
)

echo.
echo OPENFUT20 PARITY PACKAGE CHECK: PASS
pause
