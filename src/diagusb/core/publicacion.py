# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Publicacion reproducible del kit: verificacion de artefactos y notas.

Este modulo no descarga, no firma y no publica nada por si solo. Comprueba
que un kit ya armado coincide con su ``SHA256SUMS.txt``, que incluye los
archivos obligatorios y que no lleva ``__pycache__`` ni rutas peligrosas.
Tambien genera las notas de publicacion a partir del CHANGELOG real y de los
hashes calculados de los artefactos, sin inventar versiones ni URLs.

Falla cerrado: cualquier diferencia de hash, archivo faltante o ruta fuera del
kit se informa como fallo y el comando termina con codigo distinto de cero.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import date
from pathlib import Path

_RE_VERSION = re.compile(r'__version__\s*=\s*"([^"]+)"')
_RE_VERSION_VALIDA = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ARCHIVOS_OBLIGATORIOS = (
    "python/python.exe",
    "manifiesto_hashes.json",
    "src/diagusb/__main__.py",
    "src/diagusb/static/index.html",
    "src/diagusb/packages/impresion/manifest.json",
    "src/collectors/_common.ps1",
    "tools/tools.manifest.json",
    "LIVE_USB.md",
    "LICENSE",
    "LEGAL.md",
    "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md",
)

# Carpetas que el kit crea al usarse: no forman parte del artefacto publicado.
_PREFIJOS_IGNORADOS = (
    "reports/",
    "config/",
    "tools/downloads/",
)


def sha256_archivo(ruta: str | Path, bloque: int = 1024 * 1024) -> str:
    """SHA-256 de un archivo, leido por bloques."""
    digest = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(bloque), b""):
            digest.update(trozo)
    return digest.hexdigest()


def sha256_flujo(flujo, bloque: int = 1024 * 1024) -> str:
    """SHA-256 de un flujo binario ya abierto (por ejemplo, un miembro ZIP)."""
    digest = hashlib.sha256()
    for trozo in iter(lambda: flujo.read(bloque), b""):
        digest.update(trozo)
    return digest.hexdigest()


def version_declarada(raiz: str | Path) -> str:
    """Lee ``__version__`` de ``src/diagusb/_version.py``."""
    ruta = Path(raiz) / "src" / "diagusb" / "_version.py"
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encontro {ruta}")
    texto = ruta.read_text(encoding="utf-8")
    coincidencia = _RE_VERSION.search(texto)
    if not coincidencia:
        raise ValueError(f"No se pudo leer __version__ de {ruta}")
    version = coincidencia.group(1).strip()
    if not _RE_VERSION_VALIDA.match(version):
        raise ValueError(f"Version declarada con formato inesperado: {version!r}")
    return version


def validar_tag(tag: str, version: str) -> dict:
    """Comprueba que el tag sea ``v<version>`` o ``v<version>-rcN``."""
    tag = str(tag or "").strip()
    version = str(version or "").strip()
    if not _RE_VERSION_VALIDA.match(version):
        raise ValueError(f"Version con formato inesperado: {version!r}")
    if not tag:
        raise ValueError("Falta el tag.")
    if not tag.startswith("v"):
        raise ValueError(f"El tag debe empezar con 'v': {tag!r}")
    resto = tag[1:]
    if resto == version:
        return {"version": version, "tag": tag, "candidata": False}
    if re.fullmatch(re.escape(version) + r"-rc\d+", resto):
        return {"version": version, "tag": tag, "candidata": True}
    raise ValueError(
        f"El tag {tag!r} no coincide con 'v{version}' ni con 'v{version}-rcN'."
    )


