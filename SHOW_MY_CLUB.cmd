@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title OpenFUT20 - My Club
py -3.13 "%~dp0tools\club_profile.py" --show
pause
