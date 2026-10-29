#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Genera ``build/version_info.txt`` (recurso de version de Windows).

El archivo lo consume PyInstaller mediante el parametro ``version=`` del spec.
La version se toma de ``src/diagusb/_version.py``; el resto de los metadatos del
producto son fijos. El archivo se escribe en ASCII puro (los caracteres no ASCII
van escapados) para no depender de la codificacion con que se lea.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PY = ROOT / "src" / "diagusb" / "_version.py"
DESTINO = ROOT / "build" / "version_info.txt"
DESTINO_GUI = ROOT / "build" / "version_info_gui.txt"

COMPANY_NAME = "AurigaNet"
PRODUCT_NAME = "DiagUSB"
FILE_DESCRIPTION = "Kit de diagnóstico para soporte TI en Windows"
FILE_DESCRIPTION_GUI = "Aplicación de diagnóstico para soporte TI en Windows"
LEGAL_COPYRIGHT = "Copyright 2026 Daniel Ricardo Novoa"
ORIGINAL_FILENAME = "diagusb.exe"
ORIGINAL_FILENAME_GUI = "DiagUSB.exe"
INTERNAL_NAME = "diagusb"
INTERNAL_NAME_GUI = "DiagUSB"

# Idioma/codigo de pagina de la tabla de cadenas (0409 = en-US, 04B0 = Unicode).
TABLA_IDIOMA = "040904B0"
TRADUCCION = "[1033, 1200]"


def leer_version() -> str:
    texto = VERSION_PY.read_text(encoding="utf-8")
    coincidencia = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", texto)
    if not coincidencia:
        print(f"ERROR: no se encontro __version__ en {VERSION_PY}", file=sys.stderr)
        raise SystemExit(1)
    return coincidencia.group(1)


def tupla_version(version: str) -> tuple[int, int, int, int]:
    numeros: list[int] = []
    for parte in version.split("."):
        digito = re.match(r"\d+", parte)
        numeros.append(int(digito.group()) if digito else 0)
    while len(numeros) < 4:
        numeros.append(0)
    return (numeros[0], numeros[1], numeros[2], numeros[3])


def escapar(texto: str) -> str:
    return texto.encode("unicode_escape").decode("ascii")


def contenido(version: str, gui: bool = False) -> str:
    mayor, menor, parche, revision = tupla_version(version)
    filevers = f"({mayor}, {menor}, {parche}, {revision})"
    descripcion = FILE_DESCRIPTION_GUI if gui else FILE_DESCRIPTION
    original = ORIGINAL_FILENAME_GUI if gui else ORIGINAL_FILENAME
    interno = INTERNAL_NAME_GUI if gui else INTERNAL_NAME
    campos = [
        ("CompanyName", COMPANY_NAME),
        ("FileDescription", descripcion),
        ("FileVersion", version),
        ("InternalName", interno),
        ("LegalCopyright", LEGAL_COPYRIGHT),
        ("OriginalFilename", original),
        ("ProductName", PRODUCT_NAME),
        ("ProductVersion", version),
    ]
    filas = "\n".join(
        f"          StringStruct('{nombre}', '{escapar(valor)}'),"
        for nombre, valor in campos
    )
    return (
        "# Recurso de version de Windows para PyInstaller.\n"
        "# Archivo generado por scripts/generar_version_info.py; no editar a mano.\n"
        "# SPDX-License-Identifier: GPL-3.0-or-later\n"
        "# Copyright (C) 2026 Daniel Ricardo Novoa\n"
        "\n"
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={filevers},\n"
        f"    prodvers={filevers},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(\n"
        f"        '{TABLA_IDIOMA}',\n"
        "        [\n"
        f"{filas}\n"
        "        ])\n"
        "    ]),\n"
        f"    VarFileInfo([VarStruct('Translation', {TRADUCCION})])\n"
        "  ]\n"
        ")\n"
    )


def main() -> int:
    version = leer_version()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(contenido(version), encoding="ascii", newline="\n")
    DESTINO_GUI.write_text(contenido(version, gui=True), encoding="ascii", newline="\n")
    print(f"Version info escrita: {DESTINO} (version {version})")
    print(f"Version info GUI escrita: {DESTINO_GUI} (version {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
