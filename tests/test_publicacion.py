# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from diagusb.core import publicacion

REPO = Path(__file__).resolve().parents[1]

ARCHIVOS_KIT = {
    "python/python.exe": b"interprete de prueba",
    "manifiesto_hashes.json": b"{}",
    "src/diagusb/__main__.py": b"# punto de entrada",
    "src/diagusb/static/index.html": b"<html></html>",
    "src/diagusb/packages/impresion/manifest.json": b'{"name": "impresion"}',
    "src/collectors/_common.ps1": b"# comun",
    "tools/tools.manifest.json": b'{"schema_version": 1, "tools": []}',
    "LIVE_USB.md": b"# Live USB",
    "LICENSE": b"GPL-3.0-or-later",
    "LEGAL.md": b"legal",
    "THIRD_PARTY_NOTICES.md": b"terceros",
    "CHANGELOG.md": b"changelog",
}


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _escribir_sums(raiz: Path, entradas: dict[str, bytes]) -> None:
    lineas = [
        f"{_sha(datos)}  {rel}"
        for rel, datos in sorted(entradas.items())
    ]
    (raiz / "SHA256SUMS.txt").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8")


def _crear_kit(tmp_path: Path, archivos: dict[str, bytes] | None = None) -> Path:
    raiz = tmp_path / "DiagUSB"
    datos = dict(ARCHIVOS_KIT if archivos is None else archivos)
    for rel, contenido in datos.items():
        destino = raiz / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    _escribir_sums(raiz, datos)
    return raiz


def _crear_zip(carpeta: Path, destino: Path) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in sorted(carpeta.rglob("*")):
            if archivo.is_file():
                rel = archivo.relative_to(carpeta).as_posix()
                zf.write(archivo, "DiagUSB/" + rel)
    return destino


CHANGELOG = """# Changelog

## [Sin publicar]

### Agregado

- Kit verificable y notas generadas.

## [0.1.0] - 2026-10-20

- Primera version.
"""


def test_version_declarada_del_repositorio():
    assert publicacion.version_declarada(REPO) == "0.1.0"
    with pytest.raises(FileNotFoundError):
        publicacion.version_declarada(REPO / "no-existe")


def test_validar_tag_acepta_version_y_candidata():
    assert publicacion.validar_tag("v0.1.0", "0.1.0")["candidata"] is False
    assert publicacion.validar_tag("v0.1.0-rc2", "0.1.0")["candidata"] is True
    for malo in ("0.1.0", "v0.2.0", "v0.1.0-rc", "v0.1.0-beta"):
        with pytest.raises(ValueError):
            publicacion.validar_tag(malo, "0.1.0")


def test_seccion_changelog_prefiere_sin_publicar():
    seccion = publicacion.seccion_changelog(CHANGELOG, "0.1.0")
    assert seccion["titulo"] == "Sin publicar"
    assert seccion["pendiente"] is True
    assert "Kit verificable" in seccion["cuerpo"]

    cerrado = CHANGELOG.replace("## [Sin publicar]", "## [0.2.0]")
    seccion = publicacion.seccion_changelog(cerrado, "0.2.0")
    assert seccion["titulo"] == "0.2.0"
    assert seccion["pendiente"] is False

    with pytest.raises(ValueError):
        publicacion.seccion_changelog("# Changelog\n\nSin secciones.\n", "0.1.0")


