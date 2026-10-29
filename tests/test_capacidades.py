# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de deteccion previa de hardware y gating de paquetes."""

from pathlib import Path

from diagusb.core import capacidades
from diagusb.core.registry import discover_packages


def _caps(printer=None, network=None, cpu=None, battery=None):
    return {
        "ok": True,
        "printers": printer or {
            "query_ok": True,
            "real": 0,
            "virtual": 0,
            "offline": 0,
        },
        "network": network or {
            "query_ok": True,
            "has_adapter": False,
            "has_link": False,
            "has_ipv4": False,
            "has_gateway": False,
            "present_kinds": [],
            "active_kinds": [],
            "wifi_present": False,
            "wifi_enabled": False,
            "wifi_link": False,
        },
        "cpu_temperature": cpu or {
            "query_ok": True,
            "available": False,
            "process_running": False,
            "error": "LibreHardwareMonitor no esta activo.",
        },
        "battery": battery or {
            "query_ok": True,
            "present": False,
            "count": 0,
            "error": "",
        },
    }


def test_sin_impresora_fisica_no_aplica():
    disp = capacidades.evaluar_requisitos(["printer"], _caps())
    assert disp["available"] is False
    assert "impresora" in disp["reason"].lower()


def test_impresora_offline_se_puede_diagnosticar():
    caps = _caps(printer={
        "query_ok": True, "real": 1, "virtual": 2, "offline": 1,
    })
    disp = capacidades.evaluar_requisitos(["printer"], caps)
    assert disp["available"] is True
    assert "sin conexion" in disp["reason"]


def test_red_separa_placa_de_conectividad():
    caps = _caps(network={
        "query_ok": True,
        "has_adapter": True,
        "has_link": False,
        "has_ipv4": False,
        "has_gateway": False,
        "present_kinds": ["ethernet", "wifi"],
        "active_kinds": [],
        "wifi_present": True,
        "wifi_enabled": True,
        "wifi_link": False,
    })
    assert capacidades.evaluar_requisitos(["network_adapter"], caps)["available"] is True
    assert capacidades.evaluar_requisitos(["network_link"], caps)["available"] is False
    wifi = capacidades.evaluar_requisitos(["wifi_adapter"], caps)
    assert wifi["available"] is True
    assert "sin conexion" in wifi["reason"]


def test_wifi_deshabilitado_no_aplica():
    caps = _caps(network={
        "query_ok": True,
        "has_adapter": True,
        "has_link": False,
        "has_ipv4": False,
        "has_gateway": False,
        "present_kinds": ["wifi"],
        "active_kinds": [],
        "wifi_present": True,
        "wifi_enabled": False,
        "wifi_link": False,
    })
    disp = capacidades.evaluar_requisitos(["wifi_adapter"], caps)
    assert disp["available"] is False
    assert "deshabilitado" in disp["reason"]


def test_temperatura_cpu_requiere_lhm_activo():
    disp = capacidades.evaluar_requisitos(["cpu_temperature"], _caps())
    assert disp["available"] is False
    assert "LibreHardwareMonitor" in disp["reason"]


def test_temperatura_cpu_disponible_con_lhm():
    caps = _caps(cpu={
        "query_ok": True,
        "available": True,
        "process_running": True,
        "cpu_name": "AMD Ryzen 7 5800H",
        "max_temp_c": 62.0,
        "error": "",
    })
    disp = capacidades.evaluar_requisitos(["cpu_temperature"], caps)
    assert disp["available"] is True
    assert "Ryzen" in disp["reason"]


def test_temperatura_cpu_lhm_sin_servidor_web():
    caps = _caps(cpu={
        "query_ok": False,
        "available": False,
        "process_running": True,
        "error": "El servidor web no responde.",
    })
    disp = capacidades.evaluar_requisitos(["cpu_temperature"], caps)
    assert disp["available"] is False
    assert "servidor web" in disp["reason"]


