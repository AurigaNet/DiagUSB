# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Deteccion previa de hardware y conexiones para habilitar modulos.

El preflight es de solo lectura y rapido: consulta impresoras instaladas y
adaptadores de red, sin hacer ping ni ejecutar diagnosticos completos. Sus
resultados se usan para bloquear modulos que no aplican (por ejemplo,
Impresion si no hay ninguna impresora fisica) y para que la Revision Total
omita esos paquetes en lugar de ejecutarlos sin datos.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from diagusb.core import integridad
from diagusb.core.procesos import opciones_sin_ventana

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {"ts": 0.0, "data": None}
_TTL_SEGUNDOS = 6.0

_KIND_LABELS = {
    "ethernet": "Ethernet",
    "wifi": "WiFi",
    "bluetooth": "Bluetooth PAN",
    "usb_tethering": "Tethering USB",
    "wwan": "Banda ancha movil",
    "other": "Otra red",
}


def _ruta_script() -> Path:
    candidatos = []
    base_frozen = getattr(sys, "_MEIPASS", None)
    if base_frozen:
        candidatos.append(Path(base_frozen) / "collectors" / "capacidades.ps1")
    for padre in Path(__file__).resolve().parents:
        candidatos.append(padre / "collectors" / "capacidades.ps1")
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    return (Path(__file__).resolve().parents[2]
            / "collectors" / "capacidades.ps1")


def _ejecutar_script() -> dict:
    script = _ruta_script()
    if not script.is_file():
        return {"query": {"status": "error", "message": f"No se encontro {script}"},
                "data": []}

    ok, motivo = integridad.verificar(script)
    if ok:
        comun = integridad.localizar_common(script)
        if comun is not None:
            ok, motivo = integridad.verificar(comun)
    if not ok:
        return {"query": {"status": "error", "message": motivo}, "data": []}

    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **opciones_sin_ventana(),
        )
    except Exception as e:
        return {"query": {"status": "error", "message": str(e)}, "data": []}

    try:
        stdout, stderr = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return {"query": {"status": "timeout", "message": "Tiempo agotado"},
                "data": []}
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return {"query": {"status": "error", "message": str(e)}, "data": []}

    try:
        data = json.loads((stdout or "").strip())
    except (TypeError, ValueError):
        detalle = (stderr or "").strip().splitlines()
        return {"query": {"status": "error",
                          "message": detalle[-1] if detalle else "Sin salida"},
                "data": []}
    return data if isinstance(data, dict) else {"query": {"status": "error",
                                                          "message": "Salida invalida"},
                                                "data": []}


def _payload(raw: dict) -> dict:
    items = raw.get("data")
    if isinstance(items, list):
        return items[0] if items and isinstance(items[0], dict) else {}
    return items if isinstance(items, dict) else {}


def _resumen_tipos(kinds) -> str:
    vistos = []
    for kind in kinds or []:
        etiqueta = _KIND_LABELS.get(str(kind), str(kind))
        if etiqueta and etiqueta not in vistos:
            vistos.append(etiqueta)
    return ", ".join(vistos)


def _texto_resumen(data: dict) -> str:
    p = data.get("printers") or {}
    n = data.get("network") or {}
    partes = []

    if p.get("query_ok"):
        reales = int(p.get("real") or 0)
        virtuales = int(p.get("virtual") or 0)
        texto = f"Impresoras: {reales} fisica(s)"
        if virtuales:
            texto += f", {virtuales} virtual(es)"
        partes.append(texto)
    else:
        partes.append("Impresoras: sin verificar")

    if n.get("query_ok"):
        activos = _resumen_tipos(n.get("active_kinds"))
        partes.append("Red: " + (activos or "sin enlace activo"))
        if n.get("wifi_link"):
            partes.append("WiFi: conectado")
        elif n.get("wifi_enabled"):
            partes.append("WiFi: sin conexion")
        elif n.get("wifi_present"):
            partes.append("WiFi: deshabilitado")
        else:
            partes.append("WiFi: no detectado")
    else:
        partes.append("Red: sin verificar")

    cpu = data.get("cpu_temperature") or {}
    if cpu.get("available"):
        temperatura = cpu.get("max_temp_c")
        if isinstance(temperatura, (int, float)):
            partes.append(f"CPU: {float(temperatura):.0f} C")
        else:
            partes.append("CPU: LHM activo")
    elif cpu.get("process_running"):
        partes.append("CPU: LHM sin servidor web")
    else:
        partes.append("CPU: LHM inactivo")

    baterias = data.get("battery") or {}
    if baterias.get("query_ok"):
        if baterias.get("present"):
            partes.append("Bateria: presente")
        else:
            partes.append("Bateria: no detectada")
    else:
        partes.append("Bateria: sin verificar")
    return " - ".join(partes)