def test_generar_notas_usa_hashes_y_changelog_reales(tmp_path):
    uno = tmp_path / "DiagUSB-kit-0.1.0.zip"
    uno.write_bytes(b"kit")
    dos = tmp_path / "NOTAS-0.1.0.md"
    dos.write_bytes(b"notas")
    changelog = CHANGELOG.replace("## [Sin publicar]", "## [0.1.0]")

    generado = publicacion.generar_notas(
        "0.1.0", "v0.1.0", [uno, dos], changelog, fecha="2026-10-28")

    texto = generado["texto"]
    assert "# DiagUSB 0.1.0 - notas de publicacion" in texto
    assert "- Fecha: 2026-10-28" in texto
    assert "- Tag: v0.1.0" in texto
    assert "- Candidata: no" in texto
    assert "- Seccion del CHANGELOG: 0.1.0" in texto
    assert "Kit verificable" in texto
    assert _sha(b"kit") in texto
    assert str(len(b"kit")) in texto
    assert "no llevan firma Authenticode" in texto
    assert "Windows 11 aun no probado" in texto

    metadatos = generado["metadatos"]
    assert metadatos["version"] == "0.1.0"
    assert metadatos["artefactos"][0]["nombre"] == uno.name
    assert metadatos["artefactos"][0]["sha256"] == _sha(b"kit")
    assert metadatos["changelog_pendiente"] is False


def test_generar_notas_avisa_si_usa_sin_publicar(tmp_path):
    artefacto = tmp_path / "kit.zip"
    artefacto.write_bytes(b"x")
    generado = publicacion.generar_notas(
        "0.2.0", "v0.2.0-rc1", [artefacto], CHANGELOG, fecha="2026-10-28")
    assert "- Candidata: si" in generado["texto"]
    assert "renombrela a [0.2.0]" in generado["texto"]
    assert generado["metadatos"]["changelog_pendiente"] is True


def test_generar_notas_falla_cerrado(tmp_path):
    with pytest.raises(ValueError):
        publicacion.generar_notas("0.1.0", "v0.1.0", [], CHANGELOG)
    with pytest.raises(FileNotFoundError):
        publicacion.generar_notas(
            "0.1.0", "v0.1.0", [tmp_path / "no.zip"], CHANGELOG)
    artefacto = tmp_path / "kit.zip"
    artefacto.write_bytes(b"x")
    with pytest.raises(ValueError):
        publicacion.generar_notas(
            "0.1.0", "v0.2.0", [artefacto], CHANGELOG)
    with pytest.raises(ValueError):
        publicacion.generar_notas(
            "0.1.0", "v0.1.0", [artefacto], CHANGELOG, fecha="28-10-2026")


def test_verificar_carpeta_correcta(tmp_path):
    raiz = _crear_kit(tmp_path)
    resultado = publicacion.verificar_kit(raiz, estricto=True)
    assert resultado["ok"] is True
    assert resultado["tipo"] == "carpeta"
    assert resultado["correctos"] == len(ARCHIVOS_KIT)
    assert resultado["fallos"] == []
    assert resultado["extras"] == []


def test_verificar_carpeta_con_hash_distinto_y_faltante(tmp_path):
    raiz = _crear_kit(tmp_path)
    (raiz / "LICENSE").write_bytes(b"otra licencia")
    resultado = publicacion.verificar_kit(raiz)
    assert resultado["ok"] is False
    assert any("hash distinto en LICENSE" in f for f in resultado["fallos"])

    (raiz / "LIVE_USB.md").unlink()
    resultado = publicacion.verificar_kit(raiz)
    assert "LIVE_USB.md" in resultado["faltantes"]


def test_verificar_carpeta_extras_y_datos_locales(tmp_path):
    raiz = _crear_kit(tmp_path)
    (raiz / "suelto.txt").write_text("no listado", encoding="utf-8")
    (raiz / "reports").mkdir()
    (raiz / "reports" / "informe.pdf").write_bytes(b"%PDF")
    (raiz / "config").mkdir()
    (raiz / "config" / "entrega.json").write_text("{}", encoding="utf-8")

    flexible = publicacion.verificar_kit(raiz)
    assert flexible["ok"] is True
    assert flexible["extras"] == ["suelto.txt"]
    assert set(flexible["ignorados"]) == {
        "config/entrega.json", "reports/informe.pdf"}

    estricto = publicacion.verificar_kit(raiz, estricto=True)
    assert estricto["ok"] is False
    assert estricto["extras"] == ["suelto.txt"]


