# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Escritura y lectura segura de archivos JSON de DiagUSB.

La escritura es atomica: se escribe un ``<ruta>.tmp`` en la misma carpeta, se
fuerza el volcado a disco con ``flush`` + ``os.fsync`` y recien entonces se
reemplaza el destino con ``os.replace``. Si el JSON en disco esta corrupto, se
preserva renombrandolo a ``<nombre>.corrupto-<YYYYMMDD_HHMMSS>`` en lugar de
sobrescribirlo en silencio.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def _marca_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def preservar_corrupto(ruta: Path) -> Path | None:
    """Renombra un archivo corrupto a ``<nombre>.corrupto-<fecha>``.

    Devuelve la ruta nueva, o ``None`` si no se pudo preservar.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    destino = ruta.with_name(f"{ruta.name}.corrupto-{_marca_tiempo()}")
    contador = 1
    while destino.exists():
        destino = ruta.with_name(f"{ruta.name}.corrupto-{_marca_tiempo()}_{contador}")
        contador += 1
    try:
        os.replace(ruta, destino)
    except OSError:
        return None
    return destino


def escribir_json_atomico(ruta: Path, datos, *, indent: int = 2) -> None:
    """Escribe ``datos`` como JSON de forma atomica (tmp + fsync + replace)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=indent)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def leer_json(ruta: Path, *, preservar: bool = False):
    """Lee un JSON. Devuelve ``None`` si falta o esta corrupto.

    Si ``preservar`` es True y el archivo existe pero es invalido, se renombra
    a ``<nombre>.corrupto-<fecha>`` antes de devolver ``None``.
    """
    ruta = Path(ruta)
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        if preservar:
            preservar_corrupto(ruta)
        return None
