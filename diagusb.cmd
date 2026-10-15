@echo off
chcp 65001 >nul
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Lanzador principal de DiagUSB

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHONPATH=%SCRIPT_DIR%src"

echo.
echo ============================================================
echo  DiagUSB - Herramienta de Diagnostico USB
echo ============================================================
echo.

REM Verificar que Python este disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado o no esta en el PATH.
    echo Asegurese de tener Python 3.10 o superior instalado.
    pause
    exit /b 1
)

REM Ejecutar el modulo principal
python -m diagusb %*

set "EXIT_CODE=%ERRORLEVEL%"

echo.
if !EXIT_CODE! neq 0 (
    echo La ejecucion finalizo con errores (codigo: !EXIT_CODE!)
) else (
    echo La ejecucion finalizo correctamente.
)

pause
exit /b %EXIT_CODE%
