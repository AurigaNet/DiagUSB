#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Regresiones del diagnostico: disco, impresion, red, servicios y proxy.

Las pruebas textuales comprueban que los colectores conservan los respaldos
que no dependen de servicios de Windows que pueden estar detenidos. Las
pruebas de reglas usan datos simulados y no ejecutan PowerShell ni la red.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diagusb.core.models import CollectorResult, QueryInfo
from diagusb.core.rules import RuleEngine, _findings_no_evaluados


def _resultado(collector_id, data, status="ok", message=""):
    return CollectorResult(
        collector_id=collector_id,
        data=data,
        query=QueryInfo(status=status, message=message),
    )


def _texto(relativo):
    return (ROOT / "src" / "diagusb" / relativo).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Disco
# ---------------------------------------------------------------------------

def test_disco_logico_usa_driveinfo_y_descarta_volumenes_sin_tamano():
    texto = _texto("packages/disco/collectors/get_logical_disks.ps1")
    assert "System.IO.DriveInfo" in texto
    assert "Win32_LogicalDisk" in texto
    assert "-gt 0" in texto


def test_disco_fisico_respalda_storage_con_win32_diskdrive():
    texto = _texto("packages/disco/collectors/get_physical_disks.ps1")
    assert "smphost" in texto
    assert "Win32_DiskDrive" in texto
    assert "MSStorageDriver_FailurePredictStatus" in texto
    assert "Start-Job" in texto and "Wait-Job" in texto


def test_regla_espacio_omite_volumenes_sin_porcentaje():
    motor = RuleEngine()
    obs = [_resultado("logical_disks", [
        {"device_id": "C:", "free_percent": None,
         "free_gb": None, "total_gb": None},
        {"device_id": "D:", "free_percent": 91.3},
    ])]
    assert motor._check_disk_space(obs) == []


def test_regla_espacio_no_duplica_dos_puntos():
    motor = RuleEngine()
    obs = [_resultado("logical_disks", [{"device_id": "C:",
                                         "free_percent": 5.0}])]
    hallazgos = motor._check_disk_space(obs)
    assert len(hallazgos) == 1
    assert hallazgos[0].message.startswith("Espacio crítico en C:")
    assert "C::" not in hallazgos[0].message


def test_regla_espacio_alerta_con_porcentaje_real():
    motor = RuleEngine()
    obs = [_resultado("logical_disks", [{"device_id": "E:",
                                         "free_percent": 5.0}])]
    hallazgos = motor._check_disk_space(obs)
    assert len(hallazgos) == 1
    assert hallazgos[0].severity == "critical"


# ---------------------------------------------------------------------------
# Colectores que dependen de servicios detenidos
# ---------------------------------------------------------------------------

def test_impresion_informa_no_disponible_sin_spooler():
    for nombre in ("get_printers.ps1", "get_printer_drivers.ps1",
                   "get_printer_ports.ps1", "get_print_jobs.ps1"):
        texto = _texto("packages/impresion/collectors/" + nombre)
        assert "Spooler" in texto
        assert "DIAGUSB_NOT_AVAILABLE" in texto


def test_common_propaga_el_motivo_en_query_message():
    texto = (ROOT / "collectors" / "_common.ps1").read_text(encoding="utf-8")
    assert "message = $mensajeQuery" in texto
    assert "DIAGUSB_(NOT_AVAILABLE|DENIED|TIMEOUT)" in texto


def test_no_evaluado_incluye_motivo_del_colector():
    obs = [_resultado(
        "physical_disks", [], status="denied",
        message="se requieren permisos de administrador")]
    hallazgos = _findings_no_evaluados(obs)
    assert len(hallazgos) == 1
    assert "requiere administrador" in hallazgos[0].message
    assert "permisos" in hallazgos[0].message
    assert hallazgos[0].details["no_evaluado"] is True


