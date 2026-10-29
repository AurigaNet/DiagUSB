# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modelos de datos para DiagUSB."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WindowsInfo:
    version: str = ""
    build: str = ""
    edition: str = ""
    architecture: str = ""


@dataclass
class RegionalSettings:
    locale: str = ""
    timezone: str = ""
    currency: str = ""


@dataclass
class PowerShellInfo:
    version: str = ""
    execution_policy: str = ""


@dataclass
class QueryInfo:
    status: str = "unknown"
    duration_ms: int = 0
    timeout_seconds: int = 15


@dataclass
class ContextInfo:
    computer_name: str = ""
    user: str = ""
    is_elevated: bool = False
    windows: WindowsInfo = field(default_factory=WindowsInfo)
    regional_settings: RegionalSettings = field(default_factory=RegionalSettings)
    powershell: PowerShellInfo = field(default_factory=PowerShellInfo)


@dataclass
class ContextResult:
    """Resultado de la deteccion de contexto del sistema."""
    system_type: str = "unknown"
    form_factor: str = "unknown"
    is_virtual: bool = False
    manufacturer: str = ""
    model: str = ""
    domain: str = ""
    has_battery: bool = False
    has_wifi: bool = False
    processor_family: str = ""
    total_memory_gb: int = 0
    os_type: str = "workstation"
    os_version: str = ""
    uptime_hours: int = 0
    is_domain_member: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "ContextResult":
        return cls(
            system_type=data.get("system_type", "unknown"),
            form_factor=data.get("form_factor", "unknown"),
            is_virtual=data.get("is_virtual", False),
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", ""),
            domain=data.get("domain", ""),
            has_battery=data.get("has_battery", False),
            has_wifi=data.get("has_wifi", False),
            processor_family=data.get("processor_family", ""),
            total_memory_gb=data.get("total_memory_gb", 0),
            os_type=data.get("os_type", "workstation"),
            os_version=data.get("os_version", ""),
            uptime_hours=data.get("uptime_hours", 0),
            is_domain_member=data.get("is_domain_member", False),
        )


@dataclass
class CollectorResult:
    schema_version: str = "1.0"
    collector_id: str = ""
    captured_at_utc: str = ""
    query: QueryInfo = field(default_factory=QueryInfo)
    context: ContextInfo = field(default_factory=ContextInfo)
    metadata: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ComputerId:
    smbios_uuid: str = ""
    bios_serial: str = ""
    machine_guid: str = ""
    mac_addresses: list[str] = field(default_factory=list)
    weak_candidate: bool = False
    machine_id: str = ""
    componentes: dict[str, str] = field(default_factory=dict)
    calidad: str = ""
    respaldos: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    computer_id: ComputerId = field(default_factory=ComputerId)
    captured_at_utc: str = ""
    observations: list[CollectorResult] = field(default_factory=list)


@dataclass
class Finding:
    severity: str = "ok"  # ok/warning/error/critical
    collector_id: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    knowledge_id: str = ""  # entrada de la base de conocimiento asociada


@dataclass
class DiagnosticResult:
    symptom: str = ""
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    context: Optional[ContextInfo] = None
    system_context: Optional[ContextResult] = None
    collector_results: list[CollectorResult] = field(default_factory=list)


@dataclass
class Difference:
    collector_id: str = ""
    field_path: str = ""
    baseline_value: Any = None
    current_value: Any = None
    severity: str = "warning"  # ok/warning/error/critical


@dataclass
class CollectorManifest:
    id: str = ""
    label: str = ""
    script: str = ""


@dataclass
class PackageManifest:
    name: str = ""
    version: str = ""
    label: str = ""
    description: str = ""
    symptoms: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    collectors: list[CollectorManifest] = field(default_factory=list)
