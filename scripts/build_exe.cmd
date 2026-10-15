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

echo Ejecutando PyInstaller...
python -m PyInstaller build\diagusb.spec --noconfirm
if errorlevel 1 (
    echo ERROR: la construccion fallo.
    exit /b 1
)

echo.
echo ============================================================
echo  Construccion exitosa
echo  CLI:     dist\diagusb\diagusb.exe
echo  Servidor: dist\diagusb\diagusb.exe web   (o python -m diagusb.web_server)
echo ============================================================
exit /b 0
