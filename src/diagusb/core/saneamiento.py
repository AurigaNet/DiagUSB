# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Saneamiento de datos sensibles antes de persistirlos o mostrarlos."""

from __future__ import annotations

import re
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


def _enmascarar_mac(valor: str) -> str:
    """Enmascara una MAC: deja los dos primeros pares y oculta el resto."""
    partes = re.split(r"[-:]", valor)
    if len(partes) == 6 and all(re.fullmatch(r"[0-9A-Fa-f]{2}", p) for p in partes):
        sep = "-" if "-" in valor else ":"
        return sep.join(partes[:2] + ["***"] * 4)
    apretado = re.sub(r"[-:]", "", valor)
    if len(apretado) == 12 and re.fullmatch(r"[0-9A-Fa-f]+", apretado):
        return apretado[:4] + "********"
    return MARCA


def _enmascarar_ip(valor: str) -> str:
    """Enmascara una IPv4: oculta los dos últimos octetos."""
    partes = valor.split(".")
    if len(partes) == 4 and all(p.isdigit() for p in partes):
        return ".".join(partes[:2] + ["***", "***"])
    return MARCA


def redactar(obj: Any) -> Any:
    """Devuelve una copia con valores y líneas sensibles reemplazados por MARCA.

    El enmascarado de direcciones MAC (_enmascarar_mac) y de direcciones IP
    (_enmascarar_ip) se conserva para la exportación de informes (Fase 4).
    Al guardar o comparar instantáneas locales se escriben y comparan los
    valores reales: si se enmascaran al guardar, la comparación nunca vería
    un cambio real de gateway_mac ni de dhcp_server.
    """
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
