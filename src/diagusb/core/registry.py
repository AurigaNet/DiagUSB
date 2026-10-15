# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Registro de paquetes para DiagUSB."""

import json
from pathlib import Path
from typing import Any

from .models import CollectorManifest, PackageManifest


def _generate_label(collector_id: str) -> str:
    """
    Genera un label legible en español a partir de un ID de colector.

    Args:
        collector_id: ID del colector (ej: 'printers', 'print_jobs')

    Returns:
        Label legible en español (ej: 'Impresoras', 'Trabajos de Impresión')
    """
    # Mapeo de términos técnicos a español
    terminos_espanol = {
        "printers": "Impresoras",
        "print_jobs": "Trabajos de Impresión",
        "print_events": "Eventos de Impresión",
        "printer_drivers": "Controladores de Impresora",
        "printer_ports": "Puertos de Impresora",
        "spooler_service": "Servicio de Colas",
        "hardware": "Hardware",
        "os": "Sistema Operativo",
        "software": "Software Instalado",
        "patches": "Parches Instalados",
        "installed_software": "Software Instalado",
        "installed_patches": "Parches Instalados",
    }

    if collector_id in terminos_espanol:
        return terminos_espanol[collector_id]

    # Fallback: convertir snake_case a título con espacios
    # get_printers -> printers -> Impresoras
    label = collector_id.replace("_", " ")
    # Capitalizar cada palabra
    label = " ".join(word.capitalize() for word in label.split())
    return label


def _auto_discover_collectors(collectors_dir: Path) -> list[CollectorManifest]:
    """
    Auto-descubre colectores escaneando archivos .ps1 en el directorio.

    Args:
        collectors_dir: Ruta al directorio de colectores del paquete

    Returns:
        Lista de CollectorManifest generados automáticamente
    """
    collectors = []

    if not collectors_dir.exists():
        return collectors

    for item in collectors_dir.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() != ".ps1":
            continue

        # Extraer ID del nombre del archivo: get_printers.ps1 -> printers
        filename = item.stem  # get_printers
        if filename.startswith("get_"):
            collector_id = filename[4:]  # printers
        else:
            collector_id = filename

        label = _generate_label(collector_id)
        script = item.name  # get_printers.ps1

        collectors.append(CollectorManifest(
            id=collector_id,
            label=label,
            script=script
        ))

    return collectors


def discover_packages() -> list[PackageManifest]:
    """
    Descubre todos los paquetes disponibles en el directorio packages.

    Returns:
        Lista de PackageManifest con los datos de cada paquete.
    """
    packages = []

    # Obtener ruta al directorio de paquetes (src/diagusb/packages)
    packages_dir = Path(__file__).parent.parent / "packages"

    if not packages_dir.exists():
        return packages

    # Buscar directorios de paquetes
    for item in packages_dir.iterdir():
        if not item.is_dir():
            continue

        manifest_path = item / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            collectors_data = data.get("collectors", [])

            # Auto-descubrimiento si collectors es un diccionario vacío
            if collectors_data == {}:
                collectors_dir = item / "collectors"
                collectors = _auto_discover_collectors(collectors_dir)
            else:
                # Usar datos explícitos del manifest
                collectors = []
                for col_data in collectors_data:
                    collectors.append(CollectorManifest(
                        id=col_data.get("id", ""),
                        label=col_data.get("label", ""),
                        script=col_data.get("script", "")
                    ))

            package = PackageManifest(
                name=data.get("name", item.name),
                version=data.get("version", "1.0.0"),
                label=data.get("label", item.name),
                description=data.get("description", ""),
                symptoms=data.get("symptoms", []),
                collectors=collectors
            )
            packages.append(package)

        except Exception as e:
            # Ignorar paquetes con errores
            continue

    return packages


def build_package_menu() -> list[dict[str, Any]]:
    """
    Construye el menu de paquetes para el menu interactivo.

    Returns:
        Lista de diccionarios con id, label, description, symptoms, has_symptoms.
    """
    packages = discover_packages()
    menu = []

    for pkg in packages:
        has_symptoms = len(pkg.symptoms) > 0
        menu.append({
            "id": pkg.name,
            "label": pkg.label,
            "description": pkg.description,
            "symptoms": pkg.symptoms,
            "has_symptoms": has_symptoms
        })

    return menu
