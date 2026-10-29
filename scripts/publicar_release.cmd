:: SPDX-License-Identifier: GPL-3.0-or-later
:: Copyright (C) 2026 Daniel Ricardo Novoa
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar_release.ps1" %*
pause
