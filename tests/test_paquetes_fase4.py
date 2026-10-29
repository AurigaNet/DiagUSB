# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de los paquetes de red, puertos y perifericos (fase 4).

Cubren los manifiestos, la forma de los colectores y las reglas nuevas con
datos simulados. Los colectores reales se ejecutan aparte en Windows.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core import knowledge_base as kb
from diagusb.core.informe import (informe_a_html, informe_a_pdf,
                                  informe_desde_diagnostico)
from diagusb.core.models import CollectorResult
from diagusb.core.registry import discover_packages
from diagusb.core.rules import RuleEngine

RAIZ = Path(__file__).parent.parent
PAQUETES = RAIZ / "src" / "diagusb" / "packages"

NUEVOS = {
    "puertos_locales": (["listen"], ["puerto_expuesto"]),
    "escaneo_red": (["neighbors", "reachability"], ["equipos_red_no_visibles"]),
    "captura_sospechosa": (["proxy", "hosts", "capture"], ["trafico_red_alterado"]),
    "gateways_dns": (["gateway", "dns"], ["gateway_no_responde", "dns_inestable"]),
    "perifericos": (["input"], ["teclado_no_responde", "mouse_no_responde"]),
}


def obs(collector_id: str, data, status: str = "ok") -> CollectorResult:
    return CollectorResult(
        schema_version=1,
        collector_id=collector_id,
        captured_at_utc=datetime.utcnow().isoformat(),
        query={"status": status, "duration_ms": 10, "timeout_seconds": 15},
        context={},
        metadata={},
        data=data,
        errors=[],
        notes=[],
    )


def test_manifiestos_de_fase4_se_descubren():
    paquetes = {p.name: p for p in discover_packages()}
    for nombre, (_, sintomas) in NUEVOS.items():
        assert nombre in paquetes, nombre
        assert paquetes[nombre].symptoms == sintomas
        assert paquetes[nombre].collectors, f"{nombre} sin colectores"


def test_colectores_sin_escrituras_y_con_aviso_spdx():
    prohibidos = (
        "Set-Content", "Out-File", "New-Item", "Remove-Item", "Set-Item",
        "Stop-Service", "Start-Service", "Restart-Service", "Set-Service",
        "Disable-NetAdapter", "Enable-NetAdapter", "Set-NetIP", "New-NetIP",
        "Remove-NetIP", "netsh ", "reg add", "reg delete", "Remove-NetRoute",
        "New-NetRoute", "Set-NetFirewall", "New-NetFirewall",
    )
    for nombre in NUEVOS:
        scripts = list((PAQUETES / nombre / "collectors").glob("*.ps1"))
        assert scripts, f"{nombre} sin scripts"
        for script in scripts:
            texto = script.read_text(encoding="utf-8")
            assert texto.startswith("# SPDX-License-Identifier: GPL-3.0-or-later"), script
            assert "New-DiagUsbCollectorResult" in texto, script
            for prohibido in prohibidos:
                assert prohibido not in texto, f"{script.name}: {prohibido}"


