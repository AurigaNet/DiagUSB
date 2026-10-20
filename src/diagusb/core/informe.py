# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modelo y generadores de informes completos DiagUSB (HTML, Word .doc, PDF).

Sin dependencias externas: el PDF se genera con un motor minimo propio y
el Word es un HTML con la cabecera especifica de Microsoft Word.
"""

import base64
import hashlib
import html
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import knowledge_base as kb
from .metricas import nivel_medidor as medidores_nivel
from .graficos import (PALETA as _PALETA, arcos_bezier as _arcos_bezier,
                       porciones as _porciones, porciones_simples as _porciones_simples,
                       rgb_de as _rgb_de, svg_dona as _svg_dona,
                       svg_torta as _svg_torta)
from .graficos_png import (imagen_barra as _png_barra,
                           imagen_dona as _png_dona,
                           imagen_torta as _png_torta)

SEVERIDAD_LABEL = {
    "critical": "CRÍTICO",
    "error": "ERROR",
    "warning": "ADVERTENCIA",
    "ok": "OK",
}

ESTADOS_ACCION = [
    "Pendiente",
    "Resuelto",
    "Resuelto parcialmente",
    "No reproducido",
    "Requiere repuestos",
    "Requiere administrador",
    "Derivado / escalar",
]

_RECOMENDACIONES_CATALOGO = {
    ("logical_disks", "critical"): "Libere espacio inmediatamente en la unidad afectada (temporales, descargas, papelera de reciclaje) o migre datos a otro disco. Verifique luego del proceso el porcentaje de espacio libre.",
    ("logical_disks", "warning"): "Programe una limpieza de espacio en disco y monitoree la unidad. Considere expandir la capacidad si el uso sigue en aumento.",
    ("physical_disks", "error"): "El disco físico reporta estado no óptimo. Realice un respaldo urgente, verifique SMART/cable SATA y planifique el reemplazo del disco.",
    ("disk_performance", "warning"): "La cola de disco está elevada. Verifique procesos con alta actividad de E/S, desactive indexación temporalmente y considere migrar a SSD.",
    ("spooler_service", "error"): "Reinicie el servicio Print Spooler, verifique permisos de la carpeta %SystemRoot%\\System32\\spool\\PRINTERS y revise el disco del spooler.",
    ("printers", "error"): "Verifique que la impresora esté encendida, seleccionada como predeterminada y que el puerto apunte al equipo/IP correcto.",
    ("critical_services", "error"): "Inicie el servicio afectado y configure su tipo de inicio en Automático. Revise el visor de eventos si el servicio se detiene reiteradamente.",
    ("memory_status", "warning"): "Cierre aplicaciones consumidoras de memoria. Verifique fugas de memoria y considere ampliar la RAM si el uso se mantiene alto.",
    ("network_adapters", "error"): "Habilite el adaptador de red afectado, reinstale el driver o verifique el cable/switch.",
    ("firewall_status", "warning"): "Rehabilite el perfil de firewall afectado y revise las políticas de grupo que pudieron desactivarlo.",
}

_RECOMENDACIONES_SEVERIDAD = {
    "critical": "Problema crítico: requiere atención prioritaria antes de continuar con otras tareas.",
    "error": "Revise el detalle del problema y aplique la acción correctiva correspondiente.",
    "warning": "Advertencia: monitoree la situación y programe mantenimiento preventivo.",
}

# Lista de opciones de solucion por tipo de problema (colector, severidad)
SOLUCIONES_POR_PROBLEMA = {
    ("logical_disks", "critical"): [
        "Eliminar archivos temporales, descargas y papelera de reciclaje",
        "Ejecutar limpieza de disco del sistema (cleanmgr) y Storage Sense",
        "Mover archivos grandes/datos a otra unidad",
        "Desinstalar aplicaciones pesadas o migrar perfiles a otro disco",
        "Ampliar la capacidad del disco o reemplazarlo por uno mayor",
    ],
    ("logical_disks", "warning"): [
        "Programar limpieza de espacio periódica",
        "Habilitar Storage Sense para limpieza automática",
        "Mover archivos grandes a otra unidad",
        "Revisar carpetas de temporales y caché de navegadores",
    ],
    ("physical_disks", "error"): [
        "Realizar respaldo inmediato de datos críticos",
        "Reemplazar el disco (salud degradada)",
        "Verificar cable SATA/alimentación y reasentar el conector",
        "Ejecutar verificación chkdsk y SMART extendido",
    ],
    ("disk_performance", "warning"): [
        "Migrar el sistema a un disco SSD",
        "Reducir procesos con alta actividad de E/S",
        "Desactivar indexación temporalmente",
        "Actualizar drivers de almacenamiento",
    ],
    ("spooler_service", "error"): [
        "Reiniciar el servicio Print Spooler",
        "Limpiar la cola de impresión y la carpeta spool",
        "Configurar el servicio en tipo de inicio Automático",
        "Reinstalar drivers de impresión",
    ],
    ("printers", "error"): [
        "Verificar encendido y conexión de la impresora",
        "Reasignar el puerto TCP/IP correcto",
        "Desinstalar y reinstalar la impresora",
        "Imprimir página de prueba y vaciar cola de trabajos",
    ],
    ("critical_services", "error"): [
        "Iniciar el servicio y configurarlo en Automático",
        "Revisar dependencias del servicio",
        "Consultar el visor de eventos para la causa de la detención",
    ],
    ("memory_status", "warning"): [
        "Cerrar aplicaciones que consumen memoria",
        "Revisar procesos con fugas (Monitor de recursos)",
        "Ampliar la memoria RAM física",
        "Ajustar el archivo de paginación",
    ],
    ("network_adapters", "error"): [
        "Habilitar el adaptador de red",
        "Reinstalar o actualizar el driver de red",
        "Probar otro cable/switch/puerto",
        "Restablecer configuración de red (netsh winsock/reset)",
    ],
    ("firewall_status", "warning"): [
        "Rehabilitar el perfil de firewall afectado",
        "Revisar políticas de grupo o endpoint que lo desactivaron",
        "Restaurar la configuración de firewall predeterminada",
    ],
}

_SOLUCIONES_SEVERIDAD = {
    "critical": [
        "Aplicar acción correctiva inmediata",
        "Verificar el problema luego de la intervención",
        "Escalar a soporte superior si persiste",
    ],
    "error": [
        "Aplicar la acción correctiva sugerida",
        "Verificar el comportamiento luego de la intervención",
    ],
    "warning": [
        "Programar mantenimiento preventivo",
        "Monitorear la situación periódicamente",
    ],
}


def soluciones_para(colector: str, severidad: str) -> list[str]:
    """Devuelve la lista de opciones de solucion para un problema dado."""
    return list(
        SOLUCIONES_POR_PROBLEMA.get((colector, severidad))
        or _SOLUCIONES_SEVERIDAD.get(severidad, _SOLUCIONES_SEVERIDAD["warning"])
    )


def recomendacion_para(colector: str, severidad: str) -> str:
    return (
        _RECOMENDACIONES_CATALOGO.get((colector, severidad))
        or _RECOMENDACIONES_SEVERIDAD.get(severidad, "")
    )


def mejoras_sugeridas(results: list[dict]) -> list[dict]:
    """Analiza los resultados de los colectores y sugiere mejoras (no problemas).

    Devuelve lista de {id, titulo, detalle}.
    """
    mejoras: list[dict] = []
    vistos: set[str] = set()

    def add(mid: str, titulo: str, detalle: str):
        if mid not in vistos:
            vistos.add(mid)
            mejoras.append({"id": mid, "titulo": titulo, "detalle": detalle})

    for r in results:
        if not isinstance(r, dict):
            continue
        cid = r.get("collector_id", "")
        query = r.get("query", {}) or {}
        if query.get("status") != "ok":
            continue
        data = r.get("data")

        if cid == "logical_disks" and isinstance(data, list):
            for d in data:
                if not isinstance(d, dict):
                    continue
                free = d.get("free_percent")
                dev = d.get("device_id", "?")
                if isinstance(free, (int, float)) and 20 <= free < 40:
                    add(f"espacio_{dev}",
                        f"Espacio holgado pero menguante en {dev} ({free:.0f}% libre)",
                        "Considere una limpieza preventiva y monitoreo del uso de la unidad.")
        elif cid == "physical_disks" and isinstance(data, list):
            for d in data:
                if not isinstance(d, dict):
                    continue
                if d.get("media_type") == "HDD":
                    add("migrar_ssd",
                        "Disco mecánico (HDD) detectado",
                        "La migración a SSD mejora notablemente el arranque y la respuesta del equipo.")
                temp = d.get("temperature")
                if isinstance(temp, (int, float)) and temp >= 50:
                    add("temperatura",
                        "Temperatura de disco elevada",
                        "Verifique la ventilación del gabinete y la limpieza de polvo.")
        elif cid == "memory_status" and isinstance(data, dict):
            usage = data.get("physical_memory_usage_percent")
            if isinstance(usage, (int, float)) and 65 <= usage < 85:
                add("memoria_preventiva",
                    f"Uso de memoria física en {usage:.0f}%",
                    "Revise procesos en el administrador de tareas y programe ampliación si el uso sigue subiendo.")
        elif cid == "disk_performance" and isinstance(data, list):
            for d in data:
                if isinstance(d, dict) and isinstance(d.get("current_disk_queue_length"), (int, float)) \
                        and d["current_disk_queue_length"] >= 1:
                    add("cola_disco",
                        "Actividad de disco continua (cola > 0)",
                        "Reduzca tareas simultáneas de E/S y verifique procesos en segundo plano.")
        elif cid == "firewall_status" and isinstance(data, list):
            off = [d.get("name") for d in data if isinstance(d, dict) and not d.get("enabled")]
            if off:
                add("firewall_off",
                    f"Firewall deshabilitado en perfil(s): {', '.join(str(x) for x in off)}",
                    "La seguridad del equipo queda expuesta; reactive el firewall.")
        elif cid == "installed_software" and query.get("status") == "error":
            add("inventario_admin",
                "Inventario de software incompleto (requiere permisos)",
                "Ejecute la herramienta como Administrador para obtener el inventario completo.")

    # installed_software no llega aqui por el filtro status==ok; evaluar aparte
    for r in results:
        if isinstance(r, dict) and r.get("collector_id") == "installed_software" \
                and (r.get("query", {}) or {}).get("status") == "error":
            add("inventario_admin",
                "Inventario de software incompleto (requiere permisos)",
                "Ejecute la herramienta como Administrador para obtener el inventario completo.")

    return mejoras


@dataclass
class InformeProblema:
    indice: int
    severidad: str
    colector: str
    titulo: str
    detalle: dict = field(default_factory=dict)
    recomendacion: str = ""
    soluciones: list[str] = field(default_factory=list)
    solucion_elegida: str = ""
    estado: str = "Pendiente"
    solucion: str = ""
    knowledge_id: str = ""
    estado_esperado: str = ""
    por_que: str = ""
    verificacion: str = ""
    grupo: list[str] = field(default_factory=list)


@dataclass
class InformeMejora:
    id: str = ""
    titulo: str = ""
    detalle: str = ""
    aplicada: bool = False
    comentario: str = ""


@dataclass
class InformeColector:
    collector_id: str
    status: str
    duration_ms: int = 0
    resumen: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    limitado: str = ""


@dataclass
class InformeData:
    generado_en: str = ""
    equipo: dict = field(default_factory=dict)
    paquete: dict = field(default_factory=dict)
    resumen: dict = field(default_factory=dict)
    colectores: list[InformeColector] = field(default_factory=list)
    problemas: list[InformeProblema] = field(default_factory=list)
    mejoras: list[InformeMejora] = field(default_factory=list)
    recomendaciones: list[str] = field(default_factory=list)
    tecnico: str = ""
    cliente: str = ""
    observaciones: str = ""
    diferencias: list[dict] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    metricas: dict = field(default_factory=dict)
    metricas_base: dict = field(default_factory=dict)
    metricas_actual: dict = field(default_factory=dict)
    resultados: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Construccion del informe desde el payload del diagnostico
# ---------------------------------------------------------------------------

_CLAVES_HUMANAS = {
    "device_id": "unidad", "free_percent": "libre", "size_gb": "tamaño",
    "free_space_gb": "espacio libre", "total_size_gb": "tamaño total",
    "media_type": "tipo de medio", "status": "estado", "health_status": "salud",
    "temperature": "temperatura °C", "model": "modelo", "serial": "número de serie",
    "physical_memory_usage_percent": "uso de memoria", "cpu_usage": "uso de CPU",
    "current_disk_queue_length": "cola de disco", "ip_address": "dirección IP",
    "ipv4_address": "IPv4", "gateway": "puerta de enlace", "dns_servers": "DNS",
    "mac_address": "MAC", "description": "descripción", "name": "nombre",
    "display_name": "nombre visible", "state": "estado", "start_mode": "inicio",
    "driver_version": "versión", "driver_date": "fecha del driver",
    "device_name": "dispositivo", "manufacturer": "fabricante",
    "version": "versión", "build": "compilación", "caption": "sistema",
    "computer_name": "equipo", "user": "usuario", "is_elevated": "permisos elevados",
    "ssid": "red", "signal": "señal", "channel": "canal", "authentication": "autenticación",
    "kb": "KB", "titulo": "título", "importancia": "importancia",
    "actualizaciones_pendientes": "pendientes", "enabled": "activado",
    "profile": "perfil", "interface": "interfaz", "speed_mbps": "velocidad",
}


def _par_humano(k: str, v: Any) -> str:
    etiqueta = _CLAVES_HUMANAS.get(k, str(k).replace("_", " "))
    if isinstance(v, bool):
        valor = "Sí" if v else "No"
    elif isinstance(v, (dict, list)):
        valor = f"[{len(v)} elementos]"
    elif v is None:
        valor = "-"
    else:
        valor = str(v)
    return f"{etiqueta}: {valor}"


def _resumen_datos(data: Any, collector_id: str = "") -> list[str]:
    """Convierte los datos de un colector en lineas legibles para el informe."""
    lines: list[str] = []

    if collector_id == "logical_disks" and isinstance(data, list):
        for d in data:
            if not isinstance(d, dict):
                continue
            dev = d.get("device_id") or "?"
            partes = []
            free = d.get("free_percent")
            if isinstance(free, (int, float)):
                partes.append(f"{free:.0f}% libre")
            sg = d.get("size_gb") or d.get("total_size_gb")
            if isinstance(sg, (int, float)):
                partes.append(f"{sg:.0f} GB")
            fs = d.get("free_space_gb")
            if isinstance(fs, (int, float)):
                partes.append(f"({fs:.0f} GB disponibles)")
            if d.get("status"):
                partes.append(f"estado {d['status']}")
            lines.append(f"{dev} — " + (", ".join(partes) if partes else "sin datos de espacio"))
        return lines

    if collector_id == "installed_software" and isinstance(data, list):
        return [f"Software instalado: {len(data)} aplicaciones"]

    if collector_id == "pending_updates" and isinstance(data, (dict, list)):
        d = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data
        if isinstance(d, dict) and "actualizaciones_pendientes" in d:
            return [f"Actualizaciones pendientes: {d.get('actualizaciones_pendientes')}"]

    if collector_id == "memory_status" and isinstance(data, dict):
        usage = data.get("physical_memory_usage_percent")
        if isinstance(usage, (int, float)):
            return [f"Uso de memoria física: {usage:.0f}%"]

    if isinstance(data, list):
        lines.append(f"Registros: {len(data)}")
        for i, item in enumerate(data[:8], 1):
            if isinstance(item, dict):
                lines.append(f"  [{i}] " + ", ".join(
                    _par_humano(k, v) for k, v in list(item.items())[:6]))
        if len(data) > 8:
            lines.append(f"  ... y {len(data) - 8} registro(s) más (ver anexo)")
    elif isinstance(data, dict):
        for k, v in list(data.items())[:12]:
            lines.append(_par_humano(k, v))
        if len(data) > 12:
            lines.append(f"... y {len(data) - 12} campo(s) más (ver anexo)")
    elif data:
        lines.append(str(data))
    return lines


def _knowledge_de(f: dict) -> dict | None:
    """Entrada de la base de conocimiento de un finding (payload o por colector)."""
    if isinstance(f.get("knowledge"), dict) and f["knowledge"].get("estado_esperado"):
        return f["knowledge"]
    entradas = kb.por_colector(f.get("collector_id", ""))
    if not entradas and f.get("knowledge_id"):
        e = kb.buscar(f.get("knowledge_id"))
        entradas = [e] if e else []
    return kb.entrada_json(entradas[0]) if entradas else None


_ESTADOS_NO_EVALUADO = ("denied", "not_available", "error", "timeout")


def _primer_dict(data: Any) -> dict | None:
    """Primer diccionario de los datos de un colector (llegan como lista)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict):
                return x
    return None