def seccion_changelog(texto: str, version: str) -> dict:
    """Extrae del CHANGELOG los cambios que se publican ahora.

    Se prefiere ``## [Sin publicar]`` porque contiene los cambios posteriores a
    la ultima version publicada; si no existe, se usa ``## [<version>]``. En el
    primer caso se marca ``pendiente`` para que las notas pidan renombrar la
    seccion al etiquetar.
    """
    lineas = str(texto).splitlines()
    encabezados: list[tuple[int, str]] = []
    for indice, linea in enumerate(lineas):
        coincidencia = re.match(r"^## \[([^\]]+)\]", linea)
        if coincidencia:
            encabezados.append((indice, coincidencia.group(1).strip()))

    def cuerpo(desde: int, hasta: int) -> str:
        return "\n".join(lineas[desde:hasta]).strip()

    def construir(posicion: int, pendiente: bool) -> dict:
        indice, titulo = encabezados[posicion]
        fin = encabezados[posicion + 1][0] if posicion + 1 < len(encabezados) else len(lineas)
        return {
            "titulo": titulo,
            "cuerpo": cuerpo(indice + 1, fin),
            "pendiente": pendiente,
        }

    for posicion, (_, titulo) in enumerate(encabezados):
        if titulo.casefold() == "sin publicar":
            return construir(posicion, True)
    for posicion, (_, titulo) in enumerate(encabezados):
        if titulo == version:
            return construir(posicion, False)
    raise ValueError(
        f"El CHANGELOG no tiene una seccion '## [{version}]' ni '## [Sin publicar]'."
    )


def _artefacto(ruta: str | Path) -> dict:
    archivo = Path(ruta)
    if not archivo.is_file():
        raise FileNotFoundError(f"No existe el artefacto: {archivo}")
    return {
        "nombre": archivo.name,
        "ruta": str(archivo.resolve()),
        "bytes": archivo.stat().st_size,
        "sha256": sha256_archivo(archivo),
    }


def _normalizar_artefactos(artefactos) -> list[dict]:
    if isinstance(artefactos, (str, Path)):
        artefactos = [artefactos]
    normalizados: list[dict] = []
    vistos: set[str] = set()
    for elemento in artefactos or []:
        if isinstance(elemento, dict):
            datos = dict(elemento)
            for campo in ("nombre", "bytes", "sha256"):
                if campo not in datos:
                    raise ValueError(f"Al artefacto le falta el campo {campo!r}.")
            if not _RE_SHA256.match(str(datos["sha256"]).lower()):
                raise ValueError(f"SHA-256 invalido para {datos['nombre']!r}.")
            datos["sha256"] = str(datos["sha256"]).lower()
        else:
            datos = _artefacto(elemento)
        if datos["nombre"] in vistos:
            raise ValueError(f"Artefacto repetido: {datos['nombre']!r}")
        vistos.add(datos["nombre"])
        normalizados.append(datos)
    if not normalizados:
        raise ValueError("No se indico ningun artefacto para publicar.")
    return normalizados


