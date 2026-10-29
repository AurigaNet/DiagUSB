# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de las reglas de los sintomas de soporte de infraestructura.

Cubren los cuatro sintomas que antes se declaraban en los manifests pero no
tenian ninguna regla: ``disco_lento``, ``proceso_alto_cpu``,
``seguridad_comprometida`` y ``servicio_no_inicia``.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.models import CollectorResult
from diagusb.core.rules import RuleEngine


def obs(collector_id: str, data, status: str = "ok") -> CollectorResult:
    """Resultado de colector simulado con la forma real."""
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


def test_disco_lento_latencia_alta_es_error():
    motor = RuleEngine()
    datos = [{
        "disk": "0 C:",
        "avg_transfer_sec": 0.25,
        "percent_disk_time": 95,
        "current_disk_queue_length": 3,
        "read_ops_per_sec": 40,
        "write_ops_per_sec": 10,
    }]
    hallazgos = motor._check_disk_slow([obs("disk_performance", datos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"
    assert hallazgos[0].knowledge_id == "disco_lento"
    assert "Disco lento" in hallazgos[0].message


def test_disco_lento_latencia_media_es_aviso():
    motor = RuleEngine()
    datos = [{
        "disk": "0 C:",
        "avg_transfer_sec": 0.08,
        "percent_disk_time": 75,
        "current_disk_queue_length": 2,
        "read_ops_per_sec": 5,
        "write_ops_per_sec": 5,
    }]
    hallazgos = motor._check_disk_slow([obs("disk_performance", datos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"


def test_disco_lento_disco_inactivo_no_se_evalua():
    motor = RuleEngine()
    datos = [{
        "disk": "1 D:",
        "avg_transfer_sec": 0.9,
        "percent_disk_time": 99,
        "current_disk_queue_length": 9,
        "read_ops_per_sec": 0,
        "write_ops_per_sec": 0,
    }]
    assert motor._check_disk_slow([obs("disk_performance", datos)]) == []


def test_disco_lento_sin_datos_no_inventa():
    motor = RuleEngine()
    datos = [{"disk": "0 C:", "avg_transfer_sec": None,
              "percent_disk_time": None, "current_disk_queue_length": None,
              "read_ops_per_sec": None, "write_ops_per_sec": None}]
    assert motor._check_disk_slow([obs("disk_performance", datos)]) == []


def test_proceso_alto_cpu_error():
    motor = RuleEngine()
    datos = [{"name": "compressor", "pid": 4242, "cpu_percent": 72.5,
              "cpu_percent_total": 290.0, "memory_mb": 120.0}]
    hallazgos = motor._check_process_high_cpu([obs("top_processes", datos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"
    assert hallazgos[0].knowledge_id == "proceso_alto_cpu"
    assert "compressor" in hallazgos[0].message


def test_proceso_alto_cpu_aviso():
    motor = RuleEngine()
    datos = [{"name": "backup", "pid": 7, "cpu_percent": 41.0}]
    hallazgos = motor._check_process_high_cpu([obs("top_processes", datos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"


def test_proceso_cpu_normal_sin_hallazgo():
    motor = RuleEngine()
    datos = [{"name": "explorer", "pid": 10, "cpu_percent": 3.2}]
    assert motor._check_process_high_cpu([obs("top_processes", datos)]) == []


def test_proceso_cpu_no_disponible_no_inventa():
    motor = RuleEngine()
    datos = [{"name": "x", "pid": 1, "cpu_percent": None}]
    assert motor._check_process_high_cpu([obs("top_processes", datos)]) == []


def test_seguridad_antivirus_y_firewall_apagados_es_critico():
    motor = RuleEngine()
    resultados = [
        obs("antivirus_status", [{"display_name": "Defender", "enabled": False,
                                  "real_time_protection": False}]),
        obs("firewall_status", [{"name": "Dominio", "enabled": False},
                                {"name": "Privado", "enabled": False},
                                {"name": "Publico", "enabled": False}]),
    ]
    hallazgos = motor._check_security_compromised(resultados)
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "critical"
    assert hallazgos[0].knowledge_id == "seguridad_comprometida"


def test_seguridad_logons_fallidos():
    motor = RuleEngine()
    eventos = [{"id": 4625} for _ in range(6)]
    hallazgos = motor._check_security_compromised(
        [obs("security_events", eventos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"
    assert hallazgos[0].details["failed_logons"] == 6


def test_seguridad_logons_fallidos_muchos_es_error():
    motor = RuleEngine()
    eventos = [{"id": 4625} for _ in range(12)]
    hallazgos = motor._check_security_compromised(
        [obs("security_events", eventos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"


def test_seguridad_firmas_desactualizadas():
    motor = RuleEngine()
    centro = [{"type": "antivirus", "display_name": "Defender",
               "enabled": True, "up_to_date": False}]
    hallazgos = motor._check_security_compromised(
        [obs("security_center", centro)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "warning"


def test_seguridad_limpia_sin_hallazgos():
    motor = RuleEngine()
    resultados = [
        obs("antivirus_status", [{"display_name": "Defender", "enabled": True,
                                  "real_time_protection": True}]),
        obs("firewall_status", [{"name": "Dominio", "enabled": True}]),
        obs("security_events", [{"id": 4624}]),
        obs("security_center", [{"display_name": "Defender", "enabled": True,
                                 "up_to_date": True}]),
    ]
    assert motor._check_security_compromised(resultados) == []


def test_servicio_automatico_detenido_no_inicia():
    motor = RuleEngine()
    datos = [{"name": "Spooler", "display_name": "Print Spooler",
              "start_mode": "Auto", "state": "Stopped", "exit_code": 1067}]
    hallazgos = motor._check_service_wont_start(
        [obs("critical_services", datos)])
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "error"
    assert hallazgos[0].knowledge_id == "servicio_no_inicia"
    assert "1067" in hallazgos[0].message


def test_servicio_corriendo_sin_hallazgo():
    motor = RuleEngine()
    datos = [{"name": "Spooler", "display_name": "Print Spooler",
              "start_mode": "Auto", "state": "Running"}]
    assert motor._check_service_wont_start(
        [obs("critical_services", datos)]) == []


def test_servicio_manual_detenido_no_es_falla():
    motor = RuleEngine()
    datos = [{"name": "Fax", "display_name": "Fax",
              "start_mode": "Manual", "state": "Stopped"}]
    assert motor._check_service_wont_start(
        [obs("critical_services", datos)]) == []


def test_sintomas_huerfanos_tienen_regla():
    motor = RuleEngine()
    for sintoma in ("disco_lento", "proceso_alto_cpu",
                    "seguridad_comprometida", "servicio_no_inicia"):
        assert motor._rules.get(sintoma), sintoma