def test_enlace_activo_habilita_conectividad():
    caps = _caps(network={
        "query_ok": True,
        "has_adapter": True,
        "has_link": True,
        "has_ipv4": False,
        "has_gateway": False,
        "present_kinds": ["ethernet"],
        "active_kinds": ["ethernet"],
        "wifi_present": False,
        "wifi_enabled": False,
        "wifi_link": False,
    })
    disp = capacidades.evaluar_requisitos(["network_link"], caps)
    assert disp["available"] is True
    assert "sin IPv4" in disp["reason"]


def test_deteccion_fallida_permite_diagnostico():
    disp = capacidades.evaluar_requisitos(["printer"], {"ok": False})
    assert disp["available"] is True
    assert disp["warning"] is True


def test_manifiestos_declaran_requisitos():
    paquetes = {p.name: p for p in discover_packages()}
    assert paquetes["impresion"].requirements == ["printer"]
    assert paquetes["redes"].requirements == ["network_adapter"]
    assert paquetes["conectividad"].requirements == ["network_link"]
    assert paquetes["wifi"].requirements == ["wifi_adapter"]
    assert paquetes["temperatura"].requirements == ["cpu_temperature"]
    assert paquetes["bateria"].requirements == ["battery"]
    assert "conectividad" not in [
        c.id for c in paquetes["redes"].collectors
    ]


def test_sin_bateria_el_paquete_no_aplica():
    disp = capacidades.evaluar_requisitos(["battery"], _caps())
    assert disp["available"] is False
    assert "bateria" in disp["reason"].lower()
    # con una bateria presente, el paquete esta disponible
    caps = _caps(battery={"query_ok": True, "present": True, "count": 1})
    disp = capacidades.evaluar_requisitos(["battery"], caps)
    assert disp["available"] is True
    assert disp["warning"] is False
    # si la deteccion falla, fail-open con advertencia
    caps = _caps(battery={"query_ok": False, "present": False,
                          "count": 0, "error": "boom"})
    disp = capacidades.evaluar_requisitos(["battery"], caps)
    assert disp["available"] is True
    assert disp["warning"] is True


def test_colectores_clasifican_conexiones_moviles():
    raiz = Path(__file__).resolve().parent.parent
    comun = (raiz / "collectors" / "_common.ps1").read_text(encoding="utf-8")
    for termino in ("bluetooth", "rndis", "usb_tethering", "wwan", "wifi"):
        assert termino in comun
    adaptadores = (raiz / "src" / "diagusb" / "packages" / "redes"
                   / "collectors" / "get_network_adapters.ps1").read_text(
                       encoding="utf-8")
    assert "kind = Get-DiagUsbConnectionKind" in adaptadores


def test_full_scan_omite_paquetes_no_aplicables():
    from diagusb import web_server as ws

    caps = _caps(
        printer={"query_ok": True, "real": 1, "virtual": 0, "offline": 0},
        network={
            "query_ok": True,
            "has_adapter": True,
            "has_link": False,
            "has_ipv4": False,
            "has_gateway": False,
            "present_kinds": ["ethernet"],
            "active_kinds": [],
            "wifi_present": False,
            "wifi_enabled": False,
            "wifi_link": False,
        },
    )
    disponibles, omitidos = ws._clasificar_paquetes(discover_packages(), caps)
    disponibles_ids = {p.name for p in disponibles}
    omitidos_ids = {o["package"] for o in omitidos}

    assert {"impresion", "redes"} <= disponibles_ids
    assert "conectividad" in omitidos_ids
    assert "wifi" in omitidos_ids
    assert "temperatura" in omitidos_ids


def test_diagnostico_no_aplicable_no_ejecuta_colectores(monkeypatch):
    from diagusb import web_server as ws

    caps = _caps()
    llamado = {"valor": False}

    def _no_ejecutar(*args, **kwargs):
        llamado["valor"] = True
        raise AssertionError("no debe ejecutar colectores")

    monkeypatch.setattr(ws, "_scripts_colectores", _no_ejecutar)
    salida = ws.run_diagnostic("impresion", caps=caps)
    assert salida["unavailable"] is True
    assert "No aplica" in salida["error"]
    assert llamado["valor"] is False