def generar_notas(version: str, tag: str, artefactos, changelog_texto: str,
                  fecha: str | None = None) -> dict:
    """Genera el texto de notas y sus metadatos a partir de datos reales."""
    datos_tag = validar_tag(tag, version)
    fecha = (fecha or date.today().isoformat()).strip()
    if not _RE_FECHA.match(fecha):
        raise ValueError(f"Fecha con formato inesperado: {fecha!r} (use AAAA-MM-DD).")
    artefactos = _normalizar_artefactos(artefactos)
    seccion = seccion_changelog(changelog_texto, version)
    if not seccion["cuerpo"]:
        raise ValueError(
            f"La seccion {seccion['titulo']!r} del CHANGELOG esta vacia."
        )

    lineas = [
        f"# DiagUSB {version} - notas de publicacion",
        "",
        f"- Fecha: {fecha}",
        f"- Tag: {datos_tag['tag']}",
        f"- Version declarada: {version}",
        f"- Candidata: {'si' if datos_tag['candidata'] else 'no'}",
        f"- Seccion del CHANGELOG: {seccion['titulo']}",
        "",
    ]
    if seccion["pendiente"]:
        lineas += [
            f"> Nota: el texto proviene de la seccion «{seccion['titulo']}» del CHANGELOG. "
            f"Al etiquetar la version, renombrela a [{version}] para que las proximas "
            "notas citen la seccion exacta.",
            "",
        ]

    lineas += [
        "## Artefactos publicados",
        "",
        "| Archivo | Tamano (bytes) | SHA-256 |",
        "|---|---|---|",
    ]
    for artefacto in artefactos:
        lineas.append(
            f"| `{artefacto['nombre']}` | {artefacto['bytes']} | `{artefacto['sha256']}` |"
        )
    lineas += [
        "",
        "## Verificacion",
        "",
        "1. Descargue los artefactos en una misma carpeta.",
        "2. Calcule el SHA-256 de cada archivo: `Get-FileHash -Algorithm SHA256 .\\<archivo>`.",
        "3. Compare el resultado con la tabla anterior y con `SHA256SUMS.txt`.",
        "4. Para el kit, valide ademas su estructura interna:",
        "",
        "```powershell",
        f"python -m diagusb verificar-kit DiagUSB-kit-{version}.zip --estricto",
        "```",
        "",
        "## Cambios",
        "",
        seccion["cuerpo"],
        "",
        "## Alcance y limites",
        "",
        "- El kit portable incluye la distribucion embebida oficial de Python y el "
        "codigo fuente; no incluye ejecutables propios ni binarios de terceros.",
        "- Windows 10 validado; Windows 11 aun no probado en hardware real.",
        "- Los artefactos no llevan firma Authenticode: la integridad se comprueba "
        "con SHA-256. El interprete `python\\python.exe` del kit si esta firmado "
        "por Python Software Foundation.",
        "- El ejecutable opcional de PyInstaller y el instalador, si se publican, "
        "tampoco estan firmados.",
        "- DiagUSB no envia datos a servidores propios y no incluye telemetria.",
        "",
    ]
    texto = "\n".join(lineas)
    metadatos = {
        "version": version,
        "tag": datos_tag["tag"],
        "candidata": datos_tag["candidata"],
        "fecha": fecha,
        "seccion_changelog": seccion["titulo"],
        "changelog_pendiente": seccion["pendiente"],
        "artefactos": [
            {
                "nombre": a["nombre"],
                "bytes": a["bytes"],
                "sha256": a["sha256"],
            }
            for a in artefactos
        ],
    }
    return {"texto": texto, "metadatos": metadatos}


def escribir_metadatos(metadatos: dict, ruta: str | Path) -> Path:
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(metadatos, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destino


def _normalizar_rel(rel: str) -> str:
    texto = str(rel).replace("\\", "/").strip()
    while texto.startswith("./"):
        texto = texto[2:]
    return texto


def _rel_peligrosa(rel: str) -> bool:
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return True
    return any(parte in ("", ".", "..") for parte in rel.split("/"))


def _ignorado(rel: str, prefijos: tuple[str, ...] = _PREFIJOS_IGNORADOS) -> bool:
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in prefijos)


def _prohibido(rel: str) -> bool:
    return (
        rel.endswith((".pyc", ".pyo"))
        or rel.startswith("__pycache__/")
        or "/__pycache__/" in rel
    )


def _leer_sums(texto: str) -> list[tuple[str, str]]:
    entradas: list[tuple[str, str]] = []
    for numero, linea in enumerate(str(texto).splitlines(), 1):
        if not linea.strip():
            continue
        partes = linea.split(None, 1)
        if len(partes) != 2:
            raise ValueError(f"Linea {numero} invalida en SHA256SUMS.txt: {linea!r}")
        sha, rel = partes[0].strip().lower(), _normalizar_rel(partes[1])
        if not _RE_SHA256.match(sha):
            raise ValueError(
                f"Linea {numero} de SHA256SUMS.txt no tiene un SHA-256 valido: {sha!r}"
            )
        entradas.append((sha, rel))
    if not entradas:
        raise ValueError("SHA256SUMS.txt esta vacio.")
    return entradas