def _limitado_de(collector_id: str, data: Any, status: str) -> str:
    """Razon por la que un colector devolvio datos parciales ('' si completo).

    Un colector puede terminar en ``ok`` y aun asi no haber leido todo: por
    falta de permisos (``installed_software``) o porque un disco no-USB no
    aporto su fiabilidad (``physical_disks``). Las unidades USB se excluyen:
    su falta de fiabilidad es esperada y no cuenta como dato limitado.
    """
    if status != "ok":
        return ""
    if collector_id == "installed_software":
        d = _primer_dict(data)
        if d is not None and d.get("optional_features_available") is False:
            return "requiere administrador"
    if collector_id == "physical_disks":
        for x in (data if isinstance(data, list) else [data]):
            if not isinstance(x, dict) or x.get("reliability") is not None:
                continue
            if str(x.get("bus_type") or "").upper() == "USB":
                continue
            if x.get("reliability_motivo"):
                return "confiabilidad no disponible"
    return ""


def no_evaluados(informe: InformeData) -> list[str]:
    """Colectores del informe que no se pudieron evaluar (permisos/error)."""
    return [c.collector_id for c in informe.colectores
            if c.status in _ESTADOS_NO_EVALUADO]


def datos_limitados(informe: InformeData) -> list[str]:
    """Colectores con datos parciales por permisos, como 'id (razon)'."""
    return [f"{c.collector_id} ({c.limitado})" for c in informe.colectores
            if c.limitado]


def linea_alcance(informe: InformeData) -> str:
    """Linea 'Alcance: ...' con el modo, no evaluados y datos limitados."""
    modo = "administrador" if informe.equipo.get("is_elevated") else "estándar"
    no_eval = no_evaluados(informe)
    lista = ", ".join(no_eval) if no_eval else "ninguno"
    linea = f"Alcance: modo {modo}; no evaluados: {lista}"
    lim = datos_limitados(informe)
    if lim:
        linea += "; datos limitados: " + ", ".join(lim)
    return linea


