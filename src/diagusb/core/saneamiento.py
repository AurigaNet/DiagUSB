# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Saneamiento de datos sensibles antes de persistirlos o mostrarlos."""

from __future__ import annotations

import unicodedata
from typing import Any

MARCA = "[OCULTO]"

_ETIQUETAS = tuple(
    "".join(
        c for c in unicodedata.normalize("NFKD", texto.casefold())
        if not unicodedata.combining(c)
    )
    for texto in (
        "clave",
        "contraseña",
        "password",
        "passwd",
        "psk",
        "secret",
        "token",
        "key content",
        "contenido de la clave",
    )
)


def _normalizar(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(texto).casefold())
        if not unicodedata.combining(c)
    )


def _es_sensible(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return any(etiqueta in normalizado for etiqueta in _ETIQUETAS)


def _redactar_texto(texto: str) -> str:
    lineas = texto.splitlines(keepends=True)
    if not lineas:
        return texto
    salida = []
    for linea in lineas:
        fin = ""
        contenido = linea
        if linea.endswith("\r\n"):
            contenido, fin = linea[:-2], "\r\n"
        elif linea.endswith(("\n", "\r")):
            contenido, fin = linea[:-1], linea[-1]
        salida.append((MARCA if _es_sensible(contenido) else contenido) + fin)
    return "".join(salida)


def redactar(obj: Any) -> Any:
    """Devuelve una copia con valores y líneas sensibles reemplazados por MARCA."""
    if isinstance(obj, dict):
        salida = {}
        for clave, valor in obj.items():
            if _es_sensible(str(clave)):
                salida[clave] = MARCA
            else:
                salida[clave] = redactar(valor)
        return salida
    if isinstance(obj, list):
        return [redactar(valor) for valor in obj]
    if isinstance(obj, tuple):
        return tuple(redactar(valor) for valor in obj)
    if isinstance(obj, str):
        return _redactar_texto(obj)
    return obj