def _resultado_base(ruta: Path, tipo: str, estricto: bool) -> dict:
    return {
        "ruta": str(ruta.resolve()),
        "tipo": tipo,
        "estricto": bool(estricto),
        "archivos_listados": 0,
        "archivos_encontrados": 0,
        "correctos": 0,
        "fallos": [],
        "faltantes": [],
        "extras": [],
        "ignorados": [],
        "prohibidos": [],
    }


def _completar(res: dict) -> dict:
    res["ok"] = not (
        res["fallos"]
        or res["faltantes"]
        or res["prohibidos"]
        or (res["estricto"] and res["extras"])
    )
    return res


def _rel_raiz(rel: str, prefijo: str) -> str:
    """Quita el prefijo de empaquetado (``DiagUSB/``) para comparar."""
    if prefijo and rel.startswith(prefijo):
        return rel[len(prefijo):]
    return rel


def _verificar_carpeta(raiz: Path, entradas: list[tuple[str, str]],
                       estricto: bool, prefijo: str = "") -> dict:
    res = _resultado_base(raiz, "carpeta", estricto)
    res["archivos_listados"] = len(entradas)
    esperados: set[str] = set()
    for sha, rel in entradas:
        if _rel_peligrosa(rel):
            res["fallos"].append(f"ruta peligrosa en SHA256SUMS.txt: {rel!r}")
            continue
        rel_raiz = _rel_raiz(rel, prefijo)
        if _rel_peligrosa(rel_raiz) or rel_raiz == "SHA256SUMS.txt":
            res["fallos"].append("SHA256SUMS.txt no puede listarse a si mismo")
            continue
        esperados.add(rel_raiz)
        archivo = raiz / rel_raiz
        if not archivo.is_file():
            res["faltantes"].append(rel_raiz)
            continue
        if sha256_archivo(archivo) != sha:
            res["fallos"].append(f"hash distinto en {rel_raiz}")
            continue
        res["correctos"] += 1

    reales: set[str] = set()
    for archivo in raiz.rglob("*"):
        if archivo.is_file():
            reales.add(archivo.relative_to(raiz).as_posix())
    res["archivos_encontrados"] = len(reales)

    for rel in sorted(reales - esperados - {"SHA256SUMS.txt"}):
        if _prohibido(rel):
            res["prohibidos"].append(rel)
        elif _ignorado(rel):
            res["ignorados"].append(rel)
        else:
            res["extras"].append(rel)

    res["faltantes"].extend(
        rel for rel in ARCHIVOS_OBLIGATORIOS
        if rel not in reales and rel not in res["faltantes"]
    )
    return _completar(res)


def _verificar_zip(ruta: Path, estricto: bool) -> dict:
    res = _resultado_base(ruta, "zip", estricto)
    try:
        archivo_zip = zipfile.ZipFile(ruta)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"El archivo no es un ZIP valido: {ruta}") from exc

    with archivo_zip:
        nombres = [n for n in archivo_zip.namelist() if not n.endswith("/")]
        candidatos = [
            n for n in nombres
            if n == "SHA256SUMS.txt" or n.endswith("/SHA256SUMS.txt")
        ]
        if len(candidatos) != 1:
            raise ValueError(
                "El ZIP debe contener exactamente un SHA256SUMS.txt "
                f"(se encontraron {len(candidatos)})."
            )
        nombre_sums = candidatos[0]
        prefijo = nombre_sums[: -len("SHA256SUMS.txt")]
        with archivo_zip.open(nombre_sums) as fh:
            texto = fh.read().decode("utf-8-sig")
        entradas = _leer_sums(texto)
        res["archivos_listados"] = len(entradas)

        esperados: set[str] = set()
        for sha, rel in entradas:
            if _rel_peligrosa(rel):
                res["fallos"].append(f"ruta peligrosa en SHA256SUMS.txt: {rel!r}")
                continue
            rel_raiz = _rel_raiz(rel, prefijo)
            if _rel_peligrosa(rel_raiz) or rel_raiz == "SHA256SUMS.txt":
                res["fallos"].append("SHA256SUMS.txt no puede listarse a si mismo")
                continue
            esperados.add(rel_raiz)
            nombre = rel if (not prefijo or rel.startswith(prefijo)) else prefijo + rel
            if nombre not in nombres:
                res["faltantes"].append(rel_raiz)
                continue
            with archivo_zip.open(nombre) as fh:
                obtenido = sha256_flujo(fh)
            if obtenido != sha:
                res["fallos"].append(f"hash distinto en {rel_raiz}")
                continue
            res["correctos"] += 1

        reales: set[str] = set()
        for nombre in nombres:
            if prefijo and nombre.startswith(prefijo):
                reales.add(nombre[len(prefijo):])
            elif nombre == nombre_sums:
                continue
            else:
                reales.add(nombre)
        res["archivos_encontrados"] = len(reales)

        for rel in sorted(reales - esperados - {"SHA256SUMS.txt"}):
            if _prohibido(rel):
                res["prohibidos"].append(rel)
            elif _ignorado(rel):
                res["ignorados"].append(rel)
            else:
                res["extras"].append(rel)

    res["faltantes"].extend(
        rel for rel in ARCHIVOS_OBLIGATORIOS
        if rel not in reales and rel not in res["faltantes"]
    )
    return _completar(res)


