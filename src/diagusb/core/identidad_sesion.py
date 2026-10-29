# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Identidad del equipo, calculada una vez por sesion y pegada a cada analisis.

Lee get_hardware.ps1 (paquete inventario_general) una sola vez, verifica su
integridad y devuelve un resumen SIN seriales ni MAC crudos: nombre, id, id
corto, nivel, calidad y aviso. Si la lectura falla lo dice (nivel "ninguno"):
nunca devuelve un id vacio en silencio.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from . import identidad, integridad

_SCRIPT = (Path(__file__).resolve().parent.parent / "packages"
           / "inventario_general" / "collectors" / "get_hardware.ps1")
_LOCK = threading.Lock()
_CACHE = {"valor": None, "hasta": 0.0}
_REINTENTO_S = 60.0
_CAMPOS_REGISTRO = ("id", "computer_name", "id_corto", "nivel", "calidad")


def _nombre_local() -> str:
    return os.environ.get("COMPUTERNAME", "")


def _fallo(motivo: str) -> dict:
    return {
        "id": "", "id_corto": "", "nivel": "ninguno", "calidad": "nula",
        "aviso": ("No se pudo leer el hardware del equipo (" + motivo
                  + "): este an\u00e1lisis queda sin ID."),
        "computer_name": _nombre_local(), "error": True,
    }


def _resumen_de(raw):
    if not isinstance(raw, dict):
        return None
    datos = raw.get("data")
    items = datos if isinstance(datos, list) else [datos]
    results = [{"data": x, "context": raw.get("context")}
               for x in items if isinstance(x, dict)]
    ident = identidad.identificar(
        identidad.componentes_de_results(results),
        identidad.respaldos_de_results(results))
    ident["computer_name"] = identidad.nombre_equipo(results) or _nombre_local()
    return ident


def _calcular(runner) -> dict:
    try:
        ok, _motivo = integridad.verificar(_SCRIPT)
        if ok:
            comun = integridad.localizar_common(_SCRIPT)
            if comun is not None:
                ok, _motivo = integridad.verificar(comun)
        if not ok:
            return _fallo("integridad del colector")
        raw = runner(str(_SCRIPT), timeout=60)
        resumen = _resumen_de(raw)
        if resumen is None:
            return _fallo("sin respuesta")
        estado = str((raw.get("query") or {}).get("status") or "ok")
        if resumen["nivel"] == "ninguno" and estado != "ok":
            return _fallo("estado " + estado)
        return resumen
    except Exception as exc:  # nunca debe romper un analisis
        return _fallo(type(exc).__name__)


def para_diag(runner) -> dict:
    """Identidad de la sesion: se calcula una vez; los fallos se reintentan."""
    with _LOCK:
        ahora = time.monotonic()
        if _CACHE["valor"] is not None and ahora < _CACHE["hasta"]:
            return dict(_CACHE["valor"])
        valor = _calcular(runner)
        espera = _REINTENTO_S if valor.get("error") else float("inf")
        _CACHE["valor"] = valor
        _CACHE["hasta"] = time.monotonic() + espera
        return dict(valor)


def resumen_registro(ident) -> dict:
    """Campos de identidad que van al registro (nunca seriales ni MAC)."""
    if not isinstance(ident, dict):
        return {}
    return {campo: ident.get(campo, "") for campo in _CAMPOS_REGISTRO}