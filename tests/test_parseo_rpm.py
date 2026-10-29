# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Parseo de RPM de get_fan_speeds.ps1 contra un LHM simulado en 127.0.0.1:8085.

Los datos son simulados: prueban el parseo, no el formato real de LHM.
"""
import json
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

COLECTOR = (Path(__file__).resolve().parent.parent / "src" / "diagusb"
            / "packages" / "temperatura" / "collectors" / "get_fan_speeds.ps1")
PUERTO = 8085


def _puerto_ocupado():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PUERTO)) == 0


pytestmark = [
    pytest.mark.skipif(shutil.which("powershell") is None,
                       reason="requiere Windows PowerShell"),
    pytest.mark.skipif(_puerto_ocupado(), reason="el puerto 8085 esta ocupado"),
]


def _doc(valor):
    def hoja(t, v):
        return {"Text": t, "Value": v, "Children": []}
    return {"Text": "Sensor", "Value": "", "Children": [
        {"Text": "CPU simulado", "Value": "", "Children": [
            {"Text": "Temperatures", "Value": "", "Children": [
                hoja("CPU Package", "85,0 \u00b0C")]}]},
        {"Text": "Placa simulada", "Value": "", "Children": [
            {"Text": "Fans", "Value": "", "Children": [hoja("Fan #1", valor)]}]}]}


@pytest.fixture
def lhm_simulado():
    servidores = []

    def levantar(valor):
        cuerpo = json.dumps(_doc(valor)).encode("utf-8")

        class Manejador(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *args):
                pass

        servidor = HTTPServer(("127.0.0.1", PUERTO), Manejador)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        servidores.append(servidor)

    yield levantar
    for servidor in servidores:
        servidor.shutdown()
        servidor.server_close()


def _correr_colector():
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(COLECTOR)],
        capture_output=True, timeout=90)
    return json.loads(r.stdout.decode("utf-8-sig", errors="replace"))


CASOS = [
    ("0 RPM", 0),
    ("1200 RPM", 1200),
    ("1.234 RPM", 1234),
    ("1,234 RPM", 1234),
    ("12.345 RPM", 12345),
    ("1.234,5 RPM", 1234),
    ("1200,5 RPM", 1200),
]


@pytest.mark.parametrize("valor,esperado", CASOS, ids=[c[0] for c in CASOS])
def test_parseo_rpm(lhm_simulado, valor, esperado):
    lhm_simulado(valor)
    resultado = _correr_colector()
    assert resultado["query"]["status"] == "ok"
    datos = resultado["data"]
    if isinstance(datos, list):
        datos = datos[0]
    assert datos["fan_rpms"] == [esperado]
    assert datos["max_fan_rpm"] == esperado