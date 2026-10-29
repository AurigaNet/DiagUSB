# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Estado y verificacion de las imagenes externas del pendrive de arranque.

Este modulo solo lee el manifiesto ``tools/tools.manifest.json`` y, cuando se
lo pide, calcula el SHA-256 de los archivos que el tecnico ya descargo. Nunca
descarga, formatea, particiona ni escribe en el pendrive.

Falla cerrado: una herramienta solo se considera verificada si tiene URL,
version, SHA-256, licencia y dominio oficial, y si la URL pertenece a ese
dominio. Las herramientas sin datos oficiales quedan excluidas y se muestran
con su motivo.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from diagusb.core import rutas

NOMBRE_MANIFIESTO = "tools.manifest.json"
VARIABLE_ENTORNO = "DIAGUSB_LIVE_USB_MANIFEST"
_ESTADOS_CONOCIDOS = ("verificado", "excluido", "pendiente")
_CAMPOS_VERIFICADOS = (
    ("official_domain", "dominio oficial"),
    ("url", "URL de descarga"),
    ("version", "version"),
    ("sha256", "SHA-256"),
    ("license", "licencia"),
    ("file", "nombre de archivo"),
)


def _raiz_repositorio() -> Path:
    # core/live_usb.py -> core, diagusb, src, raiz
    return Path(__file__).resolve().parents[3]


def _candidatos_manifiesto() -> list[Path]:
    candidatos: list[Path] = []
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve().parent
        candidatos.append(exe / "tools" / NOMBRE_MANIFIESTO)
        candidatos.append(exe / "_internal" / "tools" / NOMBRE_MANIFIESTO)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidatos.append(Path(meipass) / "tools" / NOMBRE_MANIFIESTO)
    else:
        candidatos.append(_raiz_repositorio() / "tools" / NOMBRE_MANIFIESTO)
    candidatos.append(rutas.dir_base() / "tools" / NOMBRE_MANIFIESTO)
    return candidatos


def ruta_manifiesto() -> Path:
    """Devuelve la ruta del manifiesto, sin exigir que exista."""
    entorno = os.environ.get(VARIABLE_ENTORNO)
    if entorno:
        return Path(entorno)
    candidatos = _candidatos_manifiesto()
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    return candidatos[0]


def cargar_manifiesto(ruta: str | Path | None = None) -> dict:
    """Carga y valida la estructura basica del manifiesto."""
    archivo = Path(ruta) if ruta else ruta_manifiesto()
    if not archivo.is_file():
        raise FileNotFoundError(
            f"No se encontro el manifiesto de live USB: {archivo}"
        )
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"El manifiesto no es JSON valido: {exc}") from exc
    if not isinstance(datos, dict):
        raise ValueError("El manifiesto debe ser un objeto JSON.")
    if datos.get("schema_version") != 1:
        raise ValueError("Version de esquema no soportada (se esperaba 1).")
    herramientas = datos.get("tools")
    if not isinstance(herramientas, list) or not herramientas:
        raise ValueError("El manifiesto no contiene herramientas.")
    for herramienta in herramientas:
        if not isinstance(herramienta, dict):
            raise ValueError("Cada herramienta debe ser un objeto JSON.")
        if not (herramienta.get("name") or herramienta.get("nombre")):
            raise ValueError("Hay una herramienta sin nombre.")
    return datos


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _sha_valido(valor: str) -> bool:
    return len(valor) == 64 and all(c in "0123456789abcdefABCDEF" for c in valor)


def _url_oficial(url: str, dominio: str) -> bool:
    try:
        partes = urlparse(url)
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    dominio = _texto(dominio).lower().lstrip(".")
    if partes.scheme not in ("http", "https") or not host or not dominio:
        return False
    return host == dominio or host.endswith("." + dominio)


def evaluar_herramienta(herramienta: dict) -> dict:
    """Evalua una entrada del manifiesto y explica por que no esta lista."""
    nombre = _texto(herramienta.get("name") or herramienta.get("nombre")) or "(sin nombre)"
    estado = _texto(herramienta.get("estado")).lower() or "pendiente"
    motivo = _texto(herramienta.get("motivo"))
    motivos: list[str] = []

    if estado == "excluido":
        if not motivo:
            motivos.append("excluida sin motivo documentado")
        return {
            "nombre": nombre,
            "estado": "excluido",
            "lista": False,
            "motivos": motivos,
            "motivo": motivo,
            "version": _texto(herramienta.get("version")),
            "url": _texto(herramienta.get("url")),
            "archivo": _texto(herramienta.get("file")),
            "sha256": _texto(herramienta.get("sha256")).lower(),
            "licencia": _texto(herramienta.get("license")),
            "fuente": _texto(herramienta.get("source")),
            "checksum_url": _texto(herramienta.get("checksum_url")),
        }

    if estado not in _ESTADOS_CONOCIDOS:
        motivos.append(f"estado desconocido: {estado}")
    elif estado != "verificado":
        motivos.append(f"estado no verificado: {estado}")

    for campo, etiqueta in _CAMPOS_VERIFICADOS:
        if not _texto(herramienta.get(campo)):
            motivos.append(f"falta {etiqueta}")

    sha = _texto(herramienta.get("sha256")).lower()
    if sha and not _sha_valido(sha):
        motivos.append("el SHA-256 no tiene 64 caracteres hexadecimales")

    url = _texto(herramienta.get("url"))
    dominio = _texto(herramienta.get("official_domain"))
    if url and dominio and not _url_oficial(url, dominio):
        motivos.append("la URL no pertenece al dominio oficial declarado")

    archivo = _texto(herramienta.get("file"))
    if archivo and Path(archivo).name != archivo:
        motivos.append("el nombre de archivo no puede contener carpetas")

    return {
        "nombre": nombre,
        "estado": estado,
        "lista": not motivos,
        "motivos": motivos,
        "motivo": motivo,
        "version": _texto(herramienta.get("version")),
        "url": url,
        "archivo": archivo,
        "sha256": sha,
        "licencia": _texto(herramienta.get("license")),
        "fuente": _texto(herramienta.get("source")),
        "checksum_url": _texto(herramienta.get("checksum_url")),
    }