def test_puerto_expuesto_solo_con_terceros():
    motor = RuleEngine()
    data = {
        "third_party_exposed_count": 1,
        "third_party_exposed": [
            {"process_name": "app", "local_port": 5000, "local_address": "0.0.0.0"},
        ],
    }
    hallazgos = motor.evaluate("puerto_expuesto", [obs("listening_ports", data)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"
    assert hallazgos[0].knowledge_id == "puerto_expuesto"
    assert "app:5000" in hallazgos[0].details["muestra"]

    vacio = motor.evaluate("puerto_expuesto", [obs("listening_ports", {
        "third_party_exposed": [], "third_party_exposed_count": 0})])
    assert vacio == []


def test_puerto_expuesto_cuenta_una_vez_ipv4_e_ipv6():
    motor = RuleEngine()
    data = {
        "third_party_exposed": [
            {"process_name": "app", "local_port": 80, "protocol": "tcp",
             "local_address": "::"},
            {"process_name": "app", "local_port": 80, "protocol": "tcp",
             "local_address": "0.0.0.0"},
            {"process_name": "otro", "local_port": 8080, "protocol": "udp",
             "local_address": "0.0.0.0"},
        ],
    }
    hallazgos = motor.evaluate("puerto_expuesto", [obs("listening_ports", data)])
    assert hallazgos[0].details["total"] == 2
    assert hallazgos[0].details["listeners"] == 3
    assert "2 puerto(s)" in hallazgos[0].message


def test_equipos_red_no_visibles_gateway_sin_respuesta():
    motor = RuleEngine()
    data = {"gateway_ip": "192.168.1.1", "gateway_reachable": False,
            "gateway_status": "TimedOut", "checked_count": 0}
    hallazgos = motor.evaluate("equipos_red_no_visibles",
                               [obs("lan_reachability", data)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"
    assert "192.168.1.1" in hallazgos[0].message


def test_equipos_red_no_visibles_red_sin_vecinos():
    motor = RuleEngine()
    alcanzable = {"gateway_ip": "10.0.0.1", "gateway_reachable": True,
                  "checked_count": 0, "reachable_count": 0}
    vecinos = {"neighbor_count": 1, "visible_count": 1, "other_host_count": 0}
    hallazgos = motor.evaluate("equipos_red_no_visibles", [
        obs("lan_reachability", alcanzable),
        obs("network_neighbors", vecinos),
    ])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"
    assert "red local" in hallazgos[0].message


def test_equipos_red_no_visibles_con_otros_equipos_no_inventa():
    motor = RuleEngine()
    alcanzable = {"gateway_ip": "10.0.0.1", "gateway_reachable": True,
                  "checked_count": 2, "reachable_count": 2}
    vecinos = {"neighbor_count": 3, "visible_count": 3, "other_host_count": 2}
    assert motor.evaluate("equipos_red_no_visibles", [
        obs("lan_reachability", alcanzable),
        obs("network_neighbors", vecinos),
    ]) == []


def test_trafico_alterado_aviso_por_hosts():
    motor = RuleEngine()
    datos = {"non_loopback_count": 2, "active_count": 3}
    hallazgos = motor.evaluate("trafico_red_alterado", [
        obs("hosts_entries", datos),
        obs("proxy_settings", {"manual_remote_proxy": False,
                               "environment_proxy_count": 0}),
        obs("capture_drivers", {"running_count": 0, "present": False}),
    ])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"
    assert "hosts" in hallazgos[0].message


def test_trafico_alterado_error_con_captura_activa():
    motor = RuleEngine()
    hallazgos = motor.evaluate("trafico_red_alterado", [
        obs("hosts_entries", {"non_loopback_count": 1}),
        obs("proxy_settings", {"manual_remote_proxy": True,
                               "user_proxy_server": "10.0.0.9:8080",
                               "environment_proxy_count": 0}),
        obs("capture_drivers", {"running_count": 1, "present": True}),
    ])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"
    assert "10.0.0.9:8080" in hallazgos[0].message


def test_trafico_alterado_sin_anomalias_no_inventa():
    motor = RuleEngine()
    assert motor.evaluate("trafico_red_alterado", [
        obs("hosts_entries", {"non_loopback_count": 0}),
        obs("proxy_settings", {"manual_remote_proxy": False,
                               "environment_proxy_count": 0}),
        obs("capture_drivers", {"running_count": 0, "present": False}),
    ]) == []


def test_gateway_no_responde_sin_ruta_y_sin_respuesta():
    motor = RuleEngine()
    sin_ruta = motor.evaluate("gateway_no_responde",
                              [obs("gateway_routes", {"gateway_count": 0})])
    assert sin_ruta[0].severity == "warning"

    caido = motor.evaluate("gateway_no_responde", [obs("gateway_routes", {
        "gateway_count": 1, "primary_gateway": "192.168.0.1",
        "primary_reachable": False, "reachable_count": 0,
    })])
    assert caido[0].severity == "error"
    assert "192.168.0.1" in caido[0].message

    bien = motor.evaluate("gateway_no_responde", [obs("gateway_routes", {
        "gateway_count": 1, "primary_gateway": "192.168.0.1",
        "primary_reachable": True, "reachable_count": 1,
    })])
    assert bien == []


def test_dns_inestable_falla_lento_y_sin_servidores():
    motor = RuleEngine()
    falla = motor.evaluate("dns_inestable", [
        obs("dns_resolution", {"query_name": "ejemplo.test", "success": False,
                               "timed_out": True, "error": ""}),
    ])
    assert falla[0].severity == "error"
    assert "tiempo de espera" in falla[0].message

    lento = motor.evaluate("dns_inestable", [
        obs("dns_resolution", {"query_name": "ejemplo.test", "success": True,
                               "elapsed_ms": 2500}),
    ])
    assert lento[0].severity == "warning"

    sin = motor.evaluate("dns_inestable", [
        obs("gateway_dns_servers", {"unique_count": 0, "interface_count": 0}),
    ])
    assert sin[0].severity == "warning"

    bien = motor.evaluate("dns_inestable", [
        obs("gateway_dns_servers", {"unique_count": 1}),
        obs("dns_resolution", {"query_name": "ejemplo.test", "success": True,
                               "elapsed_ms": 40}),
    ])
    assert bien == []


def test_teclado_con_error_y_ausente():
    motor = RuleEngine()
    con_error = motor.evaluate("teclado_no_responde", [obs("input_devices", {
        "keyboards": [{"name": "Teclado USB", "status": "Error",
                       "config_manager_error_code": 10,
                       "pnp_device_id": "USB\\KBD\\1"}],
        "pnp_keyboards": [],
    })])
    assert con_error[0].severity == "error"
    assert con_error[0].knowledge_id == "teclado_no_responde"
    assert "codigo: 10" in con_error[0].message

    ausente = motor.evaluate("teclado_no_responde", [obs("input_devices", {
        "keyboards": [], "pnp_keyboards": [],
    })])
    assert ausente[0].severity == "warning"

    bien = motor.evaluate("teclado_no_responde", [obs("input_devices", {
        "keyboards": [{"name": "Teclado USB", "status": "OK",
                       "config_manager_error_code": 0,
                       "pnp_device_id": "USB\\KBD\\1"}],
        "pnp_keyboards": [],
    })])
    assert bien == []


def test_mouse_con_error_y_ausente():
    motor = RuleEngine()
    con_error = motor.evaluate("mouse_no_responde", [obs("input_devices", {
        "pointing_devices": [],
        "pnp_pointing_devices": [{"name": "Mouse HID", "status": "Degraded",
                                  "config_manager_error_code": 0,
                                  "pnp_device_id": "HID\\MOUSE\\1"}],
    })])
    assert con_error[0].severity == "error"
    assert con_error[0].knowledge_id == "mouse_no_responde"

    ausente = motor.evaluate("mouse_no_responde", [obs("input_devices", {
        "pointing_devices": [], "pnp_pointing_devices": [],
    })])
    assert ausente[0].severity == "warning"

    bien = motor.evaluate("mouse_no_responde", [obs("input_devices", {
        "pointing_devices": [{"name": "Mouse USB", "status": "OK",
                              "config_manager_error_code": 0,
                              "pnp_device_id": "HID\\MOUSE\\1"}],
        "pnp_pointing_devices": [],
    })])
    assert bien == []


def test_base_de_conocimiento_tiene_los_siete_sintomas():
    ids = {entrada["id"] for entrada in kb.entradas()}
    for nombre, (_, sintomas) in NUEVOS.items():
        for sintoma in sintomas:
            assert sintoma in ids, f"falta {sintoma} ({nombre})"
            entrada = kb.buscar(sintoma)
            assert entrada["soluciones"], sintoma
            assert entrada["sintomas"] == [sintoma]


def _informe_perifericos(prueba: dict | None):
    diag = {
        "package": "perifericos",
        "package_label": "Periféricos",
        "symptom": "teclado_no_responde",
        "results": [],
        "findings": [],
        "collectors_count": 1,
        "ok_count": 1,
        "error_count": 0,
    }
    if prueba is not None:
        diag["prueba_perifericos"] = prueba
    return informe_desde_diagnostico(diag, tecnico="Técnico de prueba",
                                     cliente="Taller")


def test_informe_incluye_la_prueba_interactiva():
    informe = _informe_perifericos({
        "prueba_ejecutada": True,
        "iniciada_en": "2026-10-28T10:00:00",
        "finalizada_en": "2026-10-28T10:01:00",
        "teclas": 12,
        "ultima_tecla": "Enter",
        "ultimo_codigo": "Enter",
        "movimientos": 40,
        "clics": 3,
        "botones": [0, 2],
        "rueda": 5,
    })
    html = informe_a_html(informe)
    assert "Prueba de periféricos" in html
    assert "Teclas recibidas" in html
    assert "Izquierdo, Derecho" in html
    assert "no reemplaza una prueba de hardware" in html.lower()
    pdf = informe_a_pdf(informe)
    assert pdf.startswith(b"%PDF")


def test_informe_sin_prueba_no_inventa_resultados():
    html = informe_a_html(_informe_perifericos(None))
    assert "Prueba de periféricos" not in html

    sin_eventos = informe_a_html(_informe_perifericos({
        "prueba_ejecutada": True, "teclas": 0, "movimientos": 0,
        "clics": 0, "botones": [], "rueda": 0,
    }))
    assert "No se recibieron eventos" in sin_eventos


def test_interfaz_tiene_botones_y_prueba_interactiva():
    html = (RAIZ / "src" / "diagusb" / "static" / "index.html").read_text(
        encoding="utf-8")
    for nombre in NUEVOS:
        assert f"runDiagnostic('{nombre}')" in html, nombre
    assert 'data-paquete="bateria"' in html
    assert 'id="perifericosPanel"' in html

    js = (RAIZ / "src" / "diagusb" / "static" / "app.js").read_text(
        encoding="utf-8")
    for funcion in ("iniciarPruebaPerifericos", "detenerPruebaPerifericos",
                    "limpiarPruebaPerifericos", "renderPruebaPerif"):
        assert f"function {funcion}" in js, funcion
    assert "conectarPruebaPerifericos();" in js
    assert "prueba_perifericos" in js
