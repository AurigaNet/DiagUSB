# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de la referencia por equipo (captura y comparacion)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core import referencia


IDENT = {
    "id": "dgu-0123456789abcdef",
    "id_corto": "DGU-0123-4567",
    "computer_name": "PC-SOPORTE",
    "nivel": "fuerte",
}


def resultado(collector_id: str, data, status: str = "ok") -> dict:
    return {
        "collector_id": collector_id,
        "query": {"status": status},
        "data": data,
    }


def results_impresion(offline=False, predeterminada=True, puerto="IP_10.0.0.5",
                      estado_spooler="Running", trabajos=0):
    return [
        resultado("printers", [{
            "name": "Recepcion",
            "work_offline": offline,
            "default": predeterminada,
            "port_name": puerto,
            "driver_name": "HP Universal",
            "shared": False,
            "printer_status": 3,
            "detected_error_state": 0,
        }]),
        resultado("printer_ports", [{
            "name": puerto,
            "host_address": "10.0.0.5",
            "port_number": 9100,
            "protocol": 1,
        }]),
        resultado("spooler_service", {
            "spooler": {"state": estado_spooler, "start_mode": "Auto"}
        }),
        resultado("print_jobs", [{"name": f"job{i}"} for i in range(trabajos)]),
    ]


def test_nombre_archivo_usa_id_y_evita_mezclar_sin_id():
    assert referencia.nombre_archivo("dgu-abc") == "dgu-abc.json"
    a = referencia.nombre_archivo("", "PC-Uno")
    b = referencia.nombre_archivo("", "PC-Dos")
    assert a.startswith("sinid-") and a.endswith(".json")
    assert a != b


def test_guardar_y_cargar_referencia(tmp_path):
    estado = referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    assert estado["disponible"] is True
    assert estado["id_corto"] == "DGU-0123-4567"
    doc = referencia.cargar(IDENT, base_dir=tmp_path)
    assert doc is not None
    assert doc["machine_id"] == IDENT["id"]
    assert doc["colectores"]["printers"]["status"] == "ok"


def test_sin_referencia_no_inventa_diferencias(tmp_path):
    r = referencia.comparar(IDENT, results_impresion(), base_dir=tmp_path)
    assert r["disponible"] is False
    assert r["diferencias"] == []
    assert "No hay" in r["mensaje"]


def test_comparacion_sin_cambios(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    r = referencia.comparar(IDENT, results_impresion(), base_dir=tmp_path)
    assert r["disponible"] is True
    assert r["total_diferencias"] == 0


def test_detecta_impresora_sin_conexion(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    r = referencia.comparar(IDENT, results_impresion(offline=True), base_dir=tmp_path)
    assert r["total_diferencias"] == 1
    assert r["diferencias"][0]["severidad"] == "error"
    assert "sin conexion" in r["diferencias"][0]["mensaje"]


def test_detecta_impresora_ausente(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    actual = results_impresion()
    actual[0]["data"] = []
    r = referencia.comparar(IDENT, actual, base_dir=tmp_path)
    assert any("ya no esta instalada" in d["mensaje"] for d in r["diferencias"])


def test_detecta_puerto_con_otra_ip(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    actual = results_impresion()
    actual[1]["data"][0]["host_address"] = "10.0.0.99"
    r = referencia.comparar(IDENT, actual, base_dir=tmp_path)
    assert any("otra direccion IP" in d["mensaje"] for d in r["diferencias"])
    assert any(d["severidad"] == "error" for d in r["diferencias"])


def test_detecta_spooler_detenido(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    r = referencia.comparar(IDENT, results_impresion(estado_spooler="Stopped"),
                            base_dir=tmp_path)
    assert any(d["collector_id"] == "spooler_service"
               and d["severidad"] == "critical" for d in r["diferencias"])


def test_detecta_trabajos_en_cola(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    r = referencia.comparar(IDENT, results_impresion(trabajos=2), base_dir=tmp_path)
    assert any(d["collector_id"] == "print_jobs" for d in r["diferencias"])


def test_referencia_de_otro_equipo_no_se_compara(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    otro = dict(IDENT, id="dgu-ffffffffffffffff", id_corto="DGU-FFFF-FFFF")
    r = referencia.comparar(otro, results_impresion(offline=True), base_dir=tmp_path)
    # El archivo se busca por el ID del equipo actual, asi que no lo encuentra.
    assert r["disponible"] is False


def test_aplicar_a_diagnostico_agrega_hallazgos_de_impresion(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    salida = {"package": "impresion", "findings": []}
    ref = referencia.aplicar_a_diagnostico(
        salida, results_impresion(offline=True), IDENT, base_dir=tmp_path)
    assert ref["total_diferencias"] >= 1
    assert salida["findings"]
    assert salida["findings"][0]["knowledge_id"] == "referencia_impresion"


def test_aplicar_a_otro_paquete_no_agrega_hallazgos(tmp_path):
    referencia.guardar(results_impresion(), IDENT, base_dir=tmp_path)
    salida = {"package": "disco", "findings": []}
    referencia.aplicar_a_diagnostico(
        salida, results_impresion(offline=True), IDENT, base_dir=tmp_path)
    assert salida["findings"] == []
    assert salida["referencia"]["disponible"] is True