def test_verificar_prohibe_pycache(tmp_path):
    raiz = _crear_kit(tmp_path)
    cache = raiz / "src" / "diagusb" / "__pycache__"
    cache.mkdir()
    (cache / "mod.pyc").write_bytes(b"bytecode")
    resultado = publicacion.verificar_kit(raiz)
    assert resultado["ok"] is False
    assert any("__pycache__" in p for p in resultado["prohibidos"])


def test_verificar_rechaza_rutas_peligrosas(tmp_path):
    raiz = _crear_kit(tmp_path)
    externo = tmp_path / "fuera.txt"
    externo.write_bytes(b"fuera")
    with open(raiz / "SHA256SUMS.txt", "a", encoding="utf-8") as fh:
        fh.write(f"{_sha(b'fuera')}  ../fuera.txt\n")
    resultado = publicacion.verificar_kit(raiz)
    assert resultado["ok"] is False
    assert any("ruta peligrosa" in f for f in resultado["fallos"])


def test_verificar_falta_archivo_obligatorio(tmp_path):
    archivos = dict(ARCHIVOS_KIT)
    del archivos["tools/tools.manifest.json"]
    raiz = _crear_kit(tmp_path, archivos)
    resultado = publicacion.verificar_kit(raiz)
    assert resultado["ok"] is False
    assert "tools/tools.manifest.json" in resultado["faltantes"]


