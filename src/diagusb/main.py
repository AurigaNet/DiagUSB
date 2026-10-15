# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Punto de entrada para ejecutar DiagUSB desde src/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from diagusb.__main__ import main

if __name__ == "__main__":
    main()
