# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Referencia por equipo guardada en el pendrive.

Una referencia es una captura del estado de los colectores cuando el equipo
funcionaba bien. Queda en ``config/referencias/<machine_id>.json`` y solo se
usa para comparar el estado actual del MISMO equipo (identidad estable de
``core.identidad``). Nunca modifica el sistema: solo lee resultados de
colectores ya ejecutados.

La comparacion genera diferencias objetivas (antes / ahora) y, para el
paquete de impresion, hallazgos que se suman al diagnostico del sintoma
"la impresora no imprime" de punta a punta: UI, informe y registro.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from . import almacen, rutas
from .models import Finding

SCHEMA_VERSION = 1
_MAX_DIFERENCIAS_HALLAZGO = 5

# Campos que cambian todo el tiempo y no describen una diferencia util.
_CAMPOS_VOLATILES = frozenset((
    "captured_at_utc", "duration_ms", "timeout_seconds", "timestamp",
    "uptime_hours", "cpu_usage", "cpu_percent", "cpu_percent_total",
    "memory_usage_percent", "physical_memory_usage_percent",
    "free_physical_memory_kb", "free_bytes", "free_gb", "free_space_gb",
    "used_percent", "used_percentage", "percent_disk_time",
    "current_disk_queue_length", "read_ops_per_sec", "write_ops_per_sec",
    "read_bytes_per_sec", "write_bytes_per_sec", "avg_transfer_sec",
    "temperature_c", "max_temp_c", "sensor_count",
))


def _texto(valor) -> str:
    return "" if valor is None else str(valor).strip()


def _slug(texto: str, maximo: int = 40) -> str:
    limpio = re.sub(r"[^a-z0-9-]+", "-", texto.lower()).strip("-")
    return limpio[:maximo] or "sin-id"


