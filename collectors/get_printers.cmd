:: SPDX-License-Identifier: GPL-3.0-or-later
:: Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get_printers.ps1" %*
pause