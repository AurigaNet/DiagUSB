#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de core/metricas.py (puntaje orientativo, cobertura y tendencia)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.metricas import calcular_metricas, tendencia  # noqa: E402


def _col(cid, status="ok"):
    return {"collector_id": cid, "query": {"status": status}, "data": []}


def _find(sev, cid="x", no_eval=False):
    return {"severity": sev, "collector_id": cid, "message": "m",
            "details": ({"no_evaluado": True} if no_eval else {})}


def test_sin_modulos():
    m = calcular_metricas({"package": "disco", "results": [], "findings": []})
    assert m["puntaje"] is None
    assert m["etiqueta"] == "Sin datos"
    assert m["cobertura"]["porcentaje"] == 0.0


def test_todo_ok_cien():
    m = calcular_metricas({"package": "disco", "package_label": "Disco",
                           "results": [_col("a"), _col("b"), _col("c")],
                           "findings": []})
    assert m["puntaje"] == 100
    assert m["etiqueta"] == "Bueno"
    assert m["cobertura"]["colectores_ok"] == 3
    assert m["cobertura"]["porcentaje"] == 100.0


def test_un_critico_dos_altos():
    m = calcular_metricas({"package": "disco", "package_label": "Disco",
                           "results": [_col("a"), _col("b"), _col("c")],
                           "findings": [_find("critical"), _find("error"),
                                        _find("error")]})
    assert m["puntaje"] == 69
    assert m["etiqueta"] == "Atención"


def test_diez_criticos_piso():
    m = calcular_metricas({"package": "disco", "results": [_col("a")],
                           "findings": [_find("critical", cid=f"c{i}")
                                        for i in range(10)]})
    assert m["puntaje"] == 0


def test_cobertura_menor_sesenta():
    m = calcular_metricas({"package": "disco",
                           "results": [_col("a"), _col("b", "denied"),
                                       _col("c", "error")],
                           "findings": []})
    assert m["puntaje"] == 100
    assert m["etiqueta"] == "Datos parciales"
    assert m["cobertura"]["porcentaje"] == round(1 / 3 * 100, 1)


def test_error_no_infla_puntaje():
    ok = calcular_metricas({"package": "disco", "results": [_col("a")],
                            "findings": []})
    mal = calcular_metricas({"package": "disco",
                             "results": [_col("a"), _col("b", "error"),
                                         _col("c", "timeout")],
                             "findings": []})
    assert ok["puntaje"] == mal["puntaje"]
    assert mal["cobertura"]["porcentaje"] < ok["cobertura"]["porcentaje"]


def test_no_evaluado_no_resta():
    m = calcular_metricas({"package": "disco", "results": [_col("a")],
                           "findings": [_find("warning", cid="a",
                                              no_eval=True)]})
    assert m["puntaje"] == 100
    assert m["severidad"]["warning"] == 0


def test_alcance_paquete_y_equipo():
    pkg = calcular_metricas({"package": "disco", "package_label": "Disco",
                             "results": [_col("a")], "findings": []})
    assert pkg["alcance"] == "Puntaje del paquete Disco"
    eq = calcular_metricas({"package": "full-scan", "results": [_col("a")],
                            "findings": []}, modulos=12)
    assert eq["alcance"] == "Puntaje de salud del equipo"


def test_medidores_solo_si_existen():
    m = calcular_metricas({
        "package": "disco", "findings": [],
        "results": [
            {"collector_id": "memory_status", "query": {"status": "ok"},
             "data": [{"physical_memory_usage_percent": 42.5,
                       "total_visible_memory_kb": 100,
                       "free_physical_memory_kb": 57}]},
            {"collector_id": "logical_disks", "query": {"status": "ok"},
             "data": [{"device_id": "C:", "used_percent": 70.0,
                       "free_gb": 30.0, "total_gb": 100.0}]},
        ]})
    assert m["medidores"]["memoria"]["usado_porcentaje"] == 42.5
    assert m["medidores"]["discos"][0]["unidad"] == "C:"
    sin = calcular_metricas({"package": "impresion",
                             "results": [_col("printers")], "findings": []})
    assert "medidores" not in sin