def _directorio(base_dir=None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    return rutas.dir_config() / "referencias"


def nombre_archivo(machine_id, computer_name: str = "") -> str:
    """Nombre estable del archivo de referencia para un equipo.

    Con ID fuerte/debil se usa el ID. Sin ID se usa un hash del nombre del
    equipo, para no mezclar referencias de equipos distintos en un mismo
    archivo llamado ``sin-id``.
    """
    identificador = _texto(machine_id).lower()
    if identificador:
        return _slug(identificador) + ".json"
    nombre = _texto(computer_name) or "equipo-desconocido"
    digest = hashlib.sha256(nombre.encode("utf-8")).hexdigest()[:8]
    return "sinid-" + _slug(nombre, 20) + "-" + digest + ".json"


def ruta(ident, base_dir=None) -> Path:
    ident = ident if isinstance(ident, dict) else {}
    return _directorio(base_dir) / nombre_archivo(
        ident.get("id"), ident.get("computer_name", ""))


def _mapa(results) -> dict:
    mapa = {}
    for resultado in results or []:
        if not isinstance(resultado, dict):
            continue
        collector_id = _texto(resultado.get("collector_id"))
        if not collector_id:
            continue
        query = resultado.get("query") if isinstance(resultado.get("query"), dict) else {}
        mapa[collector_id] = {
            "status": _texto(query.get("status")) or "unknown",
            "data": resultado.get("data"),
        }
    return mapa


def capturar(results, ident) -> dict:
    """Construye el documento de referencia a partir de results reales."""
    ident = ident if isinstance(ident, dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "capturada_en": datetime.now().isoformat(),
        "machine_id": _texto(ident.get("id")),
        "id_corto": _texto(ident.get("id_corto")),
        "computer_name": _texto(ident.get("computer_name")),
        "nivel": _texto(ident.get("nivel")),
        "colectores": _mapa(results),
    }


def guardar(results, ident, base_dir=None) -> dict:
    """Escribe la referencia del equipo de forma atomica y devuelve su estado."""
    documento = capturar(results, ident)
    destino = ruta(ident, base_dir)
    almacen.escribir_json_atomico(destino, documento, indent=1)
    return estado(ident, base_dir)


def cargar(ident, base_dir=None) -> dict | None:
    """Lee la referencia del equipo; None si no existe o esta corrupta."""
    destino = ruta(ident, base_dir)
    datos = almacen.leer_json(destino, preservar=True)
    if not isinstance(datos, dict):
        return None
    if not isinstance(datos.get("colectores"), dict):
        return None
    return datos


def estado(ident, base_dir=None) -> dict:
    """Estado de la referencia sin comparar nada (para la UI y el informe)."""
    destino = ruta(ident, base_dir)
    datos = cargar(ident, base_dir)
    if not datos:
        return {
            "disponible": False,
            "archivo": str(destino),
            "mensaje": "No hay una referencia guardada para este equipo.",
        }
    return {
        "disponible": True,
        "archivo": str(destino),
        "capturada_en": _texto(datos.get("capturada_en")),
        "computer_name": _texto(datos.get("computer_name")),
        "id_corto": _texto(datos.get("id_corto")),
        "colectores": len(datos.get("colectores") or {}),
        "mensaje": "Referencia guardada para este equipo.",
    }


def _por_nombre(items) -> dict:
    salida = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        clave = _texto(item.get("name") or item.get("device_id")
                       or item.get("instance_name"))
        if clave:
            salida[clave.lower()] = item
    return salida


def _diferencia(collector_id: str, campo: str, antes, ahora,
                severidad: str, mensaje: str) -> dict:
    return {
        "collector_id": collector_id,
        "campo": campo,
        "antes": antes,
        "ahora": ahora,
        "severidad": severidad,
        "mensaje": mensaje,
    }


def _diferencias_impresoras(antes, ahora) -> list[dict]:
    diffs: list[dict] = []
    previas = _por_nombre(antes)
    actuales = _por_nombre(ahora)
    for clave, previa in previas.items():
        nombre = _texto(previa.get("name")) or clave
        actual = actuales.get(clave)
        if actual is None:
            diffs.append(_diferencia(
                "printers", "impresora", nombre, "ausente", "error",
                f"La impresora '{nombre}' ya no esta instalada"))
            continue
        if bool(previa.get("work_offline")) is False and bool(actual.get("work_offline")) is True:
            diffs.append(_diferencia(
                "printers", "work_offline", False, True, "error",
                f"La impresora '{nombre}' quedo en modo sin conexion"))
        if bool(previa.get("default")) is True and bool(actual.get("default")) is False:
            diffs.append(_diferencia(
                "printers", "default", True, False, "warning",
                f"La impresora '{nombre}' dejo de ser la predeterminada"))
        if _texto(previa.get("port_name")) != _texto(actual.get("port_name")):
            diffs.append(_diferencia(
                "printers", "port_name", _texto(previa.get("port_name")),
                _texto(actual.get("port_name")), "warning",
                f"La impresora '{nombre}' cambio de puerto"))
        if _texto(previa.get("driver_name")) != _texto(actual.get("driver_name")):
            diffs.append(_diferencia(
                "printers", "driver_name", _texto(previa.get("driver_name")),
                _texto(actual.get("driver_name")), "warning",
                f"La impresora '{nombre}' cambio de controlador"))
        if bool(previa.get("shared")) is True and bool(actual.get("shared")) is False:
            diffs.append(_diferencia(
                "printers", "shared", True, False, "warning",
                f"La impresora '{nombre}' dejo de estar compartida"))
        for campo, etiqueta in (("printer_status", "estado"),
                                ("detected_error_state", "error detectado")):
            antes_val = previa.get(campo)
            ahora_val = actual.get(campo)
            if antes_val is not None and ahora_val is not None and antes_val != ahora_val:
                diffs.append(_diferencia(
                    "printers", campo, antes_val, ahora_val, "warning",
                    f"La impresora '{nombre}' cambio su {etiqueta}"))
    for clave, actual in actuales.items():
        if clave in previas:
            continue
        nombre = _texto(actual.get("name")) or clave
        diffs.append(_diferencia(
            "printers", "impresora", "ausente", nombre, "warning",
            f"Se agrego la impresora '{nombre}' despues de la referencia"))
    return diffs


def _diferencias_puertos(antes, ahora) -> list[dict]:
    diffs: list[dict] = []
    previos = _por_nombre(antes)
    actuales = _por_nombre(ahora)
    for clave, previo in previos.items():
        nombre = _texto(previo.get("name")) or clave
        actual = actuales.get(clave)
        if actual is None:
            diffs.append(_diferencia(
                "printer_ports", "puerto", nombre, "ausente", "error",
                f"El puerto de impresora '{nombre}' ya no existe"))
            continue
        if _texto(previo.get("host_address")) != _texto(actual.get("host_address")):
            diffs.append(_diferencia(
                "printer_ports", "host_address", _texto(previo.get("host_address")),
                _texto(actual.get("host_address")), "error",
                f"El puerto '{nombre}' apunta a otra direccion IP"))
        if previo.get("port_number") != actual.get("port_number"):
            diffs.append(_diferencia(
                "printer_ports", "port_number", previo.get("port_number"),
                actual.get("port_number"), "warning",
                f"El puerto '{nombre}' cambio de numero de puerto"))
        if _texto(previo.get("protocol")) != _texto(actual.get("protocol")):
            diffs.append(_diferencia(
                "printer_ports", "protocol", _texto(previo.get("protocol")),
                _texto(actual.get("protocol")), "warning",
                f"El puerto '{nombre}' cambio de protocolo"))
    return diffs


def _diferencias_spooler(antes, ahora) -> list[dict]:
    previo = antes.get("spooler") if isinstance(antes, dict) else None
    actual = ahora.get("spooler") if isinstance(ahora, dict) else None
    if not isinstance(previo, dict) or not isinstance(actual, dict):
        return []
    diffs = []
    estado_prev = _texto(previo.get("state"))
    estado_act = _texto(actual.get("state"))
    if estado_prev and estado_act and estado_prev.lower() != estado_act.lower():
        severidad = "critical" if estado_act.lower() != "running" else "warning"
        diffs.append(_diferencia(
            "spooler_service", "state", estado_prev, estado_act, severidad,
            "El servicio Print Spooler cambio de estado"))
    modo_prev = _texto(previo.get("start_mode"))
    modo_act = _texto(actual.get("start_mode"))
    if modo_prev and modo_act and modo_prev.lower() != modo_act.lower():
        diffs.append(_diferencia(
            "spooler_service", "start_mode", modo_prev, modo_act, "warning",
            "El servicio Print Spooler cambio su tipo de inicio"))
    return diffs


def _diferencias_trabajos(antes, ahora) -> list[dict]:
    n_antes = len(antes) if isinstance(antes, list) else 0
    n_ahora = len(ahora) if isinstance(ahora, list) else 0
    if n_ahora > n_antes:
        return [_diferencia(
            "print_jobs", "trabajos", n_antes, n_ahora, "warning",
            f"Quedaron {n_ahora} trabajo(s) de impresion en cola")]
    return []


def _comparar_impresion(previos: dict, actuales: dict) -> list[dict]:
    diffs: list[dict] = []
    if "printers" in previos and "printers" in actuales:
        diffs.extend(_diferencias_impresoras(
            previos["printers"].get("data"), actuales["printers"].get("data")))
    if "printer_ports" in previos and "printer_ports" in actuales:
        diffs.extend(_diferencias_puertos(
            previos["printer_ports"].get("data"),
            actuales["printer_ports"].get("data")))
    if "spooler_service" in previos and "spooler_service" in actuales:
        diffs.extend(_diferencias_spooler(
            previos["spooler_service"].get("data"),
            actuales["spooler_service"].get("data")))
    if "print_jobs" in previos and "print_jobs" in actuales:
        diffs.extend(_diferencias_trabajos(
            previos["print_jobs"].get("data"),
            actuales["print_jobs"].get("data")))
    return diffs


def comparar(ident, results, base_dir=None) -> dict:
    """Compara el estado actual con la referencia guardada del mismo equipo."""
    documento = cargar(ident, base_dir)
    if not documento:
        return {
            "disponible": False,
            "mensaje": "No hay una referencia guardada para este equipo.",
            "diferencias": [],
            "total_diferencias": 0,
        }
    id_ref = _texto(documento.get("machine_id"))
    id_actual = _texto((ident or {}).get("id"))
    if id_ref and id_actual and id_ref != id_actual:
        return {
            "disponible": True,
            "mismo_equipo": "distinto",
            "capturada_en": _texto(documento.get("capturada_en")),
            "id_corto": _texto(documento.get("id_corto")),
            "mensaje": ("La referencia guardada pertenece a otro equipo "
                        f"({_texto(documento.get('computer_name')) or 'sin nombre'}); "
                        "no se compara."),
            "diferencias": [],
            "total_diferencias": 0,
        }

    previos = documento.get("colectores") or {}
    actuales = _mapa(results)
    diffs = _comparar_impresion(previos, actuales)
    comparados = sorted(set(previos) & set(actuales))
    faltantes = sorted(set(previos) - set(actuales))
    orden = {"critical": 0, "error": 1, "warning": 2}
    diffs.sort(key=lambda d: orden.get(str(d.get("severidad")), 3))
    return {
        "disponible": True,
        "mismo_equipo": "igual",
        "capturada_en": _texto(documento.get("capturada_en")),
        "id_corto": _texto(documento.get("id_corto")),
        "colectores_comparados": comparados,
        "colectores_sin_dato_actual": faltantes,
        "total_diferencias": len(diffs),
        "diferencias": diffs,
        "mensaje": (f"{len(diffs)} diferencia(s) respecto de la referencia "
                    f"guardada el {_texto(documento.get('capturada_en')) or 'sin fecha'}."),
    }


def _finding_de(diferencia: dict, referencia: dict) -> Finding:
    return Finding(
        severity=str(diferencia.get("severidad") or "warning"),
        collector_id=str(diferencia.get("collector_id") or ""),
        message=str(diferencia.get("mensaje") or "Diferencia con la referencia"),
        details={
            "campo": diferencia.get("campo"),
            "antes": diferencia.get("antes"),
            "ahora": diferencia.get("ahora"),
            "referencia_capturada_en": referencia.get("capturada_en"),
            "origen": "referencia_equipo",
        },
        knowledge_id="referencia_impresion",
    )


def hallazgos(resultado: dict) -> list[Finding]:
    """Hallazgos del paquete de impresion a partir de las diferencias."""
    if not isinstance(resultado, dict) or not resultado.get("disponible"):
        return []
    if resultado.get("mismo_equipo") == "distinto":
        return []
    diffs = [d for d in (resultado.get("diferencias") or [])
             if isinstance(d, dict)
             and d.get("severidad") in ("critical", "error", "warning")]
    return [_finding_de(d, resultado) for d in diffs[:_MAX_DIFERENCIAS_HALLAZGO]]


def _finding_json(finding: Finding) -> dict:
    from . import knowledge_base as kb

    conocimiento = kb.knowledge_json(finding)
    return {
        "severity": finding.severity,
        "collector_id": finding.collector_id,
        "message": finding.message,
        "details": finding.details,
        "knowledge_id": finding.knowledge_id,
        "knowledge": conocimiento,
        "solutions": (conocimiento or {}).get("soluciones") or [],
    }


def aplicar_a_diagnostico(salida: dict, results, ident, base_dir=None) -> dict:
    """Agrega la referencia al payload del diagnostico y sus hallazgos.

    Solo el paquete ``impresion`` convierte las diferencias en hallazgos: es
    el modulo que usa la referencia de punta a punta. El resto de los paquetes
    recibe el estado de la referencia para mostrarlo en la UI y el informe.
    """
    resultado = comparar(ident, results, base_dir)
    resultado["estado"] = estado(ident, base_dir)
    salida["referencia"] = resultado
    if salida.get("package") != "impresion":
        return resultado
    for finding in hallazgos(resultado):
        salida.setdefault("findings", []).append(_finding_json(finding))
    return resultado
