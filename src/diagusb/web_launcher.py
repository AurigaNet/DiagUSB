#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Lanzador rapido del servidor web de DiagUSB."""

import sys
from pathlib import Path

# Agregar src al path (padre de diagusb/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from diagusb.web_server import run_server

if __name__ == "__main__":
    print("Iniciando servidor web de DiagUSB...")
    run_server()