def informe_desde_diagnostico(diag: dict, acciones: list[dict] | None = None,
                              mejoras_acciones: list[dict] | None = None,
                              tecnico: str = "", cliente: str = "",
                              observaciones: str = "",
                              diferencias: list[dict] | None = None,
                              comparacion_forzada: bool = False,
                              metricas_base: dict | None = None,
                              metricas_actual: dict | None = None) -> InformeData:
    """Construye el informe a partir del payload de /api/diagnose (o CLI)."""
    now = diag.get("timestamp") or datetime.now().isoformat()

    equipo = {}
    for r in diag.get("results", []):
        ctx = r.get("context") if isinstance(r, dict) else None
        if isinstance(ctx, dict) and ctx.get("computer_name"):
            win = ctx.get("windows", {}) or {}
            equipo = {
                "computer_name": ctx.get("computer_name", ""),
                "user": ctx.get("user", ""),
                "is_elevated": ctx.get("is_elevated", False),
                "os": win.get("caption", ""),
                "os_version": win.get("version", ""),
                "build": win.get("build_number", ""),
            }
            break

    colectores: list[InformeColector] = []
    for r in diag.get("results", []):
        if not isinstance(r, dict):
            continue
        query = r.get("query", {}) or {}
        errores = []
        for e in r.get("errors", []) or []:
            if isinstance(e, dict):
                errores.append(e.get("message", ""))
            else:
                errores.append(str(e))
        if not errores and query.get("message"):
            errores.append(str(query["message"]))
        colectores.append(InformeColector(
            collector_id=r.get("collector_id", "desconocido"),
            status=query.get("status", "unknown"),
            duration_ms=query.get("duration_ms", 0),
            resumen=_resumen_datos(r.get("data"), r.get("collector_id", "")),
            errores=[e for e in errores if e],
            limitado=_limitado_de(r.get("collector_id", ""), r.get("data"),
                                  query.get("status", "")),
        ))

    problemas: list[InformeProblema] = []
    for i, f in enumerate(diag.get("findings", []) or [], 1):
        severidad = f.get("severity", "warning")
        colector = f.get("collector_id", "")
        k = _knowledge_de(f)
        sols = (
            list(f.get("solutions") or [])
            or list((k or {}).get("soluciones") or [])
            or soluciones_para(colector, severidad)
        )
        problemas.append(InformeProblema(
            indice=i,
            severidad=severidad,
            colector=colector,
            titulo=f.get("message", "Problema detectado"),
            detalle=f.get("details", {}) or {},
            recomendacion=f.get("recommendation") or recomendacion_para(colector, severidad),
            soluciones=sols,
            knowledge_id=(k or {}).get("id", ""),
            estado_esperado=(k or {}).get("estado_esperado", ""),
            por_que=(k or {}).get("por_que_importa", ""),
            verificacion=(k or {}).get("verificacion", ""),
            grupo=[m for m in (f.get("details", {}) or {}).get("grupo_mensajes", []) or []
                   if m != f.get("message")],
        ))

    acciones = acciones or []
    for acc in acciones:
        try:
            idx = int(acc.get("indice", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(problemas):
            estado = acc.get("estado") or "Pendiente"
            if estado not in ESTADOS_ACCION:
                estado = "Pendiente"
            problemas[idx].estado = estado
            problemas[idx].solucion = (acc.get("solucion") or "").strip()
            problemas[idx].solucion_elegida = (acc.get("solucion_elegida") or "").strip()

    mejoras: list[InformeMejora] = []
    acciones_mejora = {m.get("id"): m for m in (mejoras_acciones or []) if isinstance(m, dict)}
    for m in mejoras_sugeridas(diag.get("results", []) or []):
        acc = acciones_mejora.get(m["id"], {})
        mejoras.append(InformeMejora(
            id=m["id"],
            titulo=m["titulo"],
            detalle=m["detalle"],
            aplicada=bool(acc.get("aplicada")),
            comentario=(acc.get("comentario") or "").strip(),
        ))

    n_crit = sum(1 for p in problemas if p.severidad == "critical")
    n_err = sum(1 for p in problemas if p.severidad == "error")
    n_warn = sum(1 for p in problemas if p.severidad == "warning")

    advertencias = []
    if comparacion_forzada:
        advertencias.append(
            "ADVERTENCIA: la comparación se hizo entre equipos distintos")

    return InformeData(
        generado_en=now,
        equipo=equipo,
        paquete={
            "name": diag.get("package", ""),
            "label": diag.get("package_label", diag.get("package", "")),
            "symptom": diag.get("symptom", ""),
        },
        resumen={
            "colectores_total": diag.get("collectors_count", len(colectores)),
            "colectores_ok": diag.get("ok_count", 0),
            "colectores_error": diag.get("error_count", 0),
            "problemas_total": len(problemas),
            "criticos": n_crit,
            "errores": n_err,
            "advertencias": n_warn,
        },
        colectores=colectores,
        problemas=problemas,
        mejoras=mejoras,
        recomendaciones=list(diag.get("recommendations", []) or []),
        tecnico=tecnico,
        cliente=cliente,
        observaciones=observaciones,
        diferencias=[d for d in (diferencias or []) if isinstance(d, dict)],
        advertencias=advertencias,
        metricas=diag.get("metricas") if isinstance(diag.get("metricas"), dict) else {},
        metricas_base=metricas_base or {},
        metricas_actual=metricas_actual or {},
        resultados=[r for r in (diag.get("results") or []) if isinstance(r, dict)],
    )


# ---------------------------------------------------------------------------
# HTML (base para navegador y Word)
# ---------------------------------------------------------------------------

_SEVERIDAD_COLOR = {
    "critical": "#b00020",
    "error": "#d93025",
    "warning": "#e37400",
    "ok": "#188038",
}

_CSS_PRINT = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #222; margin: 24px; font-size: 12px; }
h1 { font-size: 20px; border-bottom: 2px solid #1a73e8; padding-bottom: 6px; color: #1a73e8; }
h2 { font-size: 15px; margin-top: 22px; color: #1a73e8; border-bottom: 1px solid #ddd; padding-bottom: 3px; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; overflow-wrap: anywhere; margin: 8px 0; }
th, td { border: 1px solid #ccc; padding: 5px 8px; text-align: left; vertical-align: top; }
th, td.th { background: #f1f3f4; font-weight: 700; }
.kv td:first-child { background: #f8f9fa; font-weight: 600; width: 220px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; color: #fff; font-size: 10px; font-weight: 700; }
.problema { border: 1px solid #ddd; border-left: 5px solid #888; padding: 10px; margin: 10px 0; }
.problema h3 { margin: 0 0 6px 0; font-size: 13px; }
.muted { color: #666; }
.advertencia { background: #fff3cd; border: 1px solid #e0a800; color: #7a4f00; padding: 10px; margin: 10px 0; font-size: 13px; }
.mono { font-family: Consolas, monospace; font-size: 11px; white-space: pre-wrap; }
.firma { width: 100%; margin-top: 40px; border-collapse: collapse; }
.firma td { width: 50%; border: none; border-top: 1px solid #333; padding-top: 4px; text-align: center; }
@media print { body { margin: 0; } .no-print { display: none; } }
"""

# CSS para el .doc de Word (el cuerpo HTML se reutiliza, pero Word no hereda
# la hoja del navegador: se inyecta en el <style> del documento Office).
_CSS_WORD = """
body { font-family: 'Segoe UI', Arial, sans-serif; color: #222; font-size: 10pt; }
h1 { font-size: 18pt; color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 4px; }
h2 { font-size: 13pt; color: #1a73e8; margin-top: 16pt; border-bottom: 1px solid #ddd; padding-bottom: 2px; }
h3 { font-size: 11pt; margin: 0 0 4pt 0; }
table { border-collapse:collapse; width:100%; table-layout:fixed; mso-table-layout-alt:fixed; word-break:break-all; margin: 6pt 0; }
td, th { border: 1px solid #999; padding: 4px; vertical-align: top; font-size: 10pt; }
th, td.th { background: #f1f3f4; text-align: left; font-weight: 700; }
.kv td:first-child { width: 30%; font-weight: 600; background: #f8f9fa; }
.mono { font-family: Consolas, monospace; font-size: 9pt; white-space: pre-wrap; word-wrap:break-word; }
.muted { color: #666; }
.badge { display: inline-block; padding: 2px 6px; color: #fff; font-size: 8pt; font-weight: 700; }
.problema { border-left: 4px solid #888; padding: 8px; margin: 8px 0; }
.advertencia { background: #fff3cd; border-left: 4px solid #e0a800; color: #7a4f00; padding: 8px; }
.firma { width: 100%; margin-top: 40px; border-collapse: collapse; }
.firma td { width: 50%; border: none; border-top: 1px solid #333; padding-top: 4px; text-align: center; }
.portada { page-break-after: always; }
.portada-banda { background: #0F1F35; color: #ffffff; padding: 10pt; }
.portada-marca { font-size: 20pt; font-weight: 700; color: #ffffff; }
.portada-sub { font-size: 9pt; color: #b8c6db; }
.portada-titulo { font-size: 18pt; color: #0F1F35; }
.tarjetas { width: 100%; }
.tarjeta { border: 1px solid #ccc; padding: 6pt; margin: 4pt 0; }
.tarjeta-titulo { font-size: 8pt; color: #666; }
.tarjeta-valor { font-size: 14pt; font-weight: 700; }
.tarjeta-detalle { font-size: 8pt; color: #555; }
.panel-grafico { width: 100%; }
.grafico-celda { border: 1px solid #e3e7ec; padding: 6pt; margin: 4pt 0; }
.mini-titulo { font-size: 9pt; color: #444; }
"""


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _fmt_valor(v: Any) -> str:
    if isinstance(v, bool):
        return "Sí" if v else "No"
    if v is None:
        return "-"
    return str(v)


def _fmt_valor_truncado(v: Any) -> str:
    """Valor de una diferencia, acotado para caber en una tabla."""
    if isinstance(v, (dict, list)):
        n = len(v)
        if isinstance(v, dict):
            return f"[{n} campos] " + json.dumps(v, ensure_ascii=False)[:100]
        return f"[{n} registros] " + json.dumps(v[:3], ensure_ascii=False)[:100]
    s = _fmt_valor(v)
    return s if len(s) <= 160 else s[:157] + "..."


def _fmt_fecha(valor: Any) -> str:
    """Fecha legible 'dd/mm/aaaa hh:mm'. Si no se puede interpretar, deja el original."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return texto
    return dt.strftime("%d/%m/%Y %H:%M")


_METRICAS_COLOR = {
    "Bueno": "#2FBF71", "Atención": "#F5A623", "Crítico": "#EF4B5B",
    "Datos parciales": "#F5A623", "Sin datos": "#9FB3CB",
}
_METRICAS_RGB = {
    "Bueno": (0.18, 0.75, 0.44), "Atención": (0.96, 0.65, 0.14),
    "Crítico": (0.94, 0.29, 0.36), "Datos parciales": (0.96, 0.65, 0.14),
    "Sin datos": (0.62, 0.70, 0.80),
}


def _color_nivel_medidor(tipo: str, pct) -> str:
    """Color de un medidor segun los umbrales definidos en metricas."""
    nivel = medidores_nivel(tipo, pct)
    return {"verde": "#2FBF71", "ambar": "#F5A623", "rojo": "#EF4B5B"}[nivel]


def _color_nivel_medidor_rgb(tipo: str, pct) -> tuple:
    """Color RGB de un medidor segun los umbrales definidos en metricas."""
    return {"verde": (0.18, 0.75, 0.44), "ambar": (0.96, 0.65, 0.14),
            "rojo": (0.94, 0.29, 0.36)}[medidores_nivel(tipo, pct)]


def _barra_html(pct: float, color: str, ancho: float = 100.0) -> str:
    """Barra horizontal como tabla de dos celdas (Word y navegador)."""
    pct = max(0.0, min(100.0, float(pct or 0)))
    resto = max(0.0, 100.0 - pct)
    return (
        f"<table style='width:{ancho:.0f}%;border:none;border-collapse:collapse;'>"
        f"<tr><td bgcolor='{color}' width='{pct:.1f}%' "
        f"style='height:9px;padding:0;border:none;'></td>"
        f"<td bgcolor='#e0e3e7' width='{resto:.1f}%' "
        f"style='height:9px;padding:0;border:none;'></td></tr></table>"
    )


def _barra_apilada_html(segmentos: list, ancho: float = 100.0) -> str:
    celdas = ""
    for valor, color in segmentos:
        if valor <= 0:
            continue
        celdas += (f"<td bgcolor='{color}' width='{valor:.1f}%' "
                   f"style='height:9px;padding:0;border:none;'></td>")
    if not celdas:
        celdas = ("<td bgcolor='#e0e3e7' width='100%' "
                  "style='height:9px;padding:0;border:none;'></td>")
    return (f"<table style='width:{ancho:.0f}%;border:none;border-collapse:collapse;'>"
            f"<tr>{celdas}</tr></table>")


_SINTOMAS_LABEL = {
    "revision_total": "Revisión completa del equipo",
    "general": "Revisión general",
    "impresora_offline": "Impresora fuera de línea",
    "disco_lleno": "Disco con poco espacio",
    "driver_faltante": "Driver faltante",
}


def _pal(nombre: str) -> str:
    return _PALETA.get(nombre, _PALETA["gris"])[0]


def _pal_rgb(nombre: str) -> tuple:
    return _PALETA.get(nombre, _PALETA["gris"])[1]


def _tipo_legible(e: InformeData) -> str:
    label = (e.paquete.get("label") or e.paquete.get("name") or "").strip()
    if label.lower() in ("revisión total", "revision total", "full-scan"):
        return "Revisión completa del equipo"
    return label


def _sintoma_legible(valor) -> str:
    if not valor:
        return ""
    return _SINTOMAS_LABEL.get(str(valor), str(valor).replace("_", " ").capitalize())


def _modo(e: InformeData) -> str:
    return "Administrador" if e.equipo.get("is_elevated") else "Usuario estándar"


def _prim(valor):
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, list):
        for x in valor:
            if isinstance(x, dict):
                return x
    return {}


def _lista(valor):
    return valor if isinstance(valor, list) else []


def _data_de(e: InformeData, *ids):
    for r in e.resultados:
        if r.get("collector_id") in ids:
            return r.get("data")
    return None


def _g(v, unidad="", vacio="—"):
    if v is None or v == "":
        return vacio
    if isinstance(v, float):
        v = round(v, 1)
    return f"{v}{(' ' + unidad) if unidad else ''}"


def _si_no(v):
    if v is None:
        return "—"
    return "Sí" if v else "No"


def _porciones_severidad(m: dict) -> list:
    sev = (m or {}).get("severidad") or {}
    return _porciones([
        ("Crítico", sev.get("critical", 0), _pal("critico")),
        ("Error", sev.get("error", 0), _pal("error")),
        ("Advertencia", sev.get("warning", 0), _pal("advertencia")),
    ])


def _porciones_estado(m: dict) -> list:
    est = (m or {}).get("estados") or ((m or {}).get("cobertura") or {}).get("estados") or {}
    return _porciones([
        ("OK", est.get("ok", 0), _pal("ok")),
        ("Sin datos", est.get("sin_datos", 0), _pal("sin_datos")),
        ("Error", est.get("error", 0) + est.get("timeout", 0), _pal("critico")),
        ("No evaluado", est.get("denegado", 0) + est.get("no_disponible", 0),
         _pal("no_evaluado")),
    ])


def _discos_medidor(m: dict) -> list:
    med = (m or {}).get("medidores") or {}
    return [d for d in (med.get("discos") or [])
            if isinstance(d, dict) and d.get("usado_porcentaje") is not None]


def _porciones_dona_disco(disco: dict) -> list:
    pct = float(disco.get("usado_porcentaje") or 0)
    total = disco.get("total_gb")
    usado_gb = disco.get("usado_gb")
    if usado_gb is None and total is not None:
        usado_gb = round(total * pct / 100.0, 1)
    libre_gb = disco.get("libre_gb")
    nivel = medidores_nivel("discos", pct)
    color = {"verde": _pal("verde"), "ambar": _pal("ambar"),
             "rojo": _pal("rojo")}[nivel]
    return _porciones_simples([
        ("Usado", usado_gb if usado_gb is not None else pct, color),
        ("Libre", libre_gb if libre_gb is not None else (100 - pct), _pal("resto")),
    ])


def _resumen_ejecutivo(e: InformeData) -> list[str]:
    m = e.metricas or {}
    cob = m.get("cobertura") or {}
    est = m.get("estados") or cob.get("estados") or {}
    sev = m.get("severidad") or {}
    frases = []
    tipo = _tipo_legible(e)
    frases.append(
        f"Análisis \"{tipo}\" ejecutado el {_fmt_fecha(e.generado_en)}"
        + (f" sobre el equipo {e.equipo.get('computer_name')}"
           if e.equipo.get("computer_name") else "") + ".")
    if est:
        frases.append(
            f"Se ejecutaron {cob.get('colectores_ejecutados', 0)} colectores: "
            f"{est.get('ok', 0)} OK, {est.get('sin_datos', 0)} sin datos, "
            f"{est.get('error', 0) + est.get('timeout', 0)} con error y "
            f"{est.get('denegado', 0) + est.get('no_disponible', 0)} no evaluados "
            f"(cobertura {cob.get('porcentaje', 0)}%).")
    total = sev.get("critical", 0) + sev.get("error", 0) + sev.get("warning", 0)
    if total:
        frases.append(
            f"Se detectaron {total} problemas: {sev.get('critical', 0)} críticos, "
            f"{sev.get('error', 0)} errores y {sev.get('warning', 0)} advertencias.")
    else:
        frases.append("No se detectaron problemas automáticos en este análisis.")
    if m.get("puntaje") is not None:
        frases.append(
            f"El puntaje de salud es {m.get('puntaje')}/100 ({m.get('etiqueta', '')}).")
    return frases[:5]


_MEM_TYPE = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}
_WUA_ESTADO = {1: "Detenido", 2: "Iniciando", 3: "Deteniendo", 4: "En ejecución"}


def _gb_de_bytes(valor):
    try:
        return round(float(valor) / (1024 ** 3), 1)
    except (TypeError, ValueError):
        return None


def _mascara_de_prefijo(prefijo):
    try:
        p = int(prefijo)
    except (TypeError, ValueError):
        return None
    if not 0 <= p <= 32:
        return None
    bits = "1" * p + "0" * (32 - p)
    return ".".join(str(int(bits[i:i + 8], 2)) for i in range(0, 32, 8))


def _ficha_tecnica(e: InformeData) -> list:
    ctx = _prim(_data_de(e, "system_context"))
    hw = _prim(_data_de(e, "hardware"))
    osd = _prim(_data_de(e, "os"))
    mem = _prim(_data_de(e, "memory_status"))
    eq = e.equipo
    cs = _prim(hw.get("computer_system"))
    so = osd.get("operating_system") or {}
    si = osd.get("system_info") or {}
    fabricante = cs.get("manufacturer") or si.get("manufacturer") or ctx.get("manufacturer")
    modelo = cs.get("model") or si.get("model") or ctx.get("model")

    equipo = [
        ("Equipo", _g(eq.get("computer_name") or si.get("name"))),
        ("Usuario", _g(eq.get("user"))),
        ("Modo de ejecución", _modo(e)),
        ("Sistema operativo", _g(eq.get("os") or so.get("caption") or ctx.get("os_version"))),
        ("Versión / Build", _g(f"{so.get('version', '')} ({so.get('build_number', '')})"
                               if so.get("version") else eq.get("os_version"))),
        ("Arquitectura", _g(so.get("architecture") or ctx.get("os_architecture"))),
        ("Fabricante", _g(fabricante)),
        ("Modelo", _g(modelo)),
        ("Tipo de equipo", _g(ctx.get("system_type") or ctx.get("form_factor"))),
        ("Dominio / Grupo", "Dominio" if ctx.get("is_domain_member")
         else _g(ctx.get("domain") or si.get("domain"))),
    ]

    procs = _lista(hw.get("processors"))
    proc = procs[0] if procs else {}
    nucleos = sum(int(p.get("number_of_cores") or 0) for p in procs) or None
    logicos = sum(int(p.get("number_of_logical_processors") or 0) for p in procs) or None
    ram_total = _gb_de_bytes(cs.get("total_physical_memory_bytes")) or ctx.get("total_memory_gb")
    modulos = _lista(hw.get("physical_memory"))
    ram_mod = None
    if modulos:
        partes = []
        for m in modulos[:4]:
            if not isinstance(m, dict):
                continue
            cap = _gb_de_bytes(m.get("capacity_bytes"))
            tipo = _MEM_TYPE.get(m.get("memory_type"), "")
            vel = m.get("speed_mhz")
            desc = f"{cap:g} GB" if cap else "? GB"
            if tipo:
                desc += f" {tipo}"
            if vel:
                desc += f"-{int(vel)}"
            partes.append(desc)
        ram_mod = " + ".join(partes)
        parte = (modulos[0].get("part_number") or "").strip() if isinstance(modulos[0], dict) else ""
        if parte:
            ram_mod += f" ({parte})"
    base = _prim(hw.get("baseboards"))
    bios = _prim(hw.get("bios"))
    video = _prim(hw.get("video_controllers"))
    frecuencia = proc.get("max_clock_speed_mhz") or proc.get("current_clock_speed_mhz")
    hardware = [
        ("Procesador", _g(proc.get("name") or ctx.get("processor_family"))),
        ("Núcleos / Lógicos", _g(f"{nucleos} / {logicos}" if nucleos else None)),
        ("Frecuencia", _g(frecuencia, "MHz")),
        ("Memoria RAM", _g(ram_total, "GB")),
        ("Módulos de memoria", _g(ram_mod)),
        ("Placa base", _g(base.get("product") or base.get("model")) +
         (f" ({base.get('manufacturer')})" if base.get("manufacturer") else "")),
        ("BIOS", _g(f"{bios.get('manufacturer', '')} "
                    f"{bios.get('bios_version') or bios.get('version', '')} "
                    f"{(bios.get('release_date_utc') or bios.get('release_date') or '')[:10]}".strip())),
        ("Video", _g(video.get("name"))),
    ]

    fisicos = _lista(_data_de(e, "physical_disks"))
    discos = []
    for d in fisicos[:6]:
        if not isinstance(d, dict):
            continue
        tam = d.get("size_gb")
        discos.append((_g(d.get("friendly_name") or d.get("model") or d.get("device_id")),
                       f"{_g(tam, 'GB')} · {_g(d.get('bus_type') or d.get('interface_type'))} · "
                       f"salud {_g(d.get('health_status') or d.get('status'))}"))
    logicos_l = _lista(_data_de(e, "logical_disks"))
    for d in logicos_l[:8]:
        if not isinstance(d, dict):
            continue
        total = d.get("total_gb") if d.get("total_gb") is not None else d.get("size_gb")
        libre = d.get("free_gb") if d.get("free_gb") is not None else d.get("free_space_gb")
        discos.append((f"Unidad {_g(d.get('device_id'))}",
                       f"{_g(total, 'GB')} total · {_g(libre, 'GB')} libre · "
                       f"uso {_g(d.get('used_percent') or d.get('used_percentage'))}%"))

    nets = _lista(_data_de(e, "network_adapters"))
    ips = _prim(_data_de(e, "ip_configuration"))
    red = []
    for a in nets[:5]:
        if not isinstance(a, dict):
            continue
        vel = a.get("speed") or a.get("speed_mbps") or a.get("link_speed")
        vel_txt = _g(vel, "Mbps") if isinstance(vel, (int, float)) else _g(vel)
        red.append((_g(a.get("name") or a.get("type")),
                    f"{_g(a.get('status'))} · {vel_txt} · {_g(a.get('mac_address'))}"))
    if ips:
        red.append(("Interfaz", _g(ips.get("interface_alias") or ips.get("interface_name"))))
        red.append(("Dirección IP", _g(ips.get("ipv4_address") or ips.get("ip_address"))))
        red.append(("Máscara", _g(_mascara_de_prefijo(ips.get("ipv4_prefix"))
                                  or ips.get("subnet_mask"))))
        red.append(("Puerta de enlace", _g(ips.get("ipv4_gateway")
                                           or ips.get("default_gateway"))))
        dns = ips.get("dns_servers")
        if isinstance(dns, list):
            red.append(("DNS", _g(", ".join(str(x) for x in dns[:3]))))
    if not red:
        red.append(("Red", "—"))

    av = _prim(_data_de(e, "antivirus_status"))
    fws = _lista(_data_de(e, "firewall_status"))
    fw_map = {str(f.get("name", "")).lower(): f for f in fws if isinstance(f, dict)}
    sc = _prim(_data_de(e, "security_center", "security_center_status"))

    def _fw(nombre):
        f = fw_map.get(nombre)
        if f is not None:
            return _si_no(f.get("enabled"))
        return "—"

    seguridad = [
        ("Antivirus", _g(av.get("display_name") or av.get("name"))),
        ("Antivirus activo", _si_no(av.get("enabled") if av.get("enabled") is not None
                                    else av.get("real_time_protection"))),
        ("Firewall (dominio)", _fw("domain")),
        ("Firewall (privado)", _fw("private")),
        ("Firewall (público)", _fw("public")),
        ("Centro de seguridad", _g(sc.get("display_name") or sc.get("state_description")
                                   or sc.get("status"))),
    ]

    up = _prim(_data_de(e, "update_status", "windows_update_status"))
    pend = _lista(_data_de(e, "pending_updates"))
    hist = _prim(_data_de(e, "update_history"))
    eventos = _lista(hist.get("eventos"))
    wua = up.get("servicio_wuauserv") or {}
    estado_wua = _WUA_ESTADO.get(wua.get("estado"), wua.get("estado"))
    ultimo = eventos[0].get("mensaje") if eventos and isinstance(eventos[0], dict) else None
    modulo_no = any(isinstance(x, dict) and x.get("status") == "module_not_available"
                    for x in pend)
    actualizaciones = [
        ("Servicio Windows Update", _g(estado_wua or up.get("status"))),
        ("Eventos registrados", _g(hist.get("total_eventos") if eventos else None)),
        ("Última actividad", _g(ultimo)),
        ("Módulo PSWindowsUpdate", "No instalado" if modulo_no else "—"),
    ]

    libre_mb = mem.get("free_physical_memory_kb")
    rendimiento = [
        ("Uso de memoria", _g(mem.get("physical_memory_usage_percent"), "%")),
        ("Memoria libre", _g(round(libre_mb / 1024) if libre_mb else None, "MB")),
        ("Tiempo encendido", _g(ctx.get("uptime_hours"), "h")),
    ]

    return [
        ("Datos del equipo", equipo),
        ("Hardware", hardware),
        ("Discos", discos or [("Discos", "—")]),
        ("Red", red),
        ("Seguridad", seguridad),
        ("Actualizaciones", actualizaciones),
        ("Memoria y rendimiento", rendimiento),
    ]


def _detalle_corto(data, maximo: int = 5, tope: int = 160) -> list[str]:
    """Lineas compactas 'campo: valor' de un dato crudo (tope de registros)."""
    if not isinstance(data, (dict, list)):
        return []
    registros = data if isinstance(data, list) else [data]
    lineas = []
    for reg in registros[:maximo]:
        if not isinstance(reg, dict):
            texto = _fmt_valor(reg)
        else:
            texto = ", ".join(f"{k}: {_fmt_valor(v)}" for k, v in reg.items()
                              if not isinstance(v, (dict, list)))
        if not texto:
            continue
        lineas.append(texto if len(texto) <= tope else texto[:tope - 3] + "...")
    return lineas


def _anexo_tecnico(e: InformeData, paquetes: dict) -> list[dict]:
    filas = []
    for c in e.colectores:
        resumen = " ".join(c.resumen)[:120]
        if len(" ".join(c.resumen)) > 120:
            resumen += "..."
        data = _data_de(e, c.collector_id)
        total_reg = len(data) if isinstance(data, list) else (1 if data else 0)
        detalle = _detalle_corto(data)
        filas.append({
            "colector": c.collector_id,
            "paquete": paquetes.get(c.collector_id, ""),
            "estado": c.status,
            "duracion_ms": c.duration_ms,
            "resumen": resumen,
            "detalle": detalle,
            "registros_restantes": max(0, total_reg - len(detalle)),
        })
    return filas


def _mapa_paquete_colector(e: InformeData) -> dict:
    mapa = {}
    for cat in (e.metricas or {}).get("categorias") or []:
        pid = cat.get("paquete_id") or ""
        for cid in cat.get("colectores") or []:
            mapa[cid] = cat.get("paquete", "")
        # Si la categoria no trae la lista, se resuelve por el id del paquete.
    return mapa


def _modelo_documento(e: InformeData) -> dict:
    """Modelo unico de secciones que alimenta HTML, PDF y Word."""
    m = e.metricas or {}
    sev = m.get("severidad") or {}
    cob = m.get("cobertura") or {}
    mapa = _mapa_paquete_colector(e)
    problemas_tabla = [
        {
            "indice": p.indice,
            "severidad": p.severidad,
            "titulo": p.titulo,
            "colector": p.colector,
            "estado": p.estado,
        }
        for p in e.problemas
    ]
    return {
        "tipo": _tipo_legible(e),
        "sintoma": _sintoma_legible(e.paquete.get("symptom")),
        "fecha": _fmt_fecha(e.generado_en),
        "codigo": codigo_verificacion(e),
        "equipo": e.equipo,
        "modo": _modo(e),
        "tecnico": e.tecnico,
        "cliente": e.cliente,
        "metricas": m,
        "cobertura": cob,
        "severidad": sev,
        "indicadores": {
            "puntaje": m.get("puntaje"),
            "etiqueta": m.get("etiqueta", ""),
            "problemas": sev.get("critical", 0) + sev.get("error", 0) + sev.get("warning", 0),
            "criticos": sev.get("critical", 0),
            "errores": sev.get("error", 0),
            "advertencias": sev.get("warning", 0),
            "ok": ((m.get("estados") or {}).get("ok", 0)),
            "sin_datos": ((m.get("estados") or {}).get("sin_datos", 0)),
            "error": ((m.get("estados") or {}).get("error", 0)
                      + (m.get("estados") or {}).get("timeout", 0)),
            "cobertura": cob.get("porcentaje", 0),
        },
        "resumen_ejecutivo": _resumen_ejecutivo(e),
        "torta_severidad": _porciones_severidad(m),
        "torta_estado": _porciones_estado(m),
        "discos": _discos_medidor(m),
        "memoria": (m.get("medidores") or {}).get("memoria"),
        "leyenda_medidores": m.get("leyenda_medidores", ""),
        "categorias": m.get("categorias") or [],
        "problemas": e.problemas,
        "problemas_tabla": problemas_tabla,
        "mejoras": e.mejoras,
        "diferencias": e.diferencias,
        "recomendaciones": e.recomendaciones,
        "ficha_tecnica": _ficha_tecnica(e),
        "anexo": _anexo_tecnico(e, mapa),
        "observaciones": e.observaciones,
        "advertencias": e.advertencias,
        "comparacion": {
            "base": e.metricas_base,
            "actual": e.metricas_actual,
        } if e.metricas_base and e.metricas_actual else None,
        "alcance": linea_alcance(e),
    }


def _grafico_html_porciones(porciones_, con_svg: bool, tipo: str = "torta",
                            titulo: str = "", centro: str = "") -> str:
    if not porciones_:
        return "<p class='muted'>Sin datos para graficar.</p>"
    if con_svg:
        if tipo == "dona":
            return _svg_dona(porciones_, titulo=titulo, centro=centro)
        return _svg_torta(porciones_, titulo=titulo)
    filas = []
    total = sum(p["valor"] for p in porciones_) or 1
    for p in porciones_:
        pct = p["valor"] / total * 100
        filas.append(
            f"<tr><td>{_esc(p['etiqueta'])}</td>"
            f"<td>{p['valor']:g} ({round(pct, 1)}%)</td>"
            f"<td>{_barra_html(pct, p['color'])}</td></tr>")
    return ("<table><tr><td class='th' style='width:40%'>" + _esc(titulo) +
            "</td><td class='th' style='width:20%'>Cantidad</td>"
            "<td class='th' style='width:40%'>Proporción</td></tr>"
            + "".join(filas) + "</table>")


def codigo_verificacion(e: InformeData) -> str:
    """Primeros 16 caracteres del SHA-256 de contenido + acciones + fecha + equipo."""
    partes = [
        f"fecha:{e.generado_en}",
        f"equipo:{e.equipo.get('computer_name', '')}",
        json.dumps(e.paquete, ensure_ascii=False, sort_keys=True, default=str),
        json.dumps(e.resumen, ensure_ascii=False, sort_keys=True, default=str),
    ]
    for c in e.colectores:
        partes.append(f"C|{c.collector_id}|{c.status}|{c.duration_ms}|"
                      + "\u001f".join(c.resumen) + "|" + "\u001f".join(c.errores))
    for p in e.problemas:
        partes.append(f"P|{p.indice}|{p.severidad}|{p.colector}|{p.titulo}|{p.estado}|"
                      f"{p.solucion}|{p.solucion_elegida}|"
                      + json.dumps(p.detalle, ensure_ascii=False, sort_keys=True, default=str))
    for m in e.mejoras:
        partes.append(f"M|{m.id}|{m.titulo}|{int(m.aplicada)}|{m.comentario}")
    partes.append("R|" + "\u001f".join(e.recomendaciones))
    partes.append(f"T|{e.tecnico}|{e.cliente}|{e.observaciones}")
    for d in e.diferencias:
        partes.append("D|" + json.dumps(d, ensure_ascii=False, sort_keys=True, default=str))
    partes.append("A|" + "\u001f".join(e.advertencias))
    material = "\n".join(partes)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


_LOGO_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64' width='52' "
    "height='52' role='img'><title>DiagUSB</title>"
    "<rect x='4' y='4' width='56' height='56' rx='12' fill='#1769D2'/>"
    "<rect x='16' y='14' width='32' height='36' rx='4' fill='#ffffff'/>"
    "<rect x='21' y='20' width='22' height='4' rx='2' fill='#0F1F35'/>"
    "<rect x='21' y='28' width='22' height='4' rx='2' fill='#2FBF71'/>"
    "<rect x='21' y='36' width='14' height='4' rx='2' fill='#F5A623'/>"
    "<circle cx='48' cy='48' r='9' fill='#0F1F35'/><path d='M44 48 l3 3 l6 -7' "
    "stroke='#2FBF71' stroke-width='2.5' fill='none' stroke-linecap='round' "
    "stroke-linejoin='round'/></svg>"
)


def _html_portada(doc: dict, con_svg: bool = True) -> str:
    equipo = doc.get("equipo") or {}
    logo = (_LOGO_SVG if con_svg else
            "<div class='portada-logo-caja'><span>D</span></div>")
    return (
        "<section class='portada'>"
        "<div class='portada-banda'>"
        f"<div class='portada-logo'>{logo}</div>"
        "<div><div class='portada-marca'>DiagUSB</div>"
        "<div class='portada-sub'>Informe de diagnóstico técnico</div></div>"
        "</div>"
        f"<h1 class='portada-titulo'>{_esc(doc['tipo'])}</h1>"
        f"<p class='portada-sintoma'>Motivo: {_esc(doc['sintoma'] or '—')}</p>"
        "<table class='kv portada-kv'>"
        f"<tr><td>Equipo</td><td>{_esc(equipo.get('computer_name') or '—')}</td></tr>"
        f"<tr><td>Sistema operativo</td><td>{_esc(equipo.get('os') or '—')}</td></tr>"
        f"<tr><td>Usuario</td><td>{_esc(equipo.get('user') or '—')}</td></tr>"
        f"<tr><td>Modo</td><td>{_esc(doc['modo'])}</td></tr>"
        f"<tr><td>Fecha</td><td>{_esc(doc['fecha'] or '—')}</td></tr>"
        f"<tr><td>Técnico</td><td>{_esc(doc['tecnico'] or '________________________')}</td></tr>"
        f"<tr><td>Cliente / Sector</td><td>{_esc(doc['cliente'] or '________________________')}</td></tr>"
        f"<tr><td>Código de verificación</td><td class='mono'>{_esc(doc['codigo'])}</td></tr>"
        "</table>"
        "<p class='muted'>Puntaje orientativo. No reemplaza al diagnóstico profesional "
        "ni a las pruebas de cada fabricante.</p>"
        "</section>")


def _html_indicadores(doc: dict) -> str:
    ind = doc["indicadores"]
    color = _METRICAS_COLOR.get(ind["etiqueta"], "#9FB3CB")
    puntaje = "—" if ind["puntaje"] is None else f"{ind['puntaje']}/100"
    tarjetas = [
        ("Puntaje de salud", puntaje, "#0F1F35",
         f"{ind['etiqueta']}"),
        ("Problemas", str(ind["problemas"]), _pal("critico"),
         f"{ind['criticos']} crítico(s), {ind['errores']} error(es), "
         f"{ind['advertencias']} advertencia(s)"),
        ("Colectores", f"{ind['ok']} OK", _pal("ok"),
         f"{ind['sin_datos']} sin datos, {ind['error']} con error"),
        ("Cobertura", f"{ind['cobertura']}%", _pal("acento"),
         "colectores evaluados sobre ejecutados"),
    ]
    html = ["<div class='tarjetas'>"]
    for titulo, valor, col, detalle in tarjetas:
        html.append(
            f"<div class='tarjeta' style='border-top-color:{col}'>"
            f"<div class='tarjeta-titulo'>{_esc(titulo)}</div>"
            f"<div class='tarjeta-valor' style='color:{col}'>{_esc(valor)}</div>"
            f"<div class='tarjeta-detalle'>{_esc(detalle)}</div></div>")
    html.append("</div>")
    return "".join(html)


def _html_resumen_linea_alcance(doc: dict) -> str:
    return f"<p class='muted'><b>{_esc(doc['alcance'])}</b></p>"


def _hay_datos(porciones_) -> bool:
    return any(p.get("valor") for p in porciones_)


def _leyenda_html(porciones_, centro: str = "") -> str:
    filas = "".join(
        f"<tr><td width='14' bgcolor='{p['color']}'>&nbsp;</td>"
        f"<td>{_esc(p['etiqueta'])}: {p['valor']:g} ({p['porcentaje']:g}%)</td></tr>"
        for p in porciones_)
    extra = f"<tr><td colspan='2'><b>{_esc(centro)}</b></td></tr>" if centro else ""
    return (f"<table style='width:auto'>{filas}{extra}</table>"
            if filas else "<p class='muted'>Sin datos.</p>")


def _html_panel_grafico(doc: dict, con_svg: bool, imagenes: dict | None = None) -> str:
    def _grafico(porciones_, tipo: str, titulo: str, nombre: str,
                 centro: str = "", ancho: int = 200) -> str:
        if imagenes is not None and nombre in imagenes:
            if not _hay_datos(porciones_):
                return "<p class='muted'>Sin datos para graficar.</p>"
            return (f"<v:shape id='{nombre}' style='width:{ancho}pt;height:{ancho}pt' "
                    f"o:title='{_esc(titulo)}'>"
                    f"<v:imagedata src='{nombre}.png' o:title='{_esc(titulo)}'/>"
                    "</v:shape>" + _leyenda_html(porciones_, centro))
        return _grafico_html_porciones(porciones_, con_svg, tipo=tipo,
                                       titulo=titulo, centro=centro)

    out = ["<div class='panel-grafico'>"]
    out.append("<div class='grafico-celda'><h3>Problemas por severidad</h3>")
    out.append(_grafico(doc["torta_severidad"], "torta", "Problemas por severidad",
                        "diagusb_severidad"))
    out.append("</div>")
    out.append("<div class='grafico-celda'><h3>Estado de los colectores</h3>")
    out.append(_grafico(doc["torta_estado"], "torta", "Estado de los colectores",
                        "diagusb_estado"))
    out.append("</div>")

    discos = doc["discos"]
    out.append("<div class='grafico-celda'><h3>Ocupación de discos</h3>")
    if discos:
        for i, d in enumerate(discos[:6]):
            porc = _porciones_dona_disco(d)
            etiqueta = f"Disco {_esc(d.get('unidad') or '')}"
            centro = f"{d.get('usado_porcentaje')}%"
            out.append(f"<p class='mini-titulo'>{etiqueta} — "
                       f"{_g(d.get('total_gb'), 'GB')} total, "
                       f"{_g(d.get('libre_gb'), 'GB')} libre</p>")
            out.append(_grafico(porc, "dona", etiqueta, f"diagusb_disco{i}", centro))
    else:
        out.append("<p class='muted'>Sin datos de discos.</p>")
    out.append("</div>")

    out.append("<div class='grafico-celda'><h3>Memoria y umbrales</h3>")
    mem = doc.get("memoria")
    if mem and mem.get("usado_porcentaje") is not None:
        pct = mem["usado_porcentaje"]
        out.append(f"<p>Memoria en uso: <b>{pct}%</b></p>")
        if imagenes is not None and "diagusb_memoria" in imagenes:
            out.append("<v:shape id='diagusb_memoria' style='width:300pt;height:26pt' "
                       "o:title='Memoria en uso'><v:imagedata src='diagusb_memoria.png' "
                       "o:title='Memoria en uso'/></v:shape>")
        else:
            out.append(f"<p>{_barra_html(pct, _color_nivel_medidor('memoria', pct))}</p>")
    else:
        out.append("<p class='muted'>Sin datos de memoria.</p>")
    out.append(f"<p class='muted'>{_esc(doc.get('leyenda_medidores', ''))}</p>")
    out.append("</div>")

    comp = doc.get("comparacion")
    if comp:
        out.append("<div class='grafico-celda'><h3>Comparación antes / después</h3>")
        out.append("<table><tr><td class='th'>Momento</td><td class='th'>Puntaje</td>"
                   "<td class='th'>Barra</td></tr>")
        for etiqueta, mm in (("Antes", comp["base"]), ("Después", comp["actual"])):
            val = mm.get("puntaje")
            col = _METRICAS_COLOR.get(mm.get("etiqueta"), "#9FB3CB")
            out.append(f"<tr><td>{etiqueta}</td><td>{'-' if val is None else val}</td>"
                       f"<td>{_barra_html(val or 0, col)}</td></tr>")
        out.append("</table></div>")

    out.append("</div>")
    return "".join(out)


def _html_categorias(doc: dict) -> str:
    cats = doc["categorias"]
    if not cats:
        return "<p class='muted'>Sin datos por paquete.</p>"
    out = ["<table><tr><td class='th' style='width:22%'>Paquete</td>"
           "<td class='th' style='width:7%'>OK</td>"
           "<td class='th' style='width:10%'>Sin datos</td>"
           "<td class='th' style='width:7%'>Error</td>"
           "<td class='th' style='width:16%'>Hallazgos</td>"
           "<td class='th' style='width:38%'>Distribución</td></tr>"]
    for c in cats:
        ok = c.get("ok", 0)
        sin = c.get("sin_datos", 0)
        err = c.get("error", 0) + c.get("timeout", 0)
        ne = c.get("no_evaluado", 0)
        hall = c.get("hallazgos") or {}
        total = (ok + sin + err + ne) or 1
        segs = [(ok / total * 100, _pal("ok")), (sin / total * 100, _pal("sin_datos")),
                (err / total * 100, _pal("critico")), (ne / total * 100, _pal("no_evaluado"))]
        out.append(f"<tr><td>{_esc(c.get('paquete', ''))}</td><td>{ok}</td>"
                   f"<td>{sin}</td><td>{err}</td>"
                   f"<td>C {hall.get('critical', 0)} / E {hall.get('error', 0)} / "
                   f"A {hall.get('warning', 0)}</td>"
                   f"<td>{_barra_apilada_html(segs)}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _html_problemas(doc: dict, con_svg: bool) -> str:
    out = []
    for p in doc["problemas"]:
        color = _SEVERIDAD_COLOR.get(p.severidad, "#888")
        out.append(f"<div class='problema' style='border-left-color: {color};'>")
        out.append(f"<h3><span class='badge' style='background: {color};'>"
                   f"{_esc(SEVERIDAD_LABEL.get(p.severidad, p.severidad))}</span> "
                   f"{_esc(p.titulo)}</h3>")
        out.append(f"<p class='muted'>Colector: {_esc(p.colector)} · "
                   f"Estado de la acción: {_esc(p.estado)}</p>")
        if p.detalle:
            detalle = ", ".join(f"{k}: {_fmt_valor(v)}" for k, v in p.detalle.items()
                                if k not in ("grupo_mensajes", "grupo_total"))
            if detalle:
                out.append(f"<p><b>Qué ocurre:</b> {_esc(detalle)}</p>")
        if p.estado_esperado:
            out.append(f"<p><b>Cómo debe estar:</b> {_esc(p.estado_esperado)}</p>")
        if p.por_que:
            out.append(f"<p class='muted'><b>Por qué importa:</b> {_esc(p.por_que)}</p>")
        if p.soluciones:
            out.append("<p><b>Pasos sugeridos:</b></p><ul>")
            for s in p.soluciones:
                out.append(f"<li>{_esc(s)}</li>")
            out.append("</ul>")
        if p.verificacion:
            out.append(f"<p><b>Verificación:</b> {_esc(p.verificacion)}</p>")
        if p.grupo:
            out.append(f"<p><b>Otros casos del mismo problema ({len(p.grupo)} más):</b></p><ul>")
            for m in p.grupo:
                out.append(f"<li>{_esc(m)}</li>")
            out.append("</ul>")
        if p.solucion_elegida:
            out.append(f"<p><b>Solución aplicada:</b> {_esc(p.solucion_elegida)}</p>")
        if p.solucion:
            out.append(f"<p><b>Descripción de la acción:</b> {_esc(p.solucion)}</p>")
        out.append("</div>")
    if not doc["problemas"]:
        out.append("<p>No se detectaron problemas automáticos en este análisis.</p>")
    return "".join(out)


def _html_plan_accion(doc: dict) -> str:
    out = []
    if doc.get("recomendaciones"):
        out.append("<h3>Recomendaciones generales</h3><ul>")
        for rec in doc["recomendaciones"]:
            out.append(f"<li>{_esc(rec)}</li>")
        out.append("</ul>")
    out.append("<h3>Acciones pendientes</h3>")
    out.append("<table><tr><td class='th' style='width:6%'>Hecho</td>"
               "<td class='th' style='width:8%'>Prior.</td>"
               "<td class='th' style='width:46%'>Acción</td>"
               "<td class='th' style='width:40%'>Referencia</td></tr>")
    filas = []
    for p in doc["problemas"]:
        sev = SEVERIDAD_LABEL.get(p.severidad, p.severidad)
        acciones = p.soluciones or [p.recomendacion or "Revisar el problema detectado."]
        for a in acciones[:2]:
            filas.append((sev, a, f"Problema {p.indice} · {p.colector}"))
    if doc["mejoras"]:
        for m in doc["mejoras"]:
            if not m.aplicada:
                filas.append(("Mejora", m.titulo, m.detalle[:80]))
    if not filas:
        filas.append(("—", "Sin acciones pendientes.", ""))
    for prio, accion, ref in filas:
        out.append(f"<tr><td>☐</td><td>{_esc(prio)}</td>"
                   f"<td>{_esc(accion)}</td><td>{_esc(ref)}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _html_ficha_tecnica(doc: dict) -> str:
    out = []
    for titulo, filas in doc["ficha_tecnica"]:
        out.append(f"<h3>{_esc(titulo)}</h3><table class='kv'>")
        for k, v in filas:
            out.append(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>")
        out.append("</table>")
    return "".join(out)


def _html_anexo(doc: dict) -> str:
    filas = doc["anexo"]
    if not filas:
        return "<p class='muted'>Sin colectores registrados.</p>"
    out = ["<table><tr><td class='th' style='width:20%'>Colector</td>"
           "<td class='th' style='width:16%'>Paquete</td>"
           "<td class='th' style='width:10%'>Estado</td>"
           "<td class='th' style='width:10%'>Duración</td>"
           "<td class='th' style='width:44%'>Resumen</td></tr>"]
    for f in filas:
        out.append(f"<tr><td class='mono'>{_esc(f['colector'])}</td>"
                   f"<td>{_esc(f['paquete'])}</td><td>{_esc(f['estado'])}</td>"
                   f"<td>{f['duracion_ms']} ms</td><td>{_esc(f['resumen'])}</td></tr>")
        for linea in f["detalle"]:
            out.append(f"<tr><td></td><td></td><td></td><td></td>"
                       f"<td class='mono'>{_esc(linea)}</td></tr>")
        if f["registros_restantes"]:
            out.append(f"<tr><td></td><td></td><td></td><td></td>"
                       f"<td class='muted'>{f['registros_restantes']} registro(s) más "
                       f"en el JSON del análisis.</td></tr>")
    out.append("</table>")
    return "".join(out)


_CSS_REPORTE = """
:root { --tinta:#0F1F35; --acento:#1769D2; }
body { font-family:'Segoe UI',Arial,sans-serif; color:#222; margin:24px; font-size:12px; }
h1 { font-size:22px; color:var(--tinta); margin:0 0 2px 0; }
h2 { font-size:15px; color:var(--acento); border-bottom:1px solid #ddd;
     padding-bottom:3px; margin:22px 0 8px 0; }
h3 { font-size:12.5px; color:#333; margin:12px 0 4px 0; }
table { border-collapse:collapse; width:100%; table-layout:fixed;
        overflow-wrap:anywhere; margin:8px 0; }
th, td { border:1px solid #ccc; padding:5px 8px; text-align:left;
         vertical-align:top; }
th, td.th { background:#f1f3f4; font-weight:700; }
.kv td:first-child { background:#f8f9fa; font-weight:600; width:34%; }
.badge { display:inline-block; padding:2px 8px; border-radius:10px; color:#fff;
         font-size:10px; font-weight:700; }
.muted { color:#666; }
.mono { font-family:Consolas,monospace; font-size:11px; }
.problema { border:1px solid #ddd; border-left:5px solid #888; padding:10px;
            margin:10px 0; page-break-inside:avoid; }
.panel-grafico { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.grafico-celda { border:1px solid #e3e7ec; border-radius:8px; padding:10px;
                 page-break-inside:avoid; }
.grafico-celda h3 { margin-top:0; }
.tarjetas { display:grid; grid-template-columns:repeat(4,1fr); gap:10px;
            margin:8px 0; }
.tarjeta { border:1px solid #e3e7ec; border-top:4px solid var(--acento);
           border-radius:8px; padding:8px; page-break-inside:avoid; }
.tarjeta-titulo { font-size:10px; color:#666; text-transform:uppercase;
                  letter-spacing:.4px; }
.tarjeta-valor { font-size:20px; font-weight:700; margin:2px 0; }
.tarjeta-detalle { font-size:10px; color:#555; }
.mini-titulo { font-size:11px; color:#444; margin:6px 0 2px 0; }
.portada { page-break-after:always; }
.portada-banda { background:var(--tinta); color:#fff; border-radius:10px;
                 padding:14px 16px; display:flex; align-items:center; gap:14px; }
.portada-logo { line-height:0; }
.portada-logo-caja { width:52px; height:52px; border-radius:12px; background:#1769D2;
                     color:#fff; font-size:30px; font-weight:700; text-align:center;
                     line-height:52px; }
.portada-marca { font-size:24px; font-weight:700; }
.portada-sub { font-size:12px; color:#b8c6db; }
.portada-titulo { margin:20px 0 0 0; }
.portada-sintoma { color:#555; margin-top:4px; }
.firma { width:100%; margin-top:40px; border-collapse:collapse; }
.firma td { width:50%; border:none; border-top:1px solid #333; padding-top:4px;
            text-align:center; }
@media print { body { margin:0; }
  .portada { page-break-after:always; }
  .grafico-celda, .problema, .tarjeta, .ficha-bloque { page-break-inside:avoid; }
  h2 { page-break-after:avoid; }
}
"""


def informe_a_html(informe: InformeData, con_anexo: bool = False,
                   resultados_completos: list | None = None,
                   con_svg: bool = True, imagenes: dict | None = None) -> str:
    e = informe
    doc = _modelo_documento(e)
    n_seccion = 0

    def _sec(titulo: str) -> str:
        nonlocal n_seccion
        n_seccion += 1
        return f"<h2>{n_seccion}. {titulo}</h2>"

    out = ["<html><head><meta charset='utf-8'><title>Informe DiagUSB</title>",
           f"<style>{_CSS_REPORTE}</style></head><body>"]
    out.append(_html_portada(doc, con_svg))

    for adv in doc["advertencias"]:
        out.append(f"<p class='advertencia'><b>{_esc(adv)}</b></p>")

    out.append(_sec("Datos del servicio"))
    out.append(_html_resumen_linea_alcance(doc))
    out.append("<table class='kv'>")
    equipo = doc["equipo"]
    datos = [
        ("Equipo", _g(equipo.get("computer_name"))),
        ("Usuario", _g(equipo.get("user"))),
        ("Técnico", _g(doc["tecnico"])),
        ("Cliente / Sector", _g(doc["cliente"])),
        ("Modo de ejecución", doc["modo"]),
        ("Sistema operativo", _g(equipo.get("os"))),
        ("Versión / Build", _g(f"{equipo.get('os_version', '')} ({equipo.get('build', '')})"
                               if equipo.get("os_version") else None)),
    ]
    for k, v in datos:
        out.append(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>")
    out.append("</table>")

    out.append(_sec("Indicadores"))
    out.append(_html_indicadores(doc))

    out.append(_sec("Resumen ejecutivo"))
    out.append("<ul>")
    for frase in doc["resumen_ejecutivo"]:
        out.append(f"<li>{_esc(frase)}</li>")
    out.append("</ul>")

    out.append(_sec("Panel gráfico"))
    out.append(_html_panel_grafico(doc, con_svg, imagenes))

    out.append(_sec("Problemas detectados"))
    if doc["problemas_tabla"]:
        out.append("<table><tr><td class='th' style='width:6%'>#</td>"
                   "<td class='th' style='width:14%'>Severidad</td>"
                   "<td class='th' style='width:44%'>Título</td>"
                   "<td class='th' style='width:20%'>Colector</td>"
                   "<td class='th' style='width:16%'>Estado</td></tr>")
        for f in doc["problemas_tabla"]:
            out.append(f"<tr><td>{f['indice']}</td>"
                       f"<td>{_esc(SEVERIDAD_LABEL.get(f['severidad'], f['severidad']))}</td>"
                       f"<td>{_esc(f['titulo'])}</td><td class='mono'>{_esc(f['colector'])}</td>"
                       f"<td>{_esc(f['estado'])}</td></tr>")
        out.append("</table>")
    out.append(_html_problemas(doc, con_svg))

    out.append(_sec("Plan de acción"))
    out.append(_html_plan_accion(doc))

    out.append(_sec("Ficha técnica"))
    out.append(_html_ficha_tecnica(doc))
    if doc["categorias"]:
        out.append("<h3>Estado por paquete</h3>")
        out.append(_html_categorias(doc))

    out.append(_sec("Anexo técnico"))
    out.append(_html_anexo(doc))
    if con_anexo and resultados_completos:
        out.append("<h3>Anexo A: Datos crudos de los colectores (JSON)</h3>")
        out.append("<pre class='mono'>")
        out.append(_esc(json.dumps(resultados_completos, ensure_ascii=False,
                                   indent=2)[:200000]))
        out.append("</pre>")

    out.append(_sec("Cierre"))
    if doc["observaciones"]:
        out.append(f"<p><b>Observaciones:</b> {_esc(doc['observaciones'])}</p>")
    else:
        out.append("<p><b>Observaciones:</b> __________________________________________</p>")
    out.append("<table class='firma'><tr><td>Firma del técnico</td>"
               "<td>Conformidad del cliente</td></tr></table>")
    out.append(f"<p class='muted mono'>Código de verificación: {_esc(doc['codigo'])}</p>")
    out.append("</body></html>")
    return "".join(out)


def _imagenes_doc(doc: dict) -> dict:
    """PNG (bytes) de los graficos del panel para embeber en el .doc."""
    imagenes = {}
    for nombre, porciones_ in (("diagusb_severidad", doc["torta_severidad"]),
                               ("diagusb_estado", doc["torta_estado"])):
        if _hay_datos(porciones_):
            imagenes[nombre] = _png_torta(porciones_, 220)
    for i, d in enumerate(doc["discos"][:6]):
        porciones_ = _porciones_dona_disco(d)
        if _hay_datos(porciones_):
            imagenes[f"diagusb_disco{i}"] = _png_dona(porciones_, 200)
    mem = doc.get("memoria")
    if mem and mem.get("usado_porcentaje") is not None:
        pct = mem["usado_porcentaje"]
        imagenes["diagusb_memoria"] = _png_barra(
            pct, _color_nivel_medidor("memoria", pct))
    return imagenes


def _mhtml(html_doc: str, imagenes: dict) -> bytes:
    """Empaqueta el HTML y sus PNG como multipart/related (MHTML de Word).

    La parte HTML se envía en base64: Word no acepta `8bit` en el cuerpo
    de texto/html de un multipart/related y, con ese encoding, ignora los
    recursos embebidos (imágenes) aunque el documento sí se abra.
    """
    limite = "----=_NextPart_DiagUSB"
    html_b64 = base64.b64encode(html_doc.encode("utf-8"))
    html_lineas = b"\r\n".join(html_b64[i:i + 76] for i in range(0, len(html_b64), 76))
    partes = [
        ("MIME-Version: 1.0\r\n"
         "Content-Type: multipart/related; boundary=\"" + limite +
         "\"; type=\"text/html\"\r\n\r\n").encode("ascii"),
        ("--" + limite + "\r\n"
         "Content-Location: file:///C:/diagusb/informe.htm\r\n"
         "Content-Type: text/html; charset=\"utf-8\"\r\n"
         "Content-Transfer-Encoding: base64\r\n\r\n").encode("ascii"),
        html_lineas,
        b"\r\n",
    ]
    for nombre, png in imagenes.items():
        b64 = base64.b64encode(png)
        partes.append(("--" + limite + "\r\n"
                       f"Content-Location: file:///C:/diagusb/{nombre}.png\r\n"
                       "Content-Type: image/png\r\n"
                       "Content-Transfer-Encoding: base64\r\n\r\n").encode("ascii"))
        partes.append(b"\r\n".join(b64[i:i + 76] for i in range(0, len(b64), 76)))
        partes.append(b"\r\n")
    partes.append(("--" + limite + "--\r\n").encode("ascii"))
    return b"".join(partes)


def html_de_doc(datos: bytes) -> bytes:
    """Extrae el cuerpo ``text/html`` de un .doc MHTML (base64 o 8bit).

    Devuelve ``datos`` tal cual si no es MHTML (mantenimiento de tests
    que consumen directamente el formato anterior).
    """
    if not datos.startswith(b"MIME-Version"):
        return datos
    i = datos.find(b"Content-Type: text/html")
    if i == -1:
        return datos
    j = datos.find(b"\r\n\r\n", i)
    if j == -1:
        return datos
    encabezado = datos[i:j]
    k = j + 4
    l = datos.find(b"\r\n--", k)
    cuerpo = datos[k:l] if l != -1 else datos[k:]
    if b"base64" in encabezado.lower():
        return base64.b64decode(b"".join(cuerpo.split()))
    return cuerpo


def informe_a_doc(informe: InformeData, resultados_completos: list | None = None,
                  con_anexo: bool = False) -> bytes:
    """Genera un .doc MHTML (HTML de Word con los graficos PNG embebidos).

    El volcado JSON crudo de los colectores solo se incluye si ``con_anexo`` es
    True (cuando el técnico lo pide); por defecto no aparece.
    """
    modelo = _modelo_documento(informe)
    imagenes = _imagenes_doc(modelo)
    body = informe_a_html(informe, con_anexo=con_anexo,
                          resultados_completos=resultados_completos,
                          con_svg=False, imagenes=imagenes)
    doc = (
        "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
        "xmlns:w='urn:schemas-microsoft-com:office:word' "
        "xmlns:v='urn:schemas-microsoft-com:vml'>"
        "<head><meta charset='utf-8'><title>Informe DiagUSB</title>"
        "<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>"
        "<w:Zoom>100</w:Zoom></w:WordDocument></xml><![endif]-->"
        "<style>@page WordSection1 { size: 21cm 29.7cm; margin: 2cm; }"
        "div.WordSection1 { page: WordSection1; }"
        + _CSS_WORD + "</style></head>"
        "<body><div class='WordSection1'>" + body[body.find("<body>") + 6:body.rfind("</body>")] +
        "</div></body></html>"
    )
    return _mhtml(doc, imagenes)


# ---------------------------------------------------------------------------
# PDF (motor minimo propio, sin dependencias)
# ---------------------------------------------------------------------------

_PAGE_W = 595.28   # A4 en puntos
_PAGE_H = 841.89
_MARGIN = 48

_FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique"}
_FONT_WIDTH = {"F1": 0.50, "F2": 0.53, "F3": 0.50}


def _pdf_escape(text: str) -> str:
    raw = text.encode("cp1252", errors="replace")
    s = raw.decode("cp1252")
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _pdf_width(text: str, size: float, font: str) -> float:
    return len(text) * size * _FONT_WIDTH.get(font, 0.5)


class _PdfDoc:
    """Generador PDF minimo: texto, lineas, rectangulos y salto de pagina."""

    def __init__(self):
        self.pages: list[list[str]] = []
        self._new_page()

    def _new_page(self):
        self.ops: list[str] = []
        self.pages.append(self.ops)
        self._y = _PAGE_H - _MARGIN

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, v):
        self._y = v

    def ensure_space(self, needed: float):
        if self._y - needed < _MARGIN + 24:
            self._new_page()

    def text(self, x: float, text: str, size: float = 10, font: str = "F1",
             color: tuple = (0, 0, 0)):
        r, g, b = color
        self.ops.append(
            f"BT /{font} {size:g} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"1 0 0 1 {x:.2f} {self._y:.2f} Tm ({_pdf_escape(text)}) Tj ET"
        )

    def text_flow(self, text: str, size: float = 10, font: str = "F1",
                  color: tuple = (0, 0, 0), indent: float = 0,
                  max_width: float | None = None, leading: float | None = None):
        leading = leading or size * 1.35
        max_width = max_width or (_PAGE_W - 2 * _MARGIN - indent)
        words = text.split(" ")
        line = ""
        for w in words:
            candidate = (line + " " + w).strip()
            if _pdf_width(candidate, size, font) > max_width and line:
                self.ensure_space(leading)
                self.text(_MARGIN + indent, line, size, font, color)
                self._y -= leading
                line = w
            else:
                line = candidate
        if line:
            self.ensure_space(leading)
            self.text(_MARGIN + indent, line, size, font, color)
            self._y -= leading

    def hrule(self, color=(0.75, 0.75, 0.75)):
        self.ensure_space(6)
        self.ops.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG 0.7 w "
            f"{_MARGIN:.2f} {self._y:.2f} m {_PAGE_W - _MARGIN:.2f} {self._y:.2f} l S"
        )
        self._y -= 8

    def spacer(self, h: float = 8):
        self._y -= h

    def rect(self, x: float, y: float, w: float, h: float,
             fill: tuple | None = None, stroke: tuple | None = None,
             width: float = 0.7):
        """Rectangulo vectorial (relleno y/o borde) para las barras de metricas."""
        partes = []
        if fill:
            partes.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            partes.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} "
                          f"RG {width:g} w")
        partes.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill:
            partes.append("f")
        if stroke:
            partes.append("S")
        self.ops.append(" ".join(partes))

    def line(self, x1: float, y1: float, x2: float, y2: float,
             color=(0.75, 0.75, 0.75), width: float = 0.7):
        self.ops.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG {width:g} w "
            f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def _pinta(self, camino: str, fill, stroke, width: float):
        partes = []
        if fill:
            partes.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            partes.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} "
                          f"RG {width:g} w")
        partes.append(camino)
        if fill and stroke:
            partes.append("B")
        elif fill:
            partes.append("f")
        elif stroke:
            partes.append("S")
        self.ops.append(" ".join(partes))

    def rounded_rect(self, x: float, y: float, w: float, h: float, r: float = 6,
                     fill: tuple | None = None, stroke: tuple | None = None,
                     width: float = 0.7):
        """Rectangulo con esquinas redondeadas (Bezier)."""
        r = max(0.0, min(r, w / 2, h / 2))
        k = 0.5523 * r
        camino = (
            f"{x + r:.2f} {y:.2f} m "
            f"{x + w - r:.2f} {y:.2f} l "
            f"{x + w - r + k:.2f} {y:.2f} {x + w:.2f} {y + r - k:.2f} "
            f"{x + w:.2f} {y + r:.2f} c "
            f"{x + w:.2f} {y + h - r:.2f} l "
            f"{x + w:.2f} {y + h - r + k:.2f} {x + w - r + k:.2f} {y + h:.2f} "
            f"{x + w - r:.2f} {y + h:.2f} c "
            f"{x + r:.2f} {y + h:.2f} l "
            f"{x + r - k:.2f} {y + h:.2f} {x:.2f} {y + h - r + k:.2f} "
            f"{x:.2f} {y + h - r:.2f} c "
            f"{x:.2f} {y + r:.2f} l "
            f"{x:.2f} {y + r - k:.2f} {x + r - k:.2f} {y:.2f} "
            f"{x + r:.2f} {y:.2f} c h")
        self._pinta(camino, fill, stroke, width)

    def _camino_sector(self, cx, cy, r, a0, a1, r_in):
        ops = []
        tramos = _arcos_bezier(cx, cy, r, a0, a1)
        if not tramos:
            return ""
        p0 = tramos[0][0]
        ops.append(f"{p0[0]:.2f} {p0[1]:.2f} m")
        for _, c1, c2, p1 in tramos:
            ops.append(f"{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} "
                       f"{p1[0]:.2f} {p1[1]:.2f} c")
        if r_in > 0:
            rad = math.radians(a1)
            xi = (cx + r_in * math.sin(rad), cy + r_in * math.cos(rad))
            ops.append(f"{xi[0]:.2f} {xi[1]:.2f} l")
            for _, c1, c2, p1 in _arcos_bezier(cx, cy, r_in, a1, a0):
                ops.append(f"{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} "
                           f"{p1[0]:.2f} {p1[1]:.2f} c")
        else:
            ops.append(f"{cx:.2f} {cy:.2f} l")
        ops.append("h")
        return " ".join(ops)

    def sector(self, cx: float, cy: float, r: float, a0: float, a1: float,
               fill: tuple, r_interno: float = 0.0, stroke: tuple | None = None,
               width: float = 0.7):
        """Porcion de torta o de dona (0 grados = 12 en punto, horario)."""
        camino = self._camino_sector(cx, cy, r, a0, a1, r_interno)
        if camino:
            self._pinta(camino, fill, stroke, width)

    def text_right(self, x_derecha: float, text: str, size: float = 10,
                   font: str = "F1", color=(0, 0, 0), y: float | None = None):
        """Texto alineado a la derecha en ``x_derecha``."""
        ancho = _pdf_width(text, size, font)
        self.text(x_derecha - ancho, text, size, font, color)
        if y is not None:
            self._y = y

    def text_center(self, cx: float, text: str, size: float = 10,
                    font: str = "F1", color: tuple = (0, 0, 0)):
        """Texto centrado en ``cx`` a la altura actual."""
        ancho = _pdf_width(text, size, font)
        self.text(cx - ancho / 2, text, size, font, color)

    def text_at(self, x: float, y: float, text: str, size: float = 10,
                font: str = "F1", color: tuple = (0, 0, 0)):
        """Texto en coordenadas absolutas (y medida desde abajo, como el PDF)."""
        r, g, b = color
        self.ops.append(
            f"BT /{font} {size:g} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_escape(text)}) Tj ET")

    def text_center_at(self, cx: float, y: float, text: str, size: float = 10,
                       font: str = "F1", color: tuple = (0, 0, 0)):
        ancho = _pdf_width(text, size, font)
        self.text_at(cx - ancho / 2, y, text, size, font, color)

    def header_every_page(self, titulo: str, omitir_primera: bool = False,
                          pie_izq: str = ""):
        """Agrega encabezado/pie a todas las paginas (llamar antes de save)."""
        for i, ops in enumerate(self.pages, 1):
            if omitir_primera and i == 1:
                continue
            head = [
                f"BT /F2 8 Tf 0.35 0.35 0.35 rg 1 0 0 1 {_MARGIN:.2f} {_PAGE_H - 28:.2f} Tm ({_pdf_escape(titulo)}) Tj ET",
                f"BT /F1 8 Tf 0.45 0.45 0.45 rg 1 0 0 1 {_PAGE_W - _MARGIN - 60:.2f} 24 Tm (Página {i} de {len(self.pages)}) Tj ET",
            ]
            if pie_izq:
                head.append(
                    f"BT /F1 8 Tf 0.45 0.45 0.45 rg 1 0 0 1 {_MARGIN:.2f} 24 Tm ({_pdf_escape(pie_izq)}) Tj ET")
            ops[0:0] = head

    def save(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        # Reservamos los objetos 1 (Catalog) y 2 (Pages); se completan al final,
        # cuando ya se conocen los ids de fuentes, contenidos y paginas.
        objects.append(b"")
        objects.append(b"")

        font_ids = {}
        for fname, base in _FONTS.items():
            font_ids[fname] = add(
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} /Encoding /WinAnsiEncoding >>".encode()
            )
        font_res = " ".join(f"/{k} {v} 0 R" for k, v in font_ids.items())

        page_ids = []
        for ops in self.pages:
            stream = "\n".join(ops).encode("cp1252", errors="replace")
            cid = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                      + stream + b"\nendstream")
            pid = add(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W:g} {_PAGE_H:g}] "
                f"/Resources << /Font << {font_res} >> >> /Contents {cid} 0 R >>".encode()
            )
            page_ids.append(pid)

        kids = " ".join(f"{p} 0 R" for p in page_ids)
        objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

        # Los offsets se calculan sobre bytes (out es bytearray), nunca sobre
        # caracteres, y /Length es la longitud real en bytes del stream.
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for idx, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += f"{idx} 0 obj\n".encode()
            out += body
            out += b"\nendobj\n"

        n = len(objects)
        xref_pos = len(out)
        out += f"xref\n0 {n + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {n + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_pos}\n%%EOF\n").encode()
        return bytes(out)


def _pdf_fila_barra(doc: "_PdfDoc", etiqueta: str, valor: str, pct: float,
                    color: tuple, ancho_barra: float, x_barra: float):
    doc.ensure_space(16)
    doc.text(_MARGIN + 16, etiqueta, size=8, font="F2")
    if valor:
        doc.text(_MARGIN + 150, valor, size=8)
    y = doc.y - 11
    doc.rect(x_barra, y, ancho_barra, 9, fill=(0.88, 0.89, 0.91))
    pct = max(0.0, min(100.0, float(pct or 0)))
    if pct > 0:
        doc.rect(x_barra, y, ancho_barra * pct / 100.0, 9, fill=color)
    doc.spacer(16)


def _pdf_barra_apilada(doc: "_PdfDoc", x: float, y: float, ancho: float,
                       segmentos: list):
    doc.rect(x, y, ancho, 9, fill=(0.88, 0.89, 0.91))
    total = sum(v for v, _ in segmentos) or 1
    dx = x
    for valor, color in segmentos:
        if valor <= 0:
            continue
        w = ancho * valor / total
        doc.rect(dx, y, w, 9, fill=color)
        dx += w


def _pdf_wrap(texto, ancho: float, size: float, font: str) -> list[str]:
    palabras = str(texto).split(" ")
    lineas, linea = [], ""
    for w in palabras:
        cand = (linea + " " + w).strip()
        if _pdf_width(cand, size, font) > ancho and linea:
            lineas.append(linea)
            linea = w
        else:
            linea = cand
    if linea:
        lineas.append(linea)
    return lineas or [""]


def _pdf_tabla(doc: "_PdfDoc", columnas: list, filas: list, anchos: list,
               size: float = 8.5, negrita_col0: bool = False):
    usable = _PAGE_W - 2 * _MARGIN
    anchos_px = [usable * a for a in anchos]

    def _alto(celdas, font):
        alt = [len(_pdf_wrap(c, w - 10, size, font)) * size * 1.25
               for c, w in zip(celdas, anchos_px)]
        return max(alt + [size * 1.25]) + 6

    def _fila(celdas, font, sombra, negrita_col0_fila):
        alto = _alto(celdas, font)
        doc.ensure_space(alto + 2)
        y0 = doc.y - alto
        if sombra:
            doc.rect(_MARGIN, y0, usable, alto, fill=(0.965, 0.975, 0.985))
        doc.rect(_MARGIN, y0, usable, alto, stroke=(0.80, 0.83, 0.86), width=0.5)
        x = _MARGIN
        for w in anchos_px[:-1]:
            x += w
            doc.line(x, y0, x, y0 + alto, color=(0.85, 0.87, 0.90), width=0.4)
        x = _MARGIN
        for celda, w in zip(celdas, anchos_px):
            f = "F2" if (font == "F2" or (negrita_col0_fila and celda is celdas[0])) else "F1"
            ty = y0 + alto - 4 - size
            for ln in _pdf_wrap(celda, w - 10, size, f):
                doc.text_at(x + 5, ty, ln, size=size, font=f)
                ty -= size * 1.25
            x += w
        doc.y = y0

    if columnas:
        _fila(columnas, "F2", True, False)
    for i, celdas in enumerate(filas):
        _fila(celdas, "F1", i % 2 == 1, negrita_col0)
    doc.spacer(size + 6)


def _pdf_torta(doc: "_PdfDoc", cx: float, cy: float, r: float, porciones_: list,
               r_in: float = 0.0, centro: str = ""):
    for p in porciones_:
        doc.sector(cx, cy, r, p["a0"], p["a1"], fill=_rgb_de(p["color"]),
                   r_interno=r_in, stroke=(1.0, 1.0, 1.0), width=1.2)
    if centro:
        doc.text_center_at(cx, cy - 3, centro, size=13, font="F2",
                           color=_pal_rgb("tinta"))
    lx = cx + r + 18
    ly = cy + r - 6
    for p in porciones_:
        doc.rect(lx, ly, 9, 9, fill=_rgb_de(p["color"]))
        doc.text_at(lx + 13, ly + 1.5,
                    f"{p['etiqueta']}: {p['valor']:g} ({p['porcentaje']:g}%)",
                    size=8, font="F1")
        ly -= 13


def _pdf_bloque_torta(doc: "_PdfDoc", titulo: str, porciones_: list,
                      r: float = 62):
    doc.ensure_space(2 * r + 34)
    doc.text_flow(titulo, size=10.5, font="F2", indent=8)
    cy = doc.y - r - 4
    _pdf_torta(doc, _MARGIN + 12 + r, cy, r, porciones_)
    doc.y = cy - r - 14


def _pdf_indicadores(doc: "_PdfDoc", modelo: dict):
    ind = modelo["indicadores"]
    usable = _PAGE_W - 2 * _MARGIN
    gap = 10
    w = (usable - 3 * gap) / 4
    h = 62
    tarjetas = [
        ("PUNTAJE DE SALUD", "—" if ind["puntaje"] is None else f"{ind['puntaje']}/100",
         _METRICAS_RGB.get(ind["etiqueta"], (0.62, 0.70, 0.80))),
        ("PROBLEMAS", str(ind["problemas"]), _pal_rgb("critico")),
        ("COLECTORES", f"{ind['ok']} OK", _pal_rgb("ok")),
        ("COBERTURA", f"{ind['cobertura']}%", _pal_rgb("acento")),
    ]
    doc.ensure_space(h + 12)
    y0 = doc.y - h
    x = _MARGIN
    for titulo, valor, col in tarjetas:
        doc.rounded_rect(x, y0, w, h, 8, fill=(0.98, 0.99, 1.0),
                         stroke=(0.86, 0.89, 0.92), width=0.6)
        doc.rounded_rect(x, y0 + h - 5, w, 5, 2, fill=col)
        doc.text_at(x + 8, y0 + h - 18, titulo, size=7.5, font="F1",
                    color=(0.42, 0.42, 0.42))
        doc.text_at(x + 8, y0 + 16, valor, size=15, font="F2", color=col)
        x += w + gap
    doc.y = y0 - 12


def _pdf_panel_grafico(doc: "_PdfDoc", modelo: dict):
    m = modelo["metricas"]
    if not m or m.get("puntaje") is None and not modelo["torta_estado"]:
        doc.text_flow("Sin datos para graficar.", size=9, font="F3", indent=8)
        return
    _pdf_bloque_torta(doc, "Problemas por severidad", modelo["torta_severidad"])
    _pdf_bloque_torta(doc, "Estado de los colectores", modelo["torta_estado"])

    discos = modelo["discos"]
    if discos:
        doc.ensure_space(20)
        doc.text_flow("Ocupación de discos", size=10.5, font="F2", indent=8)
        for d in discos[:6]:
            porc = _porciones_dona_disco(d)
            r = 38
            doc.ensure_space(2 * r + 20)
            doc.text_flow(
                f"Disco {d.get('unidad', '')} — {_g(d.get('total_gb'), 'GB')} total, "
                f"{_g(d.get('libre_gb'), 'GB')} libre", size=8.5, font="F2", indent=8)
            cy = doc.y - r - 2
            _pdf_torta(doc, _MARGIN + 12 + r, cy, r, porc, r_in=r - 13,
                       centro=f"{d.get('usado_porcentaje')}%")
            doc.y = cy - r - 10

    mem = modelo.get("memoria")
    doc.ensure_space(20)
    doc.text_flow("Memoria", size=10.5, font="F2", indent=8)
    ancho_barra = _PAGE_W - 2 * _MARGIN - 16 - 210
    if mem and mem.get("usado_porcentaje") is not None:
        _pdf_fila_barra(doc, "Memoria en uso", f"{mem['usado_porcentaje']}%",
                        mem["usado_porcentaje"],
                        _color_nivel_medidor_rgb("memoria", mem["usado_porcentaje"]),
                        ancho_barra, _MARGIN + 210)
    if modelo.get("leyenda_medidores"):
        doc.text_flow(modelo["leyenda_medidores"], size=8, font="F3", indent=16,
                      color=(0.4, 0.4, 0.4))

    cats = modelo["categorias"]
    if cats:
        doc.ensure_space(20)
        doc.text_flow("Estado por paquete", size=10.5, font="F2", indent=8)
        ancho_pkg = _PAGE_W - 2 * _MARGIN - 16
        for c in cats:
            ok = c.get("ok", 0)
            sin = c.get("sin_datos", 0)
            err = c.get("error", 0) + c.get("timeout", 0)
            ne = c.get("no_evaluado", 0)
            hall = c.get("hallazgos") or {}
            doc.ensure_space(26)
            doc.text(_MARGIN + 8, str(c.get("paquete", ""))[:40], size=8, font="F2")
            doc.text(_MARGIN + 175, f"OK {ok} / s/d {sin} / err {err} | "
                                    f"H C{hall.get('critical', 0)} "
                                    f"E{hall.get('error', 0)} "
                                    f"A{hall.get('warning', 0)}", size=8)
            y = doc.y - 12
            _pdf_barra_apilada(doc, _MARGIN + 8, y, ancho_pkg, [
                (ok, _pal_rgb("ok")), (sin, _pal_rgb("sin_datos")),
                (err, _pal_rgb("critico")), (ne, _pal_rgb("no_evaluado"))])
            doc.spacer(18)

    comp = modelo.get("comparacion")
    if comp:
        doc.ensure_space(20)
        doc.text_flow("Comparación antes / después", size=10.5, font="F2", indent=8)
        for etiqueta, mm in (("Antes", comp["base"]), ("Después", comp["actual"])):
            val = mm.get("puntaje")
            col = _METRICAS_RGB.get(mm.get("etiqueta"), (0.62, 0.70, 0.80))
            _pdf_fila_barra(doc, etiqueta, "-" if val is None else str(val),
                            val or 0, col, ancho_barra, _MARGIN + 210)


def _pdf_portada(doc: "_PdfDoc", modelo: dict):
    alto = 128
    doc.rect(0, _PAGE_H - alto, _PAGE_W, alto, fill=_pal_rgb("tinta"))
    doc.rounded_rect(_MARGIN, _PAGE_H - 90, 52, 52, 12, fill=_pal_rgb("acento"))
    doc.rounded_rect(_MARGIN + 13, _PAGE_H - 81, 26, 34, 3, fill=(1, 1, 1))
    doc.rect(_MARGIN + 18, _PAGE_H - 75, 16, 3, fill=_pal_rgb("tinta"))
    doc.rect(_MARGIN + 18, _PAGE_H - 67, 16, 3, fill=_pal_rgb("verde"))
    doc.rect(_MARGIN + 18, _PAGE_H - 59, 10, 3, fill=_pal_rgb("advertencia"))
    doc.text_at(_MARGIN + 68, _PAGE_H - 62, "DiagUSB", size=22, font="F2",
                color=(1, 1, 1))
    doc.text_at(_MARGIN + 68, _PAGE_H - 78, "Informe de diagnóstico técnico",
                size=10, font="F1", color=(0.72, 0.78, 0.86))

    doc.y = _PAGE_H - alto - 34
    doc.text_flow(modelo["tipo"], size=20, font="F2", color=_pal_rgb("tinta"))
    doc.text_flow(f"Motivo: {modelo['sintoma'] or '—'}", size=10, font="F3",
                  color=(0.3, 0.3, 0.3))
    doc.spacer(10)
    eq = modelo["equipo"]
    filas = [
        ("Equipo", _g(eq.get("computer_name"))),
        ("Sistema operativo", _g(eq.get("os"))),
        ("Usuario", _g(eq.get("user"))),
        ("Modo", modelo["modo"]),
        ("Fecha", _g(modelo["fecha"])),
        ("Técnico", _g(modelo["tecnico"], vacio="________________________")),
        ("Cliente / Sector", _g(modelo["cliente"], vacio="________________________")),
        ("Código de verificación", modelo["codigo"]),
    ]
    _pdf_tabla(doc, [], filas, [0.32, 0.68], size=9.5, negrita_col0=True)
    doc.spacer(6)
    doc.text_flow("Puntaje orientativo. No reemplaza al diagnóstico profesional ni a "
                  "las pruebas de cada fabricante.", size=8.5, font="F3",
                  color=(0.4, 0.4, 0.4))
    doc._new_page()


def informe_a_pdf(informe: InformeData) -> bytes:
    doc = _PdfDoc()
    e = informe
    modelo = _modelo_documento(e)
    n_seccion = 0
    sev_color = {"critical": _pal_rgb("critico"), "error": _pal_rgb("error"),
                 "warning": _pal_rgb("advertencia"), "ok": _pal_rgb("ok")}

    def _sec(titulo: str) -> str:
        nonlocal n_seccion
        n_seccion += 1
        return f"{n_seccion}. {titulo}"

    def _heading(titulo: str):
        doc.ensure_space(30)
        doc.spacer(10)
        doc.text_flow(_sec(titulo), size=12.5, font="F2", color=_pal_rgb("acento"))

    _pdf_portada(doc, modelo)

    for adv in modelo["advertencias"]:
        doc.text_flow(adv, size=10, font="F2", color=(0.7, 0.35, 0))
        doc.spacer(2)

    _heading("Datos del servicio")
    doc.text_flow(modelo["alcance"], size=9, font="F3", color=(0.4, 0.4, 0.4), indent=8)
    eq = modelo["equipo"]
    _pdf_tabla(doc, [], [
        ("Equipo", _g(eq.get("computer_name"))),
        ("Usuario", _g(eq.get("user"))),
        ("Técnico", _g(modelo["tecnico"])),
        ("Cliente / Sector", _g(modelo["cliente"])),
        ("Modo de ejecución", modelo["modo"]),
        ("Sistema operativo", _g(eq.get("os"))),
        ("Versión / Build", _g(f"{eq.get('os_version', '')} ({eq.get('build', '')})"
                               if eq.get("os_version") else None)),
    ], [0.30, 0.70], size=9.5, negrita_col0=True)

    _heading("Indicadores")
    _pdf_indicadores(doc, modelo)

    _heading("Resumen ejecutivo")
    for frase in modelo["resumen_ejecutivo"]:
        doc.text_flow(f"- {frase}", size=9, indent=8)

    _heading("Panel gráfico")
    _pdf_panel_grafico(doc, modelo)

    _heading("Problemas detectados")
    if modelo["problemas_tabla"]:
        filas = [[str(f["indice"]),
                  SEVERIDAD_LABEL.get(f["severidad"], f["severidad"]),
                  f["titulo"], f["colector"], f["estado"]]
                 for f in modelo["problemas_tabla"]]
        _pdf_tabla(doc, ["#", "Severidad", "Título", "Colector", "Estado"], filas,
                   [0.06, 0.15, 0.40, 0.22, 0.17], size=8.5)
    if not e.problemas:
        doc.text_flow("No se detectaron problemas automáticos en este análisis.",
                      size=9, font="F3", indent=8)
    for p in e.problemas:
        doc.ensure_space(70)
        doc.text_flow(f"[{SEVERIDAD_LABEL.get(p.severidad, p.severidad)}] {p.titulo}",
                      size=10, font="F2", color=sev_color.get(p.severidad, (0.3, 0.3, 0.3)),
                      indent=8)
        doc.text_flow(f"Colector: {p.colector}", size=8, font="F3", indent=16,
                      color=(0.4, 0.4, 0.4))
        if p.detalle:
            detalle = ", ".join(f"{k}: {_fmt_valor(v)}" for k, v in p.detalle.items()
                                if k not in ("grupo_mensajes", "grupo_total"))
            if detalle:
                doc.text_flow(f"Qué ocurre: {detalle}", size=9, indent=16)
        if p.estado_esperado:
            doc.text_flow(f"Cómo debe estar: {p.estado_esperado}", size=9, font="F2", indent=16)
        if p.por_que:
            doc.text_flow(f"Por qué importa: {p.por_que}", size=8, font="F3", indent=16,
                          color=(0.35, 0.35, 0.35))
        if p.soluciones:
            doc.text_flow("Pasos sugeridos:", size=9, font="F2", indent=16)
            for s in p.soluciones:
                doc.text_flow(f"- {s}", size=8, indent=24)
        if p.verificacion:
            doc.text_flow(f"Verificación: {p.verificacion}", size=9, indent=16)
        if p.grupo:
            doc.text_flow(f"Otros casos del mismo problema ({len(p.grupo)} más):",
                          size=9, font="F2", indent=16)
            for m in p.grupo[:5]:
                doc.text_flow(f"- {m}", size=8, indent=24, color=(0.35, 0.35, 0.35))
        doc.ensure_space(18)
        y = doc.y - 11
        doc.rounded_rect(_MARGIN + 16, y, 9, 9, 2, stroke=(0.4, 0.4, 0.4), width=0.7)
        doc.text(_MARGIN + 30, f"Acción: {p.estado}", size=9, font="F2")
        doc.spacer(13)
        if p.solucion_elegida:
            doc.text_flow(f"Solución aplicada: {p.solucion_elegida}", size=9, indent=16)
        if p.solucion:
            doc.text_flow(f"Descripción de la acción: {p.solucion}", size=9, indent=16)
        doc.spacer(4)

    _heading("Plan de acción")
    if modelo["recomendaciones"]:
        doc.text_flow("Recomendaciones generales", size=10, font="F2", indent=8)
        for rec in modelo["recomendaciones"]:
            doc.text_flow(f"- {rec}", size=9, indent=16)
        doc.spacer(6)
    doc.text_flow("Acciones pendientes", size=10, font="F2", indent=8)
    pendientes = []
    for p in e.problemas:
        sev = SEVERIDAD_LABEL.get(p.severidad, p.severidad)
        for a in (p.soluciones or [p.recomendacion or "Revisar el problema detectado."])[:2]:
            pendientes.append(["[  ]", sev, a, f"Problema {p.indice} · {p.colector}"])
    for m in e.mejoras:
        if not m.aplicada:
            pendientes.append(["[  ]", "Mejora", m.titulo, m.detalle[:80]])
    if not pendientes:
        pendientes = [["[  ]", "—", "Sin acciones pendientes.", ""]]
    _pdf_tabla(doc, ["Hecho", "Prior.", "Acción", "Referencia"], pendientes,
               [0.08, 0.12, 0.48, 0.32], size=8.5)

    _heading("Ficha técnica")
    for titulo, filas in modelo["ficha_tecnica"]:
        doc.ensure_space(20)
        doc.text_flow(titulo, size=10, font="F2", indent=8)
        doc.spacer(4)
        _pdf_tabla(doc, [], [(k, str(v)) for k, v in filas], [0.32, 0.68],
                   size=8.5, negrita_col0=True)

    doc._new_page()
    _heading("Anexo técnico")
    filas_anexo = []
    for f in modelo["anexo"]:
        filas_anexo.append([f["colector"], f["paquete"], f["estado"],
                            f"{f['duracion_ms']} ms", f["resumen"]])
        for linea in f["detalle"]:
            filas_anexo.append(["", "", "", "", linea])
        if f["registros_restantes"]:
            filas_anexo.append(["", "", "", "",
                                f"{f['registros_restantes']} registro(s) más en el JSON"])
    _pdf_tabla(doc, ["Colector", "Paquete", "Estado", "Duración", "Resumen"],
               filas_anexo, [0.18, 0.16, 0.10, 0.11, 0.45], size=8)

    _heading("Cierre")
    doc.text_flow(f"Observaciones: {modelo['observaciones'] or '__________________________________________'}",
                  size=9, indent=8)
    doc.spacer(20)
    doc.text_flow("____________________________________          ____________________________________",
                  size=9, indent=8)
    doc.text_flow("Firma del técnico                                        Conformidad del cliente",
                  size=8, font="F3", indent=8, color=(0.4, 0.4, 0.4))
    doc.spacer(4)
    doc.text_flow(f"Código de verificación: {modelo['codigo']}",
                  size=8, font="F3", indent=8, color=(0.4, 0.4, 0.4))
    doc.text_flow("Informe generado por DiagUSB. El puntaje es orientativo.",
                  size=8, font="F3", indent=8, color=(0.5, 0.5, 0.5))

    doc.header_every_page(f"DiagUSB - Informe: {e.paquete.get('label', '')} - "
                          f"{_fmt_fecha(e.generado_en)}", omitir_primera=True,
                          pie_izq=f"Código: {modelo['codigo']}")
    return doc.save()
