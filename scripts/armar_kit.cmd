@echo off
chcp 65001 >nul
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Arma el kit portable de DiagUSB (Python embebido + fuente).
REM Uso: scripts\armar_kit.cmd -Salida <carpeta> [-PythonZip <zip descargado>]

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0armar_kit.ps1" %*
exit /b %errorlevel%
