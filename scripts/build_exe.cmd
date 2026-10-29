@echo off
chcp 65001 >nul
REM SPDX-License-Identifier: GPL-3.0-or-later
REM Copyright (C) 2026 Daniel Ricardo Novoa
REM Construye el ejecutable portable de DiagUSB con PyInstaller.
REM Uso: scripts\build_exe.cmd   (sin pausas, apto para automatizacion)

cd /d "%~dp0.."

echo.
echo ============================================================
echo  DiagUSB - Construccion de ejecutable portable
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no esta instalado.
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller no esta instalado. Instalando...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo ERROR: no se pudo instalar PyInstaller.
        exit /b 1
    )
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

echo Ejecutando PyInstaller...
python -m PyInstaller build\ejecutar_diagusb.spec --noconfirm --clean --distpath .
if errorlevel 1 (
    echo ERROR: la construccion fallo.
    exit /b 1
)

echo.
echo ============================================================
echo  Construccion exitosa
echo  Ejecutable: Ejecutar DiagUSB.exe (raiz del proyecto)
echo ============================================================
exit /b 0