def test_json_serializa():
    m = calcular_metricas({"package": "disco", "results": [_col("a")],
                           "findings": [_find("warning")]})
    assert isinstance(json.dumps(m, ensure_ascii=False), str)


def test_tendencia_no_mezcla():
    entradas = [
        {"fecha": "2026-01-03", "tipo": "paquete", "paquete": "disco",
         "puntaje": 80},
        {"fecha": "2026-01-02", "tipo": "full-scan", "paquete": "full-scan",
         "puntaje": 50},
        {"fecha": "2026-01-01", "tipo": "paquete", "paquete": "disco",
         "puntaje": 90},
        {"fecha": "2025-12-31", "tipo": "paquete", "paquete": "redes",
         "puntaje": 70},
    ]
    t = tendencia(entradas)
    assert [p["puntaje"] for p in t] == [90, 80]
    assert all(p["fecha"].startswith("2026-01") for p in t)


def test_tendencia_recalcula_sin_puntaje():
    entradas = [{"fecha": "2026-02-01", "tipo": "paquete", "paquete": "disco",
                 "colectores": [{"id": "a", "status": "ok"}],
                 "findings": [_find("error")]}]
    assert tendencia(entradas) == [{"fecha": "2026-02-01", "puntaje": 92}]


def test_tendencia_limita_diez():
    entradas = [{"fecha": f"2026-01-{i:02d}", "tipo": "paquete",
                 "paquete": "disco", "puntaje": i} for i in range(1, 16)]
    t = tendencia(entradas)
    assert len(t) == 10
    assert t[0]["puntaje"] == 6 and t[-1]["puntaje"] == 15


def test_campos_existentes_no_cambian():
    import diagusb.web_server as ws

    r = ws.run_diagnostic("contexto")
    base = {"package", "package_label", "symptom", "collectors_count",
            "ok_count", "error_count", "empty_count", "is_elevated",
            "results", "findings", "improvements", "integridad_fallida",
            "recommendations", "estados_accion", "timestamp"}
    assert base <= set(r)
    assert set(r) - base == {"metricas"}


def test_metricas_de_results_reevalua():
    import diagusb.web_server as ws

    results = [{"collector_id": "logical_disks", "query": {"status": "ok"},
                "data": [{"device_id": "C:", "used_percent": 99.5,
                          "free_percent": 0.5, "free_gb": 0.5,
                          "total_gb": 100.0}]}]
    m = ws._metricas_de_results(results, "disco", "Disco")
    assert m["cobertura"]["colectores_ejecutados"] == 1
    assert isinstance(m["puntaje"], int)


CASOS = [
    ("test_sin_modulos", test_sin_modulos),
    ("test_todo_ok_cien", test_todo_ok_cien),
    ("test_un_critico_dos_altos", test_un_critico_dos_altos),
    ("test_diez_criticos_piso", test_diez_criticos_piso),
    ("test_cobertura_menor_sesenta", test_cobertura_menor_sesenta),
    ("test_error_no_infla_puntaje", test_error_no_infla_puntaje),
    ("test_no_evaluado_no_resta", test_no_evaluado_no_resta),
    ("test_alcance_paquete_y_equipo", test_alcance_paquete_y_equipo),
    ("test_medidores_solo_si_existen", test_medidores_solo_si_existen),
    ("test_json_serializa", test_json_serializa),
    ("test_tendencia_no_mezcla", test_tendencia_no_mezcla),
    ("test_tendencia_recalcula_sin_puntaje", test_tendencia_recalcula_sin_puntaje),
    ("test_tendencia_limita_diez", test_tendencia_limita_diez),
    ("test_campos_existentes_no_cambian", test_campos_existentes_no_cambian),
    ("test_metricas_de_results_reevalua", test_metricas_de_results_reevalua),
]


def run_tests() -> bool:
    print("=" * 60)
    print("PRUEBAS DE METRICAS")
    print("=" * 60)
    pasadas = 0
    fallidas = 0
    for nombre, fn in CASOS:
        try:
            fn()
            print(f"  [OK] {nombre}")
            pasadas += 1
        except Exception as e:
            print(f"  [FALLO] {nombre}: {e}")
            fallidas += 1
    print(f"\nResultados: {pasadas} pasadas, {fallidas} fallidas")
    return fallidas == 0


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
