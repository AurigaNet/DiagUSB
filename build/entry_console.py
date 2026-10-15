# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Punto de entrada de consola para el ejecutable portable (PyInstaller).

__main__.py usa imports relativos, asi que desde un script raíz hay que
importarlo como paquete para que __package__ este definido.
"""

import sys

from diagusb.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
