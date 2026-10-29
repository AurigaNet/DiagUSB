# SPDX-License-Identifier: GPL-3.0-or-later
"""Registro real de reglas: nombres, orden y punto de entrada del motor."""
from collections import Counter

from diagusb.core.rules import RuleEngine, diagnose_symptoms
from diagusb.core.models import CollectorResult, Finding, QueryInfo

# Nombres de registro en orden fuente (lista literal del paso A2, antes de eac13df)
# mas la unica linea nueva: bateria_agotada despues de cpu_caliente.
ESPERADO_REGISTRO = [
    "la_impresora_no_imprime", "la_impresora_no_imprime", "la_impresora_no_imprime",
    "la_impresora_no_imprime", "la_impresora_no_imprime", "la_impresora_no_imprime",
    "adaptador_red_no_funciona",
    "no_hay_internet", "no_hay_internet", "no_hay_internet",
    "red_lenta", "dns_no_responde",
    "disco_lleno", "disco_salud", "disco_salud",
    "cpu_caliente",
    "ventilador_0_rpm_con_cpu_caliente",
    "bateria_agotada",
    "servicio_detenido", "servicios_fallando",
    "antivirus_apagado", "firewall_apagado",
    "memoria_llena", "sistema_lento", "sistema_lento",
    "updates_pendientes", "updates_fallidos", "windows_update_roto",
    "driver_antiguo", "driver_generico",
    "wifi_no_conecta", "wifi_lento", "wifi_perdida",
    "blue_screen", "error_del_sistema", "error_del_sistema",
    "apagado_inesperado", "apagado_inesperado",
    "disco_lento", "proceso_alto_cpu",
    "seguridad_comprometida", "servicio_no_inicia",
    "puerto_expuesto", "equipos_red_no_visibles", "trafico_red_alterado",
    "gateway_no_responde", "dns_inestable",
    "teclado_no_responde", "mouse_no_responde",
]


def test_registro_coincide_con_lista_de_referencia():
    """El registro interno de RuleEngine tiene exactamente los nombres de referencia."""
    motor = RuleEngine()
    real = Counter(
        nombre
        for nombre, reglas in motor._rules.items()
        for _ in reglas
    )
    assert real == Counter(ESPERADO_REGISTRO), (
        "Registro real != referencia:\n"
        f"espera: {Counter(ESPERADO_REGISTRO)}\n"
        f"real  : {real}"
    )
    for nombre in ESPERADO_REGISTRO:
        assert nombre in motor._rules, nombre


def _observacion_servicio_detenido():
    return CollectorResult(
        collector_id="critical_services",
        query=QueryInfo(status="ok", duration_ms=5, timeout_seconds=15),
        data=[{
            "name": "Spooler",
            "display_name": "Cola de impresión",
            "start_mode": "auto",
            "state": "stopped",
        }],
    )


def test_servicio_detenido_por_el_punto_de_entrada_real():
    """diagnose_symptoms (punto de entrada real) devuelve servicio_detenido con datos simulados."""
    hallazgos, _recomendaciones = diagnose_symptoms(
        ["servicio_detenido"], [_observacion_servicio_detenido()]
    )
    assert any(
        isinstance(f, Finding)
        and f.collector_id == "critical_services"
        and f.severity == "error"
        and "Servicio crítico detenido" in f.message
        for f in hallazgos
    ), hallazgos