def estado_live_usb(ruta: str | Path | None = None) -> dict:
    """Resumen del manifiesto: que esta verificado y que queda excluido."""
    datos = cargar_manifiesto(ruta)
    herramientas = [evaluar_herramienta(t) for t in datos["tools"]]
    verificadas = [h for h in herramientas if h["estado"] == "verificado"]
    listas = [h for h in verificadas if h["lista"]]
    excluidas = [h for h in herramientas if h["estado"] == "excluido"]
    pendientes = [h for h in herramientas if h["estado"] not in ("verificado", "excluido")]
    return {
        "schema_version": datos.get("schema_version"),
        "revisado_en": _texto(datos.get("generated_at")),
        "herramientas": herramientas,
        "verificadas": len(verificadas),
        "listas": len(listas),
        "excluidas": len(excluidas),
        "pendientes": len(pendientes),
        "todo_verificado": bool(verificadas) and len(listas) == len(verificadas),
    }


def _sha256_archivo(archivo: Path, bloque: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(archivo, "rb") as fh:
        while True:
            trozo = fh.read(bloque)
            if not trozo:
                break
            digest.update(trozo)
    return digest.hexdigest()


def verificar_archivos(carpeta: str | Path,
                       ruta: str | Path | None = None) -> dict:
    """Comprueba el SHA-256 de las imagenes descargadas. Solo lectura."""
    base = Path(carpeta)
    if not base.is_dir():
        raise FileNotFoundError(f"No existe la carpeta indicada: {base}")
    estado = estado_live_usb(ruta)
    resultados = []
    for herramienta in estado["herramientas"]:
        if herramienta["estado"] != "verificado":
            continue
        archivo = herramienta["archivo"]
        resultado = {
            "nombre": herramienta["nombre"],
            "archivo": archivo,
            "version": herramienta["version"],
            "sha256_esperado": herramienta["sha256"],
            "sha256_obtenido": "",
            "presente": False,
            "coincide": False,
            "error": "",
        }
        if not herramienta["lista"]:
            resultado["error"] = "entrada incompleta en el manifiesto"
            resultados.append(resultado)
            continue
        ruta_archivo = base / archivo
        if not ruta_archivo.is_file():
            resultado["error"] = "no esta en la carpeta indicada"
            resultados.append(resultado)
            continue
        resultado["presente"] = True
        resultado["sha256_obtenido"] = _sha256_archivo(ruta_archivo)
        resultado["coincide"] = (
            resultado["sha256_obtenido"] == herramienta["sha256"]
        )
        if not resultado["coincide"]:
            resultado["error"] = "el SHA-256 no coincide"
        resultados.append(resultado)

    fallos = sum(1 for r in resultados if not r["coincide"])
    return {
        "carpeta": str(base.resolve()),
        "resultados": resultados,
        "correctos": len(resultados) - fallos,
        "fallos": fallos,
        "todo_correcto": bool(resultados) and fallos == 0,
    }


def formatear_estado(estado: dict) -> str:
    """Texto legible para la consola."""
    lineas = ["Live USB - imagenes externas"]
    if estado.get("revisado_en"):
        lineas.append(f"Manifiesto revisado: {estado['revisado_en']}")
    lineas.append("")
    for h in estado.get("herramientas", []):
        if h["estado"] == "excluido":
            lineas.append(f"[EXCLUIDA] {h['nombre']}: {h['motivo'] or 'sin motivo'}")
        elif h["lista"]:
            lineas.append(
                f"[OK] {h['nombre']} {h['version']}: {h['archivo']} "
                f"({h['licencia']})"
            )
        else:
            lineas.append(f"[PENDIENTE] {h['nombre']}: " + "; ".join(h["motivos"]))
    lineas.append("")
    lineas.append(
        f"Verificadas: {estado.get('listas', 0)} de {estado.get('verificadas', 0)}. "
        f"Excluidas: {estado.get('excluidas', 0)}. "
        f"Pendientes: {estado.get('pendientes', 0)}."
    )
    return "\n".join(lineas)


def formatear_verificacion(verificacion: dict) -> str:
    """Texto legible de la verificacion de archivos."""
    lineas = [f"Carpeta: {verificacion['carpeta']}", ""]
    for r in verificacion.get("resultados", []):
        if r["coincide"]:
            lineas.append(
                f"[OK] {r['nombre']} {r['version']}: {r['archivo']}"
            )
        elif r["presente"]:
            lineas.append(
                f"[HASH NO COINCIDE] {r['nombre']}: {r['archivo']}\n"
                f"  esperado: {r['sha256_esperado']}\n"
                f"  obtenido: {r['sha256_obtenido']}"
            )
        else:
            lineas.append(
                f"[FALTA] {r['nombre']}: {r['archivo']} ({r['error']})"
            )
    lineas.append("")
    lineas.append(
        f"Correctos: {verificacion.get('correctos', 0)}. "
        f"Fallos: {verificacion.get('fallos', 0)}."
    )
    return "\n".join(lineas)
