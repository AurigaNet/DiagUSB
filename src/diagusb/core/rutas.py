# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Resolucion de rutas persistentes (config/ y reports/) para DiagUSB.

Congelado (PyInstaller), la carpeta de datos es la que contiene ``diagusb.exe``
(``Path(sys.executable).parent``), nunca ``_internal`` ni el directorio actual.
Si esa carpeta no es escribible (p. ej. un pendrive protegido), se usa como
respaldo ``%LOCALAPPDATA%\\DiagUSB``. En desarrollo la base es la raiz del
repositorio.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_NOMBRE_RESPALDO = "DiagUSB"

_base: Path | None = None
_usa_respaldo = False


def _raiz_repositorio() -> Path:
    # core/rutas.py -> core, diagusb, src, raiz
    return Path(__file__).resolve().parents[3]


def _dir_local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / _NOMBRE_RESPALDO


def _escribible(carpeta: Path) -> bool:
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".diagusb_prueba"
        with open(prueba, "w", encoding="utf-8") as fh:
            fh.write("ok")
        prueba.unlink()
        return True
    except OSError:
        return False


def dir_base() -> Path:
    """Carpeta contenedora: junto al exe si esta congelado, si no la raiz."""
    global _base, _usa_respaldo
    if _base is not None:
        return _base
    if getattr(sys, "frozen", False):
        candidato = Path(sys.executable).resolve().parent
    else:
        candidato = _raiz_repositorio()
    if _escribible(candidato):
        _base = candidato
        _usa_respaldo = False
    else:
        _base = _dir_local_appdata()
        _usa_respaldo = True
    return _base


def dir_config() -> Path:
    return dir_base() / "config"


def dir_reports() -> Path:
    return dir_base() / "reports"


def usa_respaldo() -> bool:
    """True si se esta usando %LOCALAPPDATA% por falta de permiso de escritura."""
    dir_base()
    return _usa_respaldo


def dir_respaldo() -> Path:
    return _dir_local_appdata()


def resetear_cache() -> None:
    """Invalida la ruta calculada (util en pruebas y en cambios de entorno)."""
    global _base, _usa_respaldo
    _base = None
    _usa_respaldo = False
