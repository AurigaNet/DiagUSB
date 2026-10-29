# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Saneamiento de RPM del colector real ``get_fan_rpm.ps1``.

No consulta hardware ni red: ejecuta en PowerShell la funcion pura
``ConvertFrom-DiagUsbFanSensors`` con sensores simulados. Los valores son
inventados y solo prueban el filtrado y el redondeo; no se leen fixtures ni
se presentan como lecturas del equipo.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

COMMON = (Path(__file__).resolve().parent.parent / "collectors" / "_common.ps1")

pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None, reason="requiere Windows PowerShell")


def _sensores(*valores, sensor_type="Fan"):
    return [
        {"hardware": "Placa simulada", "name": f"Fan #{indice}",
         "sensor_type": sensor_type, "value": valor}
        for indice, valor in enumerate(valores, 1)
    ]


def _correr(sensores):
    crudo = json.dumps(sensores, ensure_ascii=False).replace("'", "''")
    script = (
        f". '{COMMON}'\n"
        f"$sensores = @('{crudo}' | ConvertFrom-Json | ForEach-Object {{ $_ }})\n"
        "ConvertFrom-DiagUsbFanSensors -Sensores $sensores | "
        "ConvertTo-Json -Compress -Depth 5\n"
    )
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        capture_output=True, timeout=90)
    return json.loads(resultado.stdout.decode("utf-8-sig", errors="replace"))


CASOS = [
    ("0 RPM real", _sensores(0), [0], 0),
    ("1200 RPM", _sensores(1200), [1200], 1200),
    ("redondeo", _sensores(1713.6), [1714], 1714),
    ("lectura imposible", _sensores(749306), [], 0),
    ("valor negativo", _sensores(-5), [], 0),
    ("varios sensores", _sensores(0, 1200, 749306), [0, 1200], 1200),
    ("sensor que no es ventilador", _sensores(50, sensor_type="Temperature"),
     [], 0),
]


@pytest.mark.parametrize("nombre,sensores,esperado,maximo",
                         CASOS, ids=[c[0] for c in CASOS])
def test_saneamiento_rpm(nombre, sensores, esperado, maximo):
    datos = _correr(sensores)
    rpms = datos["fan_rpms"]
    if not isinstance(rpms, list):
        rpms = [rpms]
    assert rpms == esperado
    assert datos["max_fan_rpm"] == maximo
    assert datos["sensor_count"] == len(esperado)
