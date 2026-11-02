@echo off
chcp 65001 >nul
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Construye el instalador portable de DiagUSB:
REM   1. empaqueta la aplicacion en modo carpeta (dist\DiagUSB)
REM   2. genera el instalador con Inno Setup en la raiz (Ejecutar DiagUSB.exe)
REM Uso: scripts\build_instalador.cmd

cd /d "%~dp0.."

echo.
echo ============================================================
echo  DiagUSB - Construccion del instalador
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller no esta instalado.
    exit /b 1
)

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo ERROR: no se encontro Inno Setup 6 - ISCC.exe.
    echo Instalelo con: winget install --id JRSoftware.InnoSetup -e
    exit /b 1
)

echo Generando manifiesto de integridad de colectores...
python scripts\generar_manifiesto.py
if errorlevel 1 (
    echo ERROR: no se pudo generar el manifiesto de hashes.
    exit /b 1
)

echo Generando recurso de version del ejecutable...
python scripts\generar_version_info.py
if errorlevel 1 (
    echo ERROR: no se pudo generar la informacion de version.
    exit /b 1
)

echo Empaquetando la aplicacion en modo carpeta...
python -m PyInstaller build\ejecutar_diagusb_onedir.spec --noconfirm --clean --distpath dist
if errorlevel 1 (
    echo ERROR: fallo el empaquetado con PyInstaller.
    exit /b 1
)

echo Generando el instalador...
"%ISCC%" /Qp installer\DiagUSB.iss
if errorlevel 1 (
    echo ERROR: fallo la construccion del instalador.
    exit /b 1
)

if not exist "Ejecutar DiagUSB.exe" (
    echo ERROR: no se genero "Ejecutar DiagUSB.exe" en la raiz.
    exit /b 1
)

echo.
echo ============================================================
echo  Construccion exitosa
echo  Instalador: Ejecutar DiagUSB.exe (raiz del proyecto)
echo ============================================================
exit /b 0




