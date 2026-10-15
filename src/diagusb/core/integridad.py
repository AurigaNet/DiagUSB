# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Verificacion de integridad de los colectores (.ps1) mediante SHA-256.

El manifiesto ``manifiesto_hashes.json`` lo genera ``scripts/generar_manifiesto.py``
durante la construccion y se empaqueta dentro de ``_internal``. Antes de ejecutar
un colector, el motor compara el SHA-256 del archivo contra el manifiesto; si no
coincide, no lo ejecuta y reporta ``Integridad: el colector fue modificado``.

En modo desarrollo (sin manifiesto) los colectores se ejecutan igual y se avisa
una sola vez por consola.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MANIFIESTO_NOMBRE = "manifiesto_hashes.json"
MENSAJE_MODIFICADO = "Integridad: el colector fue modificado"

_manifiesto: dict | None = None
_cargado = False
_avisado = False


def _rutas_candidatas() -> list[Path]:
    """Rutas donde puede estar el manifiesto (congelado y desarrollo)."""
    rutas: list[Path] = []
    base_frozen = getattr(sys, "_MEIPASS", None)
    if base_frozen:
        rutas.append(Path(base_frozen) / MANIFIESTO_NOMBRE)
    if getattr(sys, "frozen", False):
        rutas.append(Path(sys.executable).resolve().parent / MANIFIESTO_NOMBRE)
    # Raiz del repositorio: core/integridad.py -> core, diagusb, src, raiz
    rutas.append(Path(__file__).resolve().parents[3] / MANIFIESTO_NOMBRE)
    return rutas


def cargar_manifiesto() -> dict | None:
    """Devuelve ``{nombre_archivo: sha256}`` o ``None`` si no hay manifiesto."""
    global _manifiesto, _cargado
    if _cargado:
        return _manifiesto
    _cargado = True
    for ruta in _rutas_candidatas():
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        archivos = data.get("archivos") if isinstance(data, dict) else None
        if isinstance(archivos, dict):
            _manifiesto = archivos
            return _manifiesto
    _manifiesto = None
    return _manifiesto


def hash_archivo(ruta: str | Path) -> str:
    """SHA-256 (hex) del contenido de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def localizar_common(script_path: str | Path) -> Path | None:
    """Busca ``_common.ps1`` subiendo por los directorios (igual que los .ps1)."""
    directorio = Path(script_path).resolve().parent
    while True:
        candidato = directorio / "collectors" / "_common.ps1"
        if candidato.is_file():
            return candidato
        padre = directorio.parent
        if padre == directorio:
            return None
        directorio = padre


def verificar(ruta: str | Path) -> tuple[bool, str]:
    """Verifica el hash de ``ruta`` contra el manifiesto.

    Devuelve ``(True, "")`` si es valido o si no hay manifiesto (desarrollo), y
    ``(False, motivo)`` si el archivo fue modificado.
    """
    global _avisado
    manifiesto = cargar_manifiesto()
    if manifiesto is None:
        if not _avisado:
            print("[DiagUSB] Aviso: no hay manifiesto de hashes; los "
                  "colectores se ejecutan sin verificar (modo desarrollo).")
            _avisado = True
        return True, ""
    esperado = manifiesto.get(Path(ruta).name)
    if esperado is None:
        # Archivo no listado: no es posible verificarlo, se permite.
        return True, ""
    try:
        real = hash_archivo(ruta)
    except OSError as e:
        return False, f"Integridad: no se pudo leer el colector ({e})"
    if real != esperado:
        return False, MENSAJE_MODIFICADO
    return True, ""