def verificar_kit(ruta: str | Path, estricto: bool = False) -> dict:
    """Verifica un kit en carpeta o ZIP contra su ``SHA256SUMS.txt``.

    No escribe nada. En modo ``estricto`` tambien falla si hay archivos que no
    figuran en el manifiesto, salvo los que crea el propio kit al usarse
    (``config/``, ``reports/`` y ``tools/downloads/``).
    """
    original = Path(ruta)
    if not original.exists():
        raise FileNotFoundError(f"No existe la ruta indicada: {original}")
    if original.is_dir():
        raiz = original
        if not (raiz / "SHA256SUMS.txt").is_file():
            anidada = raiz / "DiagUSB"
            if (anidada / "SHA256SUMS.txt").is_file():
                raiz = anidada
            else:
                raise FileNotFoundError(
                    f"No se encontro SHA256SUMS.txt en {original} ni en {anidada}"
                )
        texto = (raiz / "SHA256SUMS.txt").read_text(encoding="utf-8-sig")
        entradas = _leer_sums(texto)
        candidato = raiz.name + "/"
        prefijo = (
            candidato
            if entradas and all(rel.startswith(candidato) for _, rel in entradas)
            else ""
        )
        return _verificar_carpeta(raiz, entradas, estricto, prefijo)
    if original.is_file():
        return _verificar_zip(original, estricto)
    raise ValueError(f"La ruta no es un archivo ni una carpeta: {original}")


def formatear_verificacion(resultado: dict) -> str:
    """Texto legible del resultado de ``verificar_kit``."""
    lineas = [
        f"Kit: {resultado['ruta']} ({resultado['tipo']})",
        (
            f"Listados: {resultado['archivos_listados']} · "
            f"encontrados: {resultado['archivos_encontrados']} · "
            f"correctos: {resultado['correctos']}"
        ),
        f"Modo estricto: {'si' if resultado['estricto'] else 'no'}",
        "",
    ]
    for mensaje in resultado["fallos"]:
        lineas.append(f"[FALLA] {mensaje}")
    for rel in resultado["faltantes"]:
        lineas.append(f"[FALTA] {rel}")
    for rel in resultado["prohibidos"]:
        lineas.append(f"[PROHIBIDO] {rel}")
    for rel in resultado["extras"]:
        etiqueta = "EXTRA" if resultado["estricto"] else "EXTRA (no falla sin --estricto)"
        lineas.append(f"[{etiqueta}] {rel}")
    for rel in resultado["ignorados"]:
        lineas.append(f"[IGNORADO] {rel} (datos locales del kit)")
    if not lineas[-1]:
        lineas.append("[OK] sin diferencias")
    lineas += [
        "",
        "RESULTADO: " + ("OK" if resultado["ok"] else "FALLO"),
    ]
    return "\n".join(lineas)
