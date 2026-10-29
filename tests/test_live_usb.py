# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas del live USB: manifiesto, verificacion y cableado de la interfaz."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import diagusb.web_server as ws
from diagusb.core import live_usb

REPO = Path(__file__).resolve().parents[1]
MANIFIESTO = REPO / "tools" / "tools.manifest.json"
STATIC = Path(ws.__file__).parent / "static"


def _sha(texto: bytes) -> str:
    return hashlib.sha256(texto).hexdigest()


def _escribir_manifiesto(tmp_path: Path, herramientas: list[dict]) -> Path:
    ruta = tmp_path / "tools.manifest.json"
    ruta.write_text(json.dumps({
        "schema_version": 1,
        "generated_at": "2026-10-28",
        "tools": herramientas,
    }, ensure_ascii=False), encoding="utf-8")
    return ruta


def _herramienta_verificada(archivo: str, contenido: bytes) -> dict:
    return {
        "name": "Herramienta de prueba",
        "official_domain": "example.org",
        "url": "https://downloads.example.org/" + archivo,
        "version": "1.0",
        "sha256": _sha(contenido),
        "license": "GPL-3.0",
        "file": archivo,
        "source": "https://example.org/",
        "checksum_url": "https://example.org/sha256.txt",
        "estado": "verificado",
    }


def test_manifiesto_real_tiene_datos_oficiales_completos():
    datos = live_usb.cargar_manifiesto(MANIFIESTO)
    por_nombre = {t["name"]: t for t in datos["tools"]}
    assert set(por_nombre) == {
        "SystemRescue", "memtest86+", "Ventoy", "WinPE", "Sysinternals",
        "Npcap", "LibreHardwareMonitor", "PawnIO"
    }
    for nombre in ("SystemRescue", "memtest86+", "LibreHardwareMonitor",
                   "PawnIO"):
        t = por_nombre[nombre]
        assert t["estado"] == "verificado"
        assert t["url"].startswith("https://")
        assert t["version"]
        assert len(t["sha256"]) == 64
        assert t["license"]
        assert t["file"]
        assert t["source"].startswith("https://")
        assert t["checksum_url"].startswith("https://")
    assert por_nombre["Ventoy"]["estado"] == "excluido"
    assert por_nombre["Ventoy"]["motivo"]
    for nombre in ("WinPE", "Sysinternals", "Npcap"):
        assert por_nombre[nombre]["estado"] == "excluido"
        assert por_nombre[nombre]["motivo"]


def test_estado_resume_verificadas_y_excluidas():
    estado = live_usb.estado_live_usb(MANIFIESTO)
    assert estado["todo_verificado"] is True
    assert estado["verificadas"] == 4
    assert estado["listas"] == 4
    assert estado["excluidas"] == 4
    assert estado["pendientes"] == 0
    assert any(h["nombre"] == "Ventoy" and h["motivo"] for h in estado["herramientas"])


def test_entrada_incompleta_falla_cerrado():
    herramienta = {
        "name": "Incompleta",
        "official_domain": "example.org",
        "url": "https://otro-dominio.test/archivo.iso",
        "version": "",
        "sha256": "abc",
        "license": "",
        "file": "../archivo.iso",
        "estado": "verificado",
    }
    evaluada = live_usb.evaluar_herramienta(herramienta)
    assert evaluada["lista"] is False
    texto = " ".join(evaluada["motivos"])
    assert "version" in texto
    assert "SHA-256" in texto
    assert "dominio oficial" in texto
    assert "licencia" in texto
    assert "carpetas" in texto


def test_excluida_sin_motivo_se_reporta():
    evaluada = live_usb.evaluar_herramienta({
        "name": "Sin motivo", "estado": "excluido"
    })
    assert evaluada["lista"] is False
    assert any("sin motivo" in m for m in evaluada["motivos"])