def _normalizar(raw: dict) -> dict:
    q = raw.get("query") or {}
    status = str(q.get("status") or "error")
    if status not in ("ok", "empty"):
        return {
            "ok": False,
            "timestamp": datetime.now().isoformat(),
            "error": str(q.get("message") or "No se pudieron detectar capacidades"),
            "printers": {},
            "network": {},
            "battery": {},
            "cpu_temperature": {},
            "resumen": "Deteccion de hardware no disponible",
        }

    payload = _payload(raw)
    printers = payload.get("printers") if isinstance(payload.get("printers"), dict) else {}
    network = payload.get("network") if isinstance(payload.get("network"), dict) else {}
    cpu = (payload.get("cpu_temperature")
           if isinstance(payload.get("cpu_temperature"), dict) else {})
    battery = (payload.get("battery")
               if isinstance(payload.get("battery"), dict) else {})

    printers = dict(printers)
    printers["query_ok"] = bool(payload.get("printer_query_ok", False))
    printers["error"] = payload.get("printer_error") or ""
    network = dict(network)
    network["query_ok"] = bool(payload.get("network_query_ok", False))
    network["error"] = payload.get("network_error") or ""
    cpu = dict(cpu)
    cpu["query_ok"] = bool(cpu.get("query_ok", False))
    cpu["available"] = bool(cpu.get("available", False))
    cpu["error"] = str(cpu.get("error") or "")
    cpu["url"] = str(cpu.get("url") or "http://127.0.0.1:8085")
    cpu["process_running"] = bool(cpu.get("process_running", False))
    battery = dict(battery)
    battery["query_ok"] = bool(battery.get("query_ok", False))
    battery["present"] = bool(battery.get("present", False))
    battery["count"] = int(battery.get("count") or 0)
    battery["error"] = str(battery.get("error") or "")

    data = {
        "ok": True,
        "timestamp": datetime.now().isoformat(),
        "printers": printers,
        "network": network,
        "battery": battery,
        "cpu_temperature": cpu,
    }
    data["resumen"] = _texto_resumen(data)
    return data


def detectar(force: bool = False) -> dict:
    """Devuelve capacidades actuales, usando cache corto salvo ``force``."""
    global _CACHE
    with _CACHE_LOCK:
        ahora = time.monotonic()
        cache = _CACHE.get("data")
        if (not force and cache is not None
                and ahora - float(_CACHE.get("ts") or 0) < _TTL_SEGUNDOS):
            return copy.deepcopy(cache)
        data = _normalizar(_ejecutar_script())
        if data.get("ok"):
            _CACHE = {"ts": ahora, "data": copy.deepcopy(data)}
        return data


def _disponible(motivo: str, warning: bool = False) -> dict:
    return {"available": True, "reason": motivo, "warning": warning}


def _no_disponible(motivo: str) -> dict:
    return {"available": False, "reason": motivo, "warning": False}


