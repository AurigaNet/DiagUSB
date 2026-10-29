#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Lanzador de DiagUSB para el ejecutable PyInstaller."""

from diagusb.web_server import run_server

if __name__ == "__main__":
    run_server()
