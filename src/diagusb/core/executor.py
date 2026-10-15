# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Ejecutor de collectors de DiagUSB."""

import json
import subprocess
from pathlib import Path
from typing import Any

from diagusb.core import integridad


class TimeExpiredExpired(Exception):
    """Excepcion cuando un collector excede el timeout."""
    pass


class CollectorExecutor:
    """Ejecutor de scripts de collector de PowerShell."""

    PACKAGES_DIR = Path(__file__).resolve().parent.parent / "packages"
    TOOLS_DIR = PACKAGES_DIR

    def run(self, collector_script: str, timeout: int = 15) -> dict[str, Any]:
        """
        Ejecuta un script de collector .ps1 y devuelve el resultado JSON.

        Args:
            collector_script: Nombre del archivo .ps1 a ejecutar.
            timeout: Tiempo maximo de ejecucion en segundos.

        Returns:
            Diccionario con el resultado JSON del collector o clave 'error'.
        """
        script_path = self.TOOLS_DIR / collector_script
        if not script_path.suffix:
            script_path = script_path.with_suffix(".ps1")

        if not script_path.exists():
            return {"error": f"Script no encontrado: {script_path}"}

        ok_firma, motivo = integridad.verificar(script_path)
        if ok_firma:
            comun = integridad.localizar_common(script_path)
            if comun is not None:
                ok_firma, motivo = integridad.verificar(comun)
        if not ok_firma:
            return {"error": motivo}

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0 and stderr:
                return {"error": stderr}

            if not stdout:
                return {"error": "Sin salida del collector"}

            return json.loads(stdout)

        except subprocess.TimeoutExpired:
            raise TimeExpiredExpired(f"El collector excedio el timeout de {timeout} segundos")
        except json.JSONDecodeError as e:
            return {"error": f"Error al parsear JSON: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def run_package_collector(
        self, package_name: str, collector_script: str, timeout: int = 15
    ) -> dict[str, Any]:
        """
        Ejecuta un script de collector de un paquete especifico.

        Args:
            package_name: Nombre del paquete.
            collector_script: Nombre del archivo .ps1 a ejecutar.
            timeout: Tiempo maximo de ejecucion en segundos.

        Returns:
            Diccionario con el resultado JSON del collector o clave 'error'.
        """
        script_path = self.PACKAGES_DIR / package_name / "collectors" / collector_script
        if not script_path.suffix:
            script_path = script_path.with_suffix(".ps1")

        if not script_path.exists():
            return {"error": f"Script no encontrado: {script_path}"}

        ok_firma, motivo = integridad.verificar(script_path)
        if ok_firma:
            comun = integridad.localizar_common(script_path)
            if comun is not None:
                ok_firma, motivo = integridad.verificar(comun)
        if not ok_firma:
            return {"error": motivo}

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0 and stderr:
                return {"error": stderr}

            if not stdout:
                return {"error": "Sin salida del collector"}

            return json.loads(stdout)

        except subprocess.TimeoutExpired:
            raise TimeExpiredExpired(f"El collector excedio el timeout de {timeout} segundos")
        except json.JSONDecodeError as e:
            return {"error": f"Error al parsear JSON: {e}"}
        except Exception as e:
            return {"error": str(e)}