def evaluar_requisitos(requisitos, caps: dict) -> dict:
    """Evalua los requisitos de un paquete contra las capacidades detectadas.

    Si el preflight falla, se permite el diagnostico (fail-open) para no
    bloquear al usuario por un problema de deteccion.
    """
    reqs = [str(r) for r in (requisitos or []) if str(r).strip()]
    if not reqs:
        return _disponible("")

    if not caps.get("ok"):
        return _disponible(
            "No se pudo verificar el hardware; se permite el diagnostico.",
            warning=True)

    printers = caps.get("printers") or {}
    network = caps.get("network") or {}
    cpu = caps.get("cpu_temperature") or {}
    battery = caps.get("battery") or {}

    for req in reqs:
        if req == "printer":
            if not printers.get("query_ok"):
                return _disponible(
                    "No se pudieron verificar las impresoras; se permite el diagnostico.",
                    warning=True)
            reales = int(printers.get("real") or 0)
            if reales <= 0:
                if int(printers.get("virtual") or 0) > 0:
                    return _no_disponible(
                        "Solo se detectaron impresoras virtuales (PDF/XPS/Fax).")
                return _no_disponible("No se detecto ninguna impresora fisica.")
            offline = int(printers.get("offline") or 0)
            motivo = f"{reales} impresora(s) detectada(s)"
            if offline:
                motivo += f"; {offline} sin conexion (se puede diagnosticar)"
            return _disponible(motivo)

        if req == "network_adapter":
            if not network.get("query_ok"):
                return _disponible(
                    "No se pudieron verificar las placas de red; se permite el diagnostico.",
                    warning=True)
            if not network.get("has_adapter"):
                return _no_disponible("No se detecto ninguna placa de red fisica.")
            tipos = _resumen_tipos(network.get("present_kinds"))
            motivo = "Placas detectadas: " + (tipos or "sin clasificar")
            if network.get("virtual_only"):
                motivo = "Solo adaptadores virtuales: " + (tipos or "sin clasificar")
            if not network.get("has_link"):
                motivo += " (sin enlace activo)"
            return _disponible(motivo)

        if req == "network_link":
            if not network.get("query_ok"):
                return _disponible(
                    "No se pudo verificar el enlace de red; se permite el diagnostico.",
                    warning=True)
            if not network.get("has_link"):
                return _no_disponible("No hay un enlace de red activo.")
            tipos = _resumen_tipos(network.get("active_kinds"))
            motivo = "Enlace activo: " + (tipos or "red")
            if not network.get("has_ipv4"):
                motivo += " (sin IPv4; se puede diagnosticar)"
            elif not network.get("has_gateway"):
                motivo += " (sin gateway; se puede diagnosticar)"
            return _disponible(motivo)

        if req == "wifi_adapter":
            if not network.get("query_ok"):
                return _disponible(
                    "No se pudo verificar el WiFi; se permite el diagnostico.",
                    warning=True)
            if not network.get("wifi_present"):
                return _no_disponible("No se detecto ningun adaptador WiFi.")
            if network.get("wifi_link"):
                return _disponible("WiFi conectado.")
            if network.get("wifi_enabled"):
                return _disponible("WiFi detectado, sin conexion.")
            return _no_disponible("El adaptador WiFi esta deshabilitado.")

        if req == "battery":
            if not battery.get("query_ok"):
                return _disponible(
                    "No se pudo verificar si el equipo tiene bateria; se permite el diagnostico.",
                    warning=True)
            if not battery.get("present"):
                return _no_disponible(
                    "No se detecto ninguna bateria en este equipo.")
            return _disponible("Bateria presente.")

        if req == "cpu_temperature":
            if cpu.get("available"):
                nombre = str(cpu.get("cpu_name") or "").strip()
                motivo = "LibreHardwareMonitor activo"
                if nombre:
                    motivo += f" ({nombre})"
                return _disponible(motivo + ".")
            if cpu.get("process_running"):
                return _no_disponible(
                    str(cpu.get("error")
                        or "LibreHardwareMonitor esta abierto, pero el servidor web no responde."))
            return _no_disponible(
                str(cpu.get("error")
                    or "LibreHardwareMonitor no esta activo; no se puede leer la temperatura del CPU."))

        return _disponible("")

    return _disponible("")
