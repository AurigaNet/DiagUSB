# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Suite de pruebas para DiagUSB."""

import sys
from pathlib import Path

# Agregar src al path para imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
