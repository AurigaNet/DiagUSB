#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Genera manifiesto_hashes.json con el SHA-256 de cada colector .ps1.

Incluye todos los ``.ps1`` de ``src/diagusb/packages/**`` y el compartido
``collectors/_common.ps1``. Por defecto el archivo se escribe en la raiz del
repositorio y PyInstaller lo empaqueta dentro de ``_internal``.

Se puede indicar una ruta de salida distinta como primer argumento (lo usa
``scripts/armar_kit.ps1`` para escribir el manifiesto dentro del kit, donde
``core/integridad.py`` lo busca en ``<raiz-del-kit>/manifiesto_hashes.json``).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / "manifiesto_hashes.json"


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    destino = Path(args[0]).resolve() if args else DESTINO

    archivos: dict[str, str] = {}
    rutas = sorted((ROOT / "src" / "diagusb" / "packages").rglob("*.ps1"))
    common = ROOT / "collectors" / "_common.ps1"
    if common.is_file():
        rutas.append(common)

    for ruta in rutas:
        nombre = ruta.name
        if nombre in archivos:
            print(f"ERROR: nombre de colector duplicado: {nombre}", file=sys.stderr)
            return 1
        archivos[nombre] = sha256(ruta)

    data = {"version": 1, "total": len(archivos), "archivos": archivos}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"Manifiesto escrito: {destino} ({len(archivos)} archivos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
