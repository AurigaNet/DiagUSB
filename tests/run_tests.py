#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Ejecuta TODAS las pruebas de DiagUSB con pytest.

Uso:
    python tests/run_tests.py
    python tests/run_tests.py -k reglas
    python tests/run_tests.py --manual

El script descubre todos los archivos ``test_*.py`` de ``tests/`` y delega en
pytest, de modo que no exista una lista fija de suites que pueda quedar
desactualizada. Devuelve el mismo codigo de salida que pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

SPDX = "SPDX-License-Identifier: GPL-3.0-or-later"


def _preparar_entorno() -> Path:
    """Agrega ``src`` al path para que ``import diagusb`` funcione sin instalar."""
    tests_dir = Path(__file__).resolve().parent
    raiz = tests_dir.parent
    src = raiz / "src"
    for ruta in (str(src), str(raiz)):
        if ruta not in sys.path:
            sys.path.insert(0, ruta)
    return raiz


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: ejecuta pytest sobre todos los test_*.py."""
    raiz = _preparar_entorno()
    argumentos = list(sys.argv[1:] if argv is None else argv)

    try:
        import pytest
    except ImportError:
        print("ERROR: falta pytest. Instale las dependencias de desarrollo con:")
        print("  python -m pip install -r requirements-dev.txt")
        return 2

    if "--manual" in argumentos:
        argumentos.remove("--manual")
        import os

        os.environ["DIAGUSB_PRUEBAS_MANUALES"] = "1"

    destinos = sorted(str(p) for p in (raiz / "tests").glob("test_*.py"))
    if not destinos:
        print("ERROR: no se encontraron archivos tests/test_*.py")
        return 2

    print("=" * 60)
    print("SUITE DE PRUEBAS - DiagUSB")
    print(f"Archivos: {len(destinos)}")
    print("=" * 60)

    return int(
        pytest.main(
            [
                "-q",
                "--rootdir",
                str(raiz),
                "-c",
                str(raiz / "pytest.ini"),
                *destinos,
                *argumentos,
            ]
        )
    )


if __name__ == "__main__":
    sys.exit(main())