def test_no_disponible_no_duplica_el_hallazgo_principal():
    # Spooler detenido ya lo informa ``spooler_service`` como critical; los
    # colectores de impresion que no pueden leer solo cuentan como no
    # evaluados, sin cuatro advertencias repetidas.
    obs = [
        _resultado("printers", [], status="not_available",
                   message="el servicio Spooler no esta en ejecucion"),
        _resultado("printer_ports", [], status="not_available",
                   message="el servicio Spooler no esta en ejecucion"),
    ]
    assert _findings_no_evaluados(obs) == []


# ---------------------------------------------------------------------------
# Servicios
# ---------------------------------------------------------------------------

def test_servicio_no_inicia_exige_codigo_de_error():
    motor = RuleEngine()
    datos = [{"name": "X", "display_name": "Servicio X",
              "start_mode": "Auto", "state": "Stopped"}]
    assert motor._check_service_wont_start(
        [_resultado("critical_services", datos)]) == []

    datos[0]["exit_code"] = 1067
    hallazgos = motor._check_service_wont_start(
        [_resultado("critical_services", datos)])
    assert len(hallazgos) == 1
    assert "1067" in hallazgos[0].message


def test_service_failures_descarta_servicios_por_usuario_y_disparador():
    texto = _texto("packages/servicios/collectors/get_service_failures.ps1")
    assert "0x40" in texto
    assert "TriggerInfo" in texto


# ---------------------------------------------------------------------------
# Red y captura
# ---------------------------------------------------------------------------

def test_vecinos_excluye_difusion_y_multicast():
    texto = _texto("packages/escaneo_red/collectors/"
                   "get_network_neighbors.ps1")
    assert "FF-FF-FF-FF-FF-FF" in texto
    assert "01-00-5E" in texto
    assert "33-33" in texto


def test_captura_solo_acepta_nombres_exactos_de_driver():
    texto = _texto("packages/captura_sospechosa/collectors/"
                   "get_capture_drivers.ps1")
    assert "(?i)^(npcap|npcap_wifi|npf|pcap)$" in texto


def test_no_proxy_no_cuenta_como_proxy_de_entorno():
    texto = _texto("packages/captura_sospechosa/collectors/"
                   "get_proxy_settings.ps1")
    assert "'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'" in texto
    assert "no_proxy = $noProxy" in texto


# ---------------------------------------------------------------------------
# Rendimiento
# ---------------------------------------------------------------------------

def test_cpu_usa_contador_del_sistema_con_respaldo():
    texto = _texto("packages/memoria/collectors/"
                   "get_system_performance.ps1")
    assert "Win32_PerfFormattedData_PerfOS_Processor" in texto
    assert "PercentProcessorTime" in texto


# ---------------------------------------------------------------------------
# Eventos y actualizaciones
# ---------------------------------------------------------------------------

def test_evento_error_con_hresult_correcto_no_alerta():
    motor = RuleEngine()
    evento = {
        "time_created": datetime.now(timezone.utc).isoformat(),
        "level": 2,
        "provider_name": "Microsoft-Windows-TPM-WMI",
        "message": "HResult: La operación se completó correctamente.",
    }
    assert motor._check_critical_events(
        [_resultado("critical_events", [evento])]) == []


def test_evento_error_real_si_alerta():
    motor = RuleEngine()
    evento = {
        "time_created": datetime.now(timezone.utc).isoformat(),
        "level": 2,
        "provider_name": "Disk",
        "message": "Error de E/S en el disco.",
    }
    hallazgos = motor._check_critical_events(
        [_resultado("critical_events", [evento])])
    assert len(hallazgos) == 1


def test_drivers_de_red_filtran_clases_exactas():
    texto = _texto("packages/redes/collectors/get_network_drivers.ps1")
    assert "(?i)^(Net|NetTrans|NetClient|NetService)$" in texto
    assert "SCSIADAPTER" not in texto.split("Where-Object")[1].split("|")[0]


def test_actualizaciones_pendientes_informa_no_disponible():
    texto = _texto("packages/windows_update/collectors/"
                   "get_pending_updates.ps1")
    assert "DIAGUSB_NOT_AVAILABLE" in texto
    assert "PSWindowsUpdate" in texto
