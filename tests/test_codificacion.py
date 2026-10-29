# SPDX-License-Identifier: GPL-3.0-or-later
"""Codificacion: todo archivo de texto debe decodificar como UTF-8 limpia."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXTENSIONES = {".py", ".js", ".json", ".md", ".html", ".css", ".txt", ".ini", ".ps1"}
# Secuencias de mojibake (escritas con escapes para que este archivo no las contenga).
MOJIBAKE = ("\u00c3", "\u00c2", "\ufffd")


def _archivos_texto():
    carpetas = [RAIZ / "src", RAIZ / "tests", RAIZ / "docs"]
    carpetas += [p for p in RAIZ.iterdir() if p.is_file() and p.suffix == ".md"]
    vistos = set()
    for carpeta in carpetas:
        if not carpeta.exists():
            continue
        if carpeta.is_file():
            candidatos = [carpeta]
        else:
            candidatos = sorted(carpeta.rglob("*"))
        for ruta in candidatos:
            if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
                continue
            if ruta in vistos:
                continue
            vistos.add(ruta)
            yield ruta


def test_codificacion_utf8_limpia():
    problemas = []
    for ruta in _archivos_texto():
        try:
            texto = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            problemas.append(f"{ruta}: no decodifica como UTF-8 ({error})")
            continue
        for secuencia in MOJIBAKE:
            if secuencia in texto:
                problemas.append(f"{ruta}: contiene secuencia invalida {secuencia!r}")
                break
    if problemas:
        # Mensaje con JSON para que las rutas con backslashes queden claras.
        raise AssertionError(
            "Archivos sin UTF-8 limpia:\n" + json.dumps(problemas, ensure_ascii=False, indent=2)
        )
