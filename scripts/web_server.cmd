@echo off
chcp 65001 >nul
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Lanzador del servidor web de DiagUSB

cd /d "%~dp0..\src"
python -m diagusb.web_server
pause