def test_manifiesto_invalido(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        live_usb.cargar_manifiesto(ruta)
    with pytest.raises(FileNotFoundError):
        live_usb.cargar_manifiesto(tmp_path / "no-existe.json")


def test_verificar_archivos_ok_falla_si_cambia_o_falta(tmp_path):
    contenido = b"imagen de prueba" * 100
    archivo = "prueba.iso"
    (tmp_path / archivo).write_bytes(contenido)
    manifiesto = _escribir_manifiesto(
        tmp_path, [_herramienta_verificada(archivo, contenido)])

    ok = live_usb.verificar_archivos(tmp_path, manifiesto)
    assert ok["todo_correcto"] is True
    assert ok["correctos"] == 1
    assert ok["fallos"] == 0
    assert ok["resultados"][0]["sha256_obtenido"] == _sha(contenido)

    (tmp_path / archivo).write_bytes(b"otra cosa")
    malo = live_usb.verificar_archivos(tmp_path, manifiesto)
    assert malo["todo_correcto"] is False
    assert malo["fallos"] == 1
    assert "no coincide" in malo["resultados"][0]["error"]

    (tmp_path / archivo).unlink()
    falta = live_usb.verificar_archivos(tmp_path, manifiesto)
    assert falta["fallos"] == 1
    assert falta["resultados"][0]["presente"] is False


def test_verificar_carpeta_inexistente(tmp_path):
    manifiesto = _escribir_manifiesto(tmp_path, [])
    with pytest.raises(FileNotFoundError):
        live_usb.verificar_archivos(tmp_path / "no-existe", manifiesto)


# ---------------------------------------------------------------------------
# API y cableado de la interfaz
# ---------------------------------------------------------------------------

def _abrir_servidor():
    import socketserver
    import threading

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_api_live_usb(monkeypatch):
    import urllib.request

    monkeypatch.setenv(live_usb.VARIABLE_ENTORNO, str(MANIFIESTO))
    httpd, base = _abrir_servidor()
    try:
        req = urllib.request.Request(
            base + "/api/live-usb",
            headers={"Cookie": f"diagusb_token={ws._token_sesion()}"})
        with urllib.request.urlopen(req, timeout=20) as respuesta:
            assert respuesta.status == 200
            datos = json.loads(respuesta.read().decode("utf-8"))
        assert datos["todo_verificado"] is True
        assert datos["verificadas"] == 4
        assert {h["nombre"] for h in datos["herramientas"]} >= {
            "SystemRescue", "memtest86+", "Ventoy",
            "LibreHardwareMonitor", "PawnIO"
        }
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_interfaz_muestra_el_estado_del_live_usb():
    html = (STATIC / "index.html").read_text(encoding="utf-8", errors="replace")
    js = (STATIC / "app.js").read_text(encoding="utf-8", errors="replace")
    assert 'id="liveUsbEstado"' in html
    assert 'id="liveUsbLista"' in html
    assert "Pendrive de arranque" in html
    assert "cargarLiveUSB" in js
    assert "fetch('/api/live-usb')" in js
    assert "cargarLiveUSB();" in js


# ---------------------------------------------------------------------------
# Script de verificacion en PowerShell (solo lectura)
# ---------------------------------------------------------------------------

def test_script_verificador_no_escribe_ni_descarga():
    ruta = REPO / "scripts" / "verificar_live_usb.ps1"
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in texto
    assert "Get-FileHash" in texto
    assert "Test-DominioOficial" in texto
    for prohibido in (
        "Invoke-WebRequest", "Start-BitsTransfer", "Format-Volume",
        "Clear-Disk", "Initialize-Disk", "New-Partition", "Remove-Partition",
        "diskpart", "Remove-Item", "Set-Content", "Out-File",
    ):
        assert prohibido not in texto, prohibido


@pytest.mark.skipif(shutil.which("powershell") is None,
                    reason="PowerShell no disponible")
def test_script_verificador_detecta_hash_correcto_e_incorrecto(tmp_path):
    contenido = b"otra imagen de prueba" * 50
    archivo = "prueba.iso"
    (tmp_path / archivo).write_bytes(contenido)
    manifiesto = _escribir_manifiesto(
        tmp_path, [_herramienta_verificada(archivo, contenido)])
    script = REPO / "scripts" / "verificar_live_usb.ps1"

    orden = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script), "-Carpeta", str(tmp_path),
        "-Manifiesto", str(manifiesto),
    ]
    ok = subprocess.run(orden, capture_output=True, text=True, timeout=60)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "[OK]" in ok.stdout

    (tmp_path / archivo).write_bytes(b"contenido distinto")
    malo = subprocess.run(orden, capture_output=True, text=True, timeout=60)
    assert malo.returncode == 1
    assert "HASH NO COINCIDE" in malo.stdout
