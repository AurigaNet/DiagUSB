@echo off
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Script para construir el ejecutable de DiagUSB

echo.
echo ============================================================
echo  DiagUSB - Construccion de ejecutable
echo ============================================================
echo.

REM Verificar que Python este disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    pause
    exit /b 1
)

REM Verificar que pyinstaller este instalado
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller no esta instalado.
    echo Instale con: pip install pyinstaller
    pause
    exit /b 1
)

REM Crear directorio de salida si no existe
if not exist "dist" mkdir dist

echo Ejecutando PyInstaller...
echo.

REM Ejecutar build
pyinstaller build\diagusb.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ERROR: La construccion fallo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Construccion exitosa!
echo  El ejecutable esta en: dist\diagusb\
echo ============================================================
echo.
echo Para probar, ejecute: dist\diagusb\diagusb.exe
echo.

pause
