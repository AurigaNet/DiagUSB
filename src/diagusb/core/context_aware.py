# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modulo de deteccion automatica de contexto y adaptacion de reglas."""

from typing import Optional

class SystemContext:
    """Representa el contexto del sistema detectado."""

    SYSTEM_TYPE_DESKTOP = "desktop"
    SYSTEM_TYPE_NOTEBOOK = "notebook"
    SYSTEM_TYPE_SERVER = "server"
    SYSTEM_TYPE_UNKNOWN = "unknown"

    def __init__(self, context_data: dict):
        self.system_type = context_data.get("system_type", self.SYSTEM_TYPE_UNKNOWN)
        self.form_factor = context_data.get("form_factor", "unknown")
        self.is_virtual = context_data.get("is_virtual", False)
        self.manufacturer = context_data.get("manufacturer", "")
        self.model = context_data.get("model", "")
        self.domain = context_data.get("domain", "")
        self.has_battery = context_data.get("has_battery", False)
        self.has_wifi = context_data.get("has_wifi", False)
        self.processor_family = context_data.get("processor_family", "")
        self.total_memory_gb = context_data.get("total_memory_gb", 0)
        self.os_type = context_data.get("os_type", "workstation")
        self.os_version = context_data.get("os_version", "")
        self.uptime_hours = context_data.get("uptime_hours", 0)
        self.is_domain_member = context_data.get("is_domain_member", False)

    def is_server(self) -> bool:
        return self.system_type == self.SYSTEM_TYPE_SERVER

    def is_notebook(self) -> bool:
        return self.system_type == self.SYSTEM_TYPE_NOTEBOOK

    def is_desktop(self) -> bool:
        return self.system_type == self.SYSTEM_TYPE_DESKTOP

    def is_old_machine(self) -> bool:
        """Detecta si la maquina tiene mas de 1 ano de uptime o es vieja."""
        return self.uptime_hours > 8760 or self.total_memory_gb < 4

    def is_new_machine(self) -> bool:
        """Detecta si es una maquina relativamente nueva (menos de 6 meses de uptime)."""
        return 0 < self.uptime_hours < 4320 and self.total_memory_gb >= 8

    def get_recommendations(self) -> list[str]:
        """Genera recomendaciones basadas en el contexto."""
        recommendations = []

        if self.is_old_machine():
            recommendations.append("Equipo con mucho tiempo de actividad. Considerar reinicio planificado.")

        if self.uptime_hours > 2000:
            recommendations.append(f"Uptime elevado: {self.uptime_hours} horas. Verificar necesidad de reinicio.")

        if self.is_virtual:
            recommendations.append("Equipo virtual detectado. Verificar recursos del host.")

        if self.has_battery and self.is_desktop():
            recommendations.append("Equipo de escritorio con bateria detectada. Posible conversion o error.")

        if self.is_server() and not self.is_domain_member:
            recommendations.append("Servidor sin membrecia de dominio. Verificar configuracion.")

        if self.total_memory_gb < 4:
            recommendations.append("Memoria RAM baja. Considerar actualizacion.")

        return recommendations


def detect_context_from_observations(observations: list) -> Optional[SystemContext]:
    """Detecta el contexto del sistema desde las observaciones de colectores."""
    context_data = {}

    # Buscar el colector de contexto
    for obs in observations:
        if hasattr(obs, 'collector_id') and obs.collector_id == 'system_context':
            if hasattr(obs, 'data'):
                context_data = obs.data if isinstance(obs.data, dict) else {}
                break

    if context_data:
        return SystemContext(context_data)

    return None


def get_context_aware_rules(system_type: str, is_old: bool = False) -> dict:
    """
    Devuelve las reglas adaptadas segun el contexto del sistema.

    Args:
        system_type: "desktop", "notebook", "server"
        is_old: Si es una maquina vieja

    Returns:
        Diccionario con configuraciones de reglas adaptadas
    """
    base_config = {
        "disk_space_warning": 20,
        "disk_space_critical": 10,
        "memory_warning": 85,
        "memory_critical": 95,
        "cpu_warning": 90,
        "spooler_required": True,
        "critical_services_required": True,
    }

    if system_type == "server":
        base_config.update({
            "disk_space_warning": 30,  # Servidores mas conservadores
            "disk_space_critical": 15,
            "spooler_required": False,  # Spooler no es critico en servidores
        })
    elif system_type == "notebook":
        base_config.update({
            "battery_check": True,
            "wifi_check": True,
        })

    if is_old:
        base_config.update({
            "disk_space_warning": 30,  # Maquinas viejas necesitan mas espacio
            "driver_check": True,
        })

    return base_config