def test_verificar_carpeta_con_prefijo_diagusb(tmp_path):
    raiz = _crear_kit(tmp_path)
    lineas = (raiz / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    con_prefijo = []
    for linea in lineas:
        sha, rel = linea.split(None, 1)
        con_prefijo.append(f"{sha}  DiagUSB/{rel}")
    (raiz / "SHA256SUMS.txt").write_text(
        "\n".join(con_prefijo) + "\n", encoding="utf-8")
    resultado = publicacion.verificar_kit(raiz, estricto=True)
    assert resultado["ok"] is True
    assert resultado["correctos"] == len(ARCHIVOS_KIT)
    assert resultado["extras"] == []


def test_verificar_zip_correcto_y_con_extra(tmp_path):
    raiz = _crear_kit(tmp_path)
    zip_ok = _crear_zip(raiz, tmp_path / "DiagUSB-kit-0.1.0.zip")
    resultado = publicacion.verificar_kit(zip_ok, estricto=True)
    assert resultado["ok"] is True
    assert resultado["tipo"] == "zip"

    with zipfile.ZipFile(zip_ok, "a") as zf:
        zf.writestr("DiagUSB/sobra.txt", b"sobra")
    flexible = publicacion.verificar_kit(zip_ok)
    assert flexible["ok"] is True
    assert flexible["extras"] == ["sobra.txt"]
    estricto = publicacion.verificar_kit(zip_ok, estricto=True)
    assert estricto["ok"] is False


def test_verificar_zip_manipulado(tmp_path):
    raiz = _crear_kit(tmp_path)
    (raiz / "LICENSE").write_bytes(b"licencia cambiada despues del manifiesto")
    zip_malo = _crear_zip(raiz, tmp_path / "DiagUSB-kit-0.1.0.zip")
    resultado = publicacion.verificar_kit(zip_malo)
    assert resultado["ok"] is False
    assert any("hash distinto en LICENSE" in f for f in resultado["fallos"])


def test_verificar_zip_sin_sums(tmp_path):
    destino = tmp_path / "vacio.zip"
    with zipfile.ZipFile(destino, "w") as zf:
        zf.writestr("DiagUSB/LICENSE", b"x")
    with pytest.raises(ValueError):
        publicacion.verificar_kit(destino)


def test_formatear_verificacion(tmp_path):
    raiz = _crear_kit(tmp_path)
    texto = publicacion.formatear_verificacion(
        publicacion.verificar_kit(raiz, estricto=True))
    assert "RESULTADO: OK" in texto
    (raiz / "LICENSE").write_bytes(b"cambiada")
    texto = publicacion.formatear_verificacion(publicacion.verificar_kit(raiz))
    assert "[FALLA] hash distinto en LICENSE" in texto
    assert "RESULTADO: FALLO" in texto


def _ejecutar(*argumentos: str) -> subprocess.CompletedProcess:
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = str(REPO / "src")
    entorno["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "diagusb", *argumentos],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=entorno, timeout=120,
    )


def test_cli_verificar_kit(tmp_path):
    raiz = _crear_kit(tmp_path)
    ok = _ejecutar("verificar-kit", str(raiz), "--estricto")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "RESULTADO: OK" in ok.stdout

    json_out = _ejecutar("verificar-kit", str(raiz), "--json")
    assert json_out.returncode == 0
    datos = json.loads(json_out.stdout)
    assert datos["ok"] is True
    assert datos["tipo"] == "carpeta"

    (raiz / "LICENSE").write_bytes(b"cambiada")
    malo = _ejecutar("verificar-kit", str(raiz))
    assert malo.returncode == 1
    assert "hash distinto en LICENSE" in malo.stdout


def test_cli_notas_release(tmp_path):
    artefacto = tmp_path / "DiagUSB-kit-0.1.0.zip"
    artefacto.write_bytes(b"kit")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    notas = tmp_path / "salida" / "NOTAS-0.1.0.md"
    meta = tmp_path / "salida" / "release.json"

    ok = _ejecutar(
        "notas-release", "--version", "0.1.0", "--tag", "v0.1.0",
        "--artefacto", str(artefacto), "--salida", str(notas),
        "--json-salida", str(meta), "--changelog", str(changelog),
        "--fecha", "2026-10-28",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert notas.is_file()
    texto = notas.read_text(encoding="utf-8")
    assert "Kit verificable" in texto
    datos = json.loads(meta.read_text(encoding="utf-8"))
    assert datos["artefactos"][0]["sha256"] == _sha(b"kit")

    malo = _ejecutar(
        "notas-release", "--version", "0.1.0", "--tag", "v0.2.0",
        "--artefacto", str(artefacto), "--salida", str(notas),
        "--changelog", str(changelog),
    )
    assert malo.returncode == 1
    assert "no coincide" in malo.stdout


def test_script_de_publicacion_es_seguro_y_verifica():
    ruta = REPO / "scripts" / "publicar_release.ps1"
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in texto
    for requerido in (
        "verificar-kit", "notas-release", "armar_kit.ps1", "probar_kit.ps1",
        "SHA256SUMS.txt", "Get-FileHash", "-ConInstalador",
        "throw", "exit 0",
    ):
        assert requerido in texto, requerido
    for prohibido in (
        "Invoke-WebRequest", "Start-BitsTransfer", "Format-Volume",
        "Clear-Disk", "Initialize-Disk", "New-Partition", "diskpart",
        "git push", "gh release", "Remove-Item -LiteralPath $env:SystemDrive",
    ):
        assert prohibido not in texto, prohibido


def test_workflow_verifica_hashes_antes_de_publicar():
    ruta = REPO / ".github" / "workflows" / "build-kit.yml"
    texto = ruta.read_text(encoding="utf-8")
    assert "verificar-kit" in texto
    assert "notas-release" in texto
    assert "--notes-file" in texto
    assert texto.index("Get-FileHash") < texto.index("gh @opciones")
    assert "SHA256SUMS.txt" in texto


def test_instalador_usa_version_numerica_del_build():
    iss = (REPO / "installer" / "DiagUSB.iss").read_text(
        encoding="utf-8", errors="replace")
    build = (REPO / "scripts" / "build_installer.ps1").read_text(
        encoding="utf-8", errors="replace")
    assert "VersionInfoVersion={#MiAppVersionNumerica}" in iss
    assert "MiAppVersionNumerica" in build
    assert "/DMiAppVersionNumerica=$VersionNumerica" in build
