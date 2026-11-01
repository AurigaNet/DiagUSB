# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Comparador de instantaneas para DiagUSB."""

import json
from pathlib import Path
from typing import Any

from .models import CollectorResult, ComputerId, Difference, Snapshot
from . import almacen
from . import identidad


def load_snapshot(path: Path) -> Snapshot:
    """
    Carga una instantánea desde un archivo JSON.

    Args:
        path: Ruta al archivo de instantanea.

    Returns:
        Objeto Snapshot con los datos cargados.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Reconstruir el ComputerId
    computer_id_data = data.get("computer_id", {})
    comp_guardadas = computer_id_data.get("componentes")
    if isinstance(comp_guardadas, dict):
        componentes = dict(comp_guardadas)
    else:
        componentes = {}
        for nombre in identidad.FUERTES + identidad.DEBILES:
            valor = computer_id_data.get(nombre, "")
            if isinstance(valor, str) and valor.strip():
                componentes[nombre] = valor.strip()
    machine_id = computer_id_data.get("machine_id", "")
    if not isinstance(machine_id, str):
        machine_id = ""
    respaldos = computer_id_data.get("respaldos")
    if not isinstance(respaldos, dict):
        respaldos = {}
    computer_id = ComputerId(
        smbios_uuid=computer_id_data.get("smbios_uuid", ""),
        bios_serial=computer_id_data.get("bios_serial", ""),
        machine_guid=computer_id_data.get("machine_guid", ""),
        mac_addresses=computer_id_data.get("mac_addresses", []),
        weak_candidate=computer_id_data.get("weak_candidate", False),
        machine_id=machine_id or identidad.fingerprint(componentes),
        componentes=componentes,
        calidad=str(computer_id_data.get("calidad", "") or "")
        or identidad.calidad(componentes),
        respaldos=respaldos
    )

    # Reconstruir CollectorResults
    observations = []
    for obs_data in data.get("observations", []):
        query_data = obs_data.get("query", {})
        context_data = obs_data.get("context", {})

        # Subobjetos anidados
        windows_data = context_data.get("windows", {})
        regional_data = context_data.get("regional_settings", {})
        ps_data = context_data.get("powershell", {})

        from .models import (
            CollectorResult, QueryInfo, ContextInfo, WindowsInfo,
            RegionalSettings, PowerShellInfo
        )

        obs = CollectorResult(
            schema_version=obs_data.get("schema_version", "1.0"),
            collector_id=obs_data.get("collector_id", ""),
            captured_at_utc=obs_data.get("captured_at_utc", ""),
            query=QueryInfo(
                status=query_data.get("status", "unknown"),
                duration_ms=query_data.get("duration_ms", 0),
                timeout_seconds=query_data.get("timeout_seconds", 15),
                message=str(query_data.get("message") or "")
            ),
            context=ContextInfo(
                computer_name=context_data.get("computer_name", ""),
                user=context_data.get("user", ""),
                is_elevated=context_data.get("is_elevated", False),
                windows=WindowsInfo(
                    version=windows_data.get("version", ""),
                    build=windows_data.get("build", ""),
                    edition=windows_data.get("edition", ""),
                    architecture=windows_data.get("architecture", "")
                ),
                regional_settings=RegionalSettings(
                    locale=regional_data.get("locale", ""),
                    timezone=regional_data.get("timezone", ""),
                    currency=regional_data.get("currency", "")
                ),
                powershell=PowerShellInfo(
                    version=ps_data.get("version", ""),
                    execution_policy=ps_data.get("execution_policy", "")
                )
            ),
            metadata=obs_data.get("metadata", {}),
            data=obs_data.get("data", {}),
            errors=obs_data.get("errors", []),
            notes=obs_data.get("notes", [])
        )
        observations.append(obs)

    return Snapshot(
        computer_id=computer_id,
        captured_at_utc=data.get("captured_at_utc", ""),
        observations=observations
    )


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    """
    Guarda una instantánea en un archivo JSON.

    Args:
        snapshot: Objeto Snapshot a guardar.
        path: Ruta donde guardar el archivo.
    """
    data = {
        "computer_id": {
            "smbios_uuid": snapshot.computer_id.smbios_uuid,
            "bios_serial": snapshot.computer_id.bios_serial,
            "machine_guid": snapshot.computer_id.machine_guid,
            "mac_addresses": snapshot.computer_id.mac_addresses,
            "weak_candidate": snapshot.computer_id.weak_candidate,
            "machine_id": snapshot.computer_id.machine_id
            or identidad.fingerprint(snapshot.computer_id.componentes),
            "componentes": snapshot.computer_id.componentes,
            "calidad": snapshot.computer_id.calidad
            or identidad.calidad(snapshot.computer_id.componentes),
            "respaldos": snapshot.computer_id.respaldos,
        },
        "captured_at_utc": snapshot.captured_at_utc,
        "observations": []
    }

    for obs in snapshot.observations:
        obs_data = {
            "schema_version": obs.schema_version,
            "collector_id": obs.collector_id,
            "captured_at_utc": obs.captured_at_utc,
            "query": {
                "status": obs.query.status,
                "duration_ms": obs.query.duration_ms,
                "timeout_seconds": obs.query.timeout_seconds
            },
            "context": {
                "computer_name": obs.context.computer_name,
                "user": obs.context.user,
                "is_elevated": obs.context.is_elevated,
                "windows": {
                    "version": obs.context.windows.version,
                    "build": obs.context.windows.build,
                    "edition": obs.context.windows.edition,
                    "architecture": obs.context.windows.architecture
                },
                "regional_settings": {
                    "locale": obs.context.regional_settings.locale,
                    "timezone": obs.context.regional_settings.timezone,
                    "currency": obs.context.regional_settings.currency
                },
                "powershell": {
                    "version": obs.context.powershell.version,
                    "execution_policy": obs.context.powershell.execution_policy
                }
            },
            "metadata": obs.metadata,
            "data": obs.data,
            "errors": obs.errors,
            "notes": obs.notes
        }
        data["observations"].append(obs_data)

    almacen.escribir_json_atomico(path, data, indent=2)


def _get_nested_value(data: dict[str, Any], path: str) -> Any:
    """Obtiene un valor anidado de un diccionario usando ruta de puntos."""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _compare_values(
    collector_id: str,
    field_path: str,
    baseline_value: Any,
    current_value: Any
) -> list[Difference]:
    """Compara dos valores y devuelve las diferencias."""
    differences = []

    if baseline_value == current_value:
        return differences

    # Determinar la severidad
    severity = "warning"
    if isinstance(baseline_value, (int, float)) and isinstance(current_value, (int, float)):
        # Cambio numérico significativo
        if baseline_value == 0 and current_value != 0:
            severity = "error"
        elif current_value == 0:
            severity = "warning"

    differences.append(Difference(
        collector_id=collector_id,
        field_path=field_path,
        baseline_value=baseline_value,
        current_value=current_value,
        severity=severity
    ))
    return differences


def compare_snapshots(baseline: Snapshot, current: Snapshot) -> list[Difference]:
    """
    Compara dos instantaneas y devuelve las diferencias.

    Args:
        baseline: Instantanea base (anterior).
        current: Instantanea actual (nueva).

    Returns:
        Lista de objetos Difference con las diferencias encontradas.
    """
    differences = []

    # Armar el mapa de observaciones por collector_id
    baseline_obs = {obs.collector_id: obs for obs in baseline.observations}
    current_obs = {obs.collector_id: obs for obs in current.observations}

    # Comparar cada colector presente en la baseline
    for collector_id, baseline_observation in baseline_obs.items():
        current_observation = current_obs.get(collector_id)

        if current_observation is None:
            # Colector presente en la baseline pero ausente en la actual
            differences.append(Difference(
                collector_id=collector_id,
                field_path="",
                baseline_value="presente",
                current_value="ausente",
                severity="error"
            ))
            continue

        # Comparar los datos del colector
        baseline_data = baseline_observation.data
        current_data = current_observation.data

        # Las salidas pueden ser dict (campos) o list (registros): comparar según forma
        if isinstance(baseline_data, dict) and isinstance(current_data, dict):
            all_keys = set(baseline_data.keys()) | set(current_data.keys())
            for key in all_keys:
                baseline_val = baseline_data.get(key)
                current_val = current_data.get(key)
                if baseline_val != current_val:
                    diffs = _compare_values(collector_id, key, baseline_val, current_val)
                    differences.extend(diffs)
        elif baseline_data != current_data:
            n_base = len(baseline_data) if isinstance(baseline_data, (list, dict)) else "?"
            n_act = len(current_data) if isinstance(current_data, (list, dict)) else "?"
            differences.append(Difference(
                collector_id=collector_id,
                field_path="data",
                baseline_value=f"registros: {n_base}",
                current_value=f"registros: {n_act}",
                severity="warning"
            ))

    # Verificar colectores nuevos (presentes en actual pero ausentes en baseline)
    for collector_id in current_obs:
        if collector_id not in baseline_obs:
            differences.append(Difference(
                collector_id=collector_id,
                field_path="",
                baseline_value="ausente",
                current_value="presente",
                severity="warning"
            ))

    return differences
