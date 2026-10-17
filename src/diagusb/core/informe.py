# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modelo y generadores de informes completos DiagUSB (HTML, Word .doc, PDF).

Sin dependencias externas: el PDF se genera con un motor minimo propio y
el Word es un HTML con la cabecera especifica de Microsoft Word.
"""

import hashlib
import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import knowledge_base as kb

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
    falta de permisos (``installed_software``) o porque un dato no esta
    disponible (``physical_disks`` sin fiabilidad en USB o por tiempo agotado).
    """
    if status != "ok":
        return ""
    if collector_id == "installed_software":
        d = _primer_dict(data)
        if d is not None and d.get("optional_features_available") is False:
            return "requiere administrador"
    if collector_id == "physical_disks":
        for x in (data if isinstance(data, list) else [data]):
            if isinstance(x, dict) and x.get("reliability") is None \
                    and x.get("reliability_motivo"):
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
                              comparacion_forzada: bool = False) -> InformeData:
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


def informe_a_html(informe: InformeData, con_anexo: bool = False,
                   resultados_completos: list | None = None) -> str:
    e = informe
    n_seccion = 0

    def _sec(titulo: str) -> str:
        nonlocal n_seccion
        n_seccion += 1
        return f"<h2>{n_seccion}. {titulo}</h2>"

    out = [f"<html><head><meta charset='utf-8'><title>Informe DiagUSB</title>",
           f"<style>{_CSS_PRINT}</style></head><body>"]
    out.append(f"<h1>INFORME DE DIAGNÓSTICO - DiagUSB</h1>")
    out.append(f"<p class='muted'>Generado: {_esc(_fmt_fecha(e.generado_en))} | "
               f"Paquete: <b>{_esc(e.paquete.get('label'))}</b> | "
               f"Síntoma: {_esc(e.paquete.get('symptom'))}</p>")
    out.append(f"<p class='muted'><b>{_esc(linea_alcance(e))}</b></p>")
    for adv in e.advertencias:
        out.append(f"<p class='advertencia'><b>{_esc(adv)}</b></p>")

    out.append(_sec("Datos del equipo"))
    if e.equipo:
        out.append("<table class='kv'>")
        labels = [
            ("computer_name", "Equipo"), ("user", "Usuario"),
            ("is_elevated", "Permisos elevados"), ("os", "Sistema operativo"),
            ("os_version", "Version"), ("build", "Build"),
        ]
        for k, label in labels:
            out.append(f"<tr><td>{label}</td><td>{_esc(_fmt_valor(e.equipo.get(k)))}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='muted'>Sin datos de equipo.</p>")

    r = e.resumen
    out.append(_sec("Resumen del diagnóstico"))
    out.append("<table class='kv'>")
    out.append(f"<tr><td>Colectores ejecutados</td><td>{r.get('colectores_total', 0)} "
               f"(OK: {r.get('colectores_ok', 0)}, con error: {r.get('colectores_error', 0)})</td></tr>")
    out.append(f"<tr><td>Problemas detectados</td><td>{r.get('problemas_total', 0)} "
               f"(Críticos: {r.get('criticos', 0)}, Errores: {r.get('errores', 0)}, "
               f"Advertencias: {r.get('advertencias', 0)})</td></tr>")
    if e.tecnico:
        out.append(f"<tr><td>Técnico</td><td>{_esc(e.tecnico)}</td></tr>")
    if e.cliente:
        out.append(f"<tr><td>Cliente / Sector</td><td>{_esc(e.cliente)}</td></tr>")
    out.append("</table>")

    out.append(_sec("Problemas detectados y acciones del técnico"))
    if not e.problemas:
        out.append("<p>No se detectaron problemas automaticamente para este paquete.</p>")
    for p in e.problemas:
        color = _SEVERIDAD_COLOR.get(p.severidad, "#888")
        out.append(f"<div class='problema' style='border-left-color: {color};'>")
        out.append(f"<h3><span class='badge' style='background: {color};'>"
                   f"{_esc(SEVERIDAD_LABEL.get(p.severidad, p.severidad))}</span> "
                   f"{_esc(p.titulo)}</h3>")
        out.append(f"<p class='muted'>Colector: {_esc(p.colector)}</p>")
        if p.detalle:
            detalle = ", ".join(f"{k}: {_fmt_valor(v)}" for k, v in p.detalle.items()
                                if k not in ("grupo_mensajes", "grupo_total"))
            if detalle:
                out.append(f"<p><b>Detalle:</b> {_esc(detalle)}</p>")
        if p.grupo:
            out.append(f"<p><b>Otros casos del mismo problema "
                       f"({len(p.grupo)} más):</b></p><ul>")
            for m in p.grupo:
                out.append(f"<li>{_esc(m)}</li>")
            out.append("</ul>")
        if p.estado_esperado:
            out.append(f"<p><b>Cómo debe estar (estado esperado):</b> {_esc(p.estado_esperado)}</p>")
        if p.por_que:
            out.append(f"<p class='muted'><b>Por qué importa:</b> {_esc(p.por_que)}</p>")
        if p.verificacion:
            out.append(f"<p><b>Verificación:</b> {_esc(p.verificacion)}</p>")
        if p.soluciones:
            out.append("<p><b>Soluciones posibles:</b></p><ul>")
            for s in p.soluciones:
                out.append(f"<li>{_esc(s)}</li>")
            out.append("</ul>")
        out.append(f"<p><b>Estado:</b> {_esc(p.estado)}")
        if p.solucion_elegida:
            out.append(f" &nbsp;|&nbsp; <b>Solución aplicada (de la lista):</b> {_esc(p.solucion_elegida)}")
        if p.solucion:
            out.append(f" &nbsp;|&nbsp; <b>Descripción de la acción:</b> {_esc(p.solucion)}")
        if not p.solucion_elegida and not p.solucion:
            out.append(" &nbsp;|&nbsp; <i class='muted'>Acción implementada: (sin registrar)</i>")
        out.append("</p></div>")

    if e.mejoras:
        out.append(_sec("Mejoras sugeridas"))
        out.append("<table><tr><td class='th' style='width:22%'>Mejora</td>"
                   "<td class='th' style='width:48%'>Detalle</td>"
                   "<td class='th' style='width:12%'>Implementada</td>"
                   "<td class='th' style='width:18%'>Comentario</td></tr>")
        for m in e.mejoras:
            out.append(f"<tr><td>{_esc(m.titulo)}</td><td>{_esc(m.detalle)}</td>"
                       f"<td>{'Sí' if m.aplicada else 'No'}</td><td>{_esc(m.comentario) or '-'}</td></tr>")
        out.append("</table>")

    if e.diferencias:
        out.append(_sec("Cambios detectados (antes vs después)"))
        out.append("<table><tr><td class='th' style='width:16%'>Colector</td>"
                   "<td class='th' style='width:24%'>Campo</td>"
                   "<td class='th' style='width:30%'>Antes</td>"
                   "<td class='th' style='width:30%'>Después</td></tr>")
        for d in e.diferencias:
            out.append(f"<tr><td>{_esc(d.get('collector_id', ''))}</td>"
                       f"<td>{_esc(d.get('field_path', ''))}</td>"
                       f"<td>{_esc(_fmt_valor_truncado(d.get('baseline_value')))}</td>"
                       f"<td>{_esc(_fmt_valor_truncado(d.get('current_value')))}</td></tr>")
        out.append("</table>")

    if e.recomendaciones:
        out.append(_sec("Recomendaciones generales") + "<ul>")
        for rec in e.recomendaciones:
            out.append(f"<li>{_esc(rec)}</li>")
        out.append("</ul>")

    out.append(_sec("Análisis por colector"))
    out.append("<table><tr><td class='th' style='width:16%'>Colector</td>"
               "<td class='th' style='width:10%'>Estado</td>"
               "<td class='th' style='width:10%'>Duración</td>"
               "<td class='th' style='width:32%'>Resumen</td>"
               "<td class='th' style='width:32%'>Observaciones</td></tr>")
    for c in e.colectores:
        st_color = _SEVERIDAD_COLOR.get(
            "ok" if c.status == "ok" else ("warning" if c.status in ("empty", "not_available") else "error"),
            "#888")
        resumen = "<br>".join(_esc(x) for x in c.resumen) or "-"
        obs = "<br>".join(_esc(x) for x in c.errores) or "-"
        out.append(f"<tr><td>{_esc(c.collector_id)}</td>"
                   f"<td><span class='badge' style='background: {st_color};'>{_esc(c.status)}</span></td>"
                   f"<td>{c.duration_ms} ms</td><td class='mono'>{resumen}</td>"
                   f"<td class='mono'>{obs}</td></tr>")
    out.append("</table>")

    if e.observaciones:
        out.append(_sec("Observaciones generales"))
        out.append(f"<p class='mono'>{_esc(e.observaciones)}</p>")

    if con_anexo and resultados_completos:
        out.append("<h2>Anexo A: Datos crudos de los colectores (JSON)</h2>")
        out.append("<pre class='mono'>")
        out.append(_esc(json.dumps(resultados_completos, ensure_ascii=False, indent=2)[:200000]))
        out.append("</pre>")

    out.append("<table class='firma'><tr><td>Firma del técnico</td>"
               "<td>Conformidad del cliente</td></tr></table>")
    out.append(f"<p class='muted mono'>Código de verificación: {codigo_verificacion(e)}</p>")
    out.append("</body></html>")
    return "".join(out)


def informe_a_doc(informe: InformeData, resultados_completos: list | None = None,
                  con_anexo: bool = False) -> bytes:
    """Genera un archivo .doc (HTML con formato Word). Word lo abre directamente.

    El volcado JSON crudo de los colectores solo se incluye si ``con_anexo`` es
    True (cuando el técnico lo pide); por defecto no aparece.
    """
    body = informe_a_html(informe, con_anexo=con_anexo, resultados_completos=resultados_completos)
    doc = (
        "<html xmlns:o='urn:schemas-microsoft-com:office:office' "
        "xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>"
        "<head><meta charset='utf-8'><title>Informe DiagUSB</title>"
        "<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View>"
        "<w:Zoom>100</w:Zoom></w:WordDocument></xml><![endif]-->"
        "<style>@page WordSection1 { size: 21cm 29.7cm; margin: 2cm; }"
        "div.WordSection1 { page: WordSection1; }"
        + _CSS_WORD + "</style></head>"
        "<body><div class='WordSection1'>" + body[body.find("<body>") + 6:body.rfind("</body>")] +
        "</div></body></html>"
    )
    return b"\xef\xbb\xbf" + doc.encode("utf-8")


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

    def header_every_page(self, titulo: str):
        """Agrega encabezado/pie a todas las paginas (llamar antes de save)."""
        for i, ops in enumerate(self.pages, 1):
            head = [
                f"BT /F2 8 Tf 0.35 0.35 0.35 rg 1 0 0 1 {_MARGIN:.2f} {_PAGE_H - 28:.2f} Tm ({_pdf_escape(titulo)}) Tj ET",
                f"BT /F1 8 Tf 0.45 0.45 0.45 rg 1 0 0 1 {_PAGE_W - _MARGIN - 60:.2f} 24 Tm (Pagina {i} de {len(self.pages)}) Tj ET",
            ]
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


def informe_a_pdf(informe: InformeData) -> bytes:
    doc = _PdfDoc()
    e = informe
    n_seccion = 0

    def _sec(titulo: str) -> str:
        nonlocal n_seccion
        n_seccion += 1
        return f"{n_seccion}. {titulo}"

    doc.text_flow("INFORME DE DIAGNÓSTICO - DiagUSB", size=16, font="F2", color=(0.10, 0.45, 0.91))
    doc.spacer(2)
    doc.text_flow(f"Generado: {_fmt_fecha(e.generado_en)}  |  Paquete: {e.paquete.get('label', '')}  |  "
                  f"Síntoma: {e.paquete.get('symptom', '')}", size=9, font="F3", color=(0.4, 0.4, 0.4))
    doc.text_flow(linea_alcance(e), size=9, font="F2", color=(0.7, 0.35, 0))
    doc.hrule()

    for adv in e.advertencias:
        doc.text_flow(adv, size=10, font="F2", color=(0.7, 0.35, 0))
        doc.spacer(2)

    doc.text_flow(_sec("Datos del equipo"), size=12, font="F2", color=(0.10, 0.45, 0.91))
    if e.equipo:
        labels = [
            ("Equipo", e.equipo.get("computer_name")),
            ("Usuario", e.equipo.get("user")),
            ("Permisos elevados", _fmt_valor(e.equipo.get("is_elevated"))),
            ("Sistema operativo", e.equipo.get("os")),
            ("Versión / Build", f"{e.equipo.get('os_version', '')} ({e.equipo.get('build', '')})"),
        ]
        for k, v in labels:
            doc.text_flow(f"{k}: {v}", size=9, indent=8)
    else:
        doc.text_flow("Sin datos de equipo.", size=9, font="F3", indent=8)
    doc.spacer(4)

    doc.text_flow(_sec("Resumen del diagnóstico"), size=12, font="F2", color=(0.10, 0.45, 0.91))
    r = e.resumen
    doc.text_flow(f"Colectores ejecutados: {r.get('colectores_total', 0)} "
                  f"(OK: {r.get('colectores_ok', 0)}, con error: {r.get('colectores_error', 0)})",
                  size=9, indent=8)
    doc.text_flow(f"Problemas detectados: {r.get('problemas_total', 0)} "
                  f"(Críticos: {r.get('criticos', 0)}, Errores: {r.get('errores', 0)}, "
                  f"Advertencias: {r.get('advertencias', 0)})", size=9, indent=8)
    if e.tecnico:
        doc.text_flow(f"Técnico: {e.tecnico}", size=9, indent=8)
    if e.cliente:
        doc.text_flow(f"Cliente / Sector: {e.cliente}", size=9, indent=8)
    doc.spacer(4)

    doc.text_flow(_sec("Problemas detectados y acciones del técnico"), size=12, font="F2",
                  color=(0.10, 0.45, 0.91))
    if not e.problemas:
        doc.text_flow("No se detectaron problemas automáticos para este paquete.",
                      size=9, font="F3", indent=8)
    for p in e.problemas:
        sev_color = {"critical": (0.7, 0, 0.13), "error": (0.85, 0.19, 0.15),
                     "warning": (0.89, 0.46, 0), "ok": (0.09, 0.5, 0.22)}.get(
            p.severidad, (0.3, 0.3, 0.3))
        doc.text_flow(f"[{SEVERIDAD_LABEL.get(p.severidad, p.severidad)}] {p.titulo}",
                      size=10, font="F2", color=sev_color, indent=8)
        doc.text_flow(f"Colector: {p.colector}", size=8, font="F3", indent=16,
                      color=(0.4, 0.4, 0.4))
        if p.detalle:
            detalle = ", ".join(f"{k}: {_fmt_valor(v)}" for k, v in p.detalle.items()
                                if k not in ("grupo_mensajes", "grupo_total"))
            if detalle:
                doc.text_flow(f"Detalle: {detalle}", size=9, indent=16)
        if p.grupo:
            doc.text_flow(f"Otros casos del mismo problema ({len(p.grupo)} más):",
                          size=9, font="F2", indent=16)
            for m in p.grupo:
                doc.text_flow(f"- {m}", size=8, indent=24, color=(0.35, 0.35, 0.35))
        if p.estado_esperado:
            doc.text_flow(f"Cómo debe estar (estado esperado): {p.estado_esperado}",
                          size=9, font="F2", indent=16)
        if p.por_que:
            doc.text_flow(f"Por qué importa: {p.por_que}", size=8, font="F3", indent=16,
                          color=(0.35, 0.35, 0.35))
        if p.verificacion:
            doc.text_flow(f"Verificación: {p.verificacion}", size=9, indent=16)
        if p.soluciones:
            doc.text_flow("Soluciones posibles:", size=9, font="F2", indent=16)
            for s in p.soluciones:
                doc.text_flow(f"- {s}", size=8, indent=24)
        doc.text_flow(f"Estado de la acción: {p.estado}", size=9, font="F2", indent=16)
        if p.solucion_elegida:
            doc.text_flow(f"Solución aplicada (de la lista): {p.solucion_elegida}",
                          size=9, indent=16, font="F2")
        doc.text_flow(f"Descripción de la acción: {p.solucion or '(sin registrar)'}",
                      size=9, indent=16, font="F3" if not p.solucion else "F1")
        doc.spacer(4)

    if e.mejoras:
        doc.text_flow(_sec("Mejoras sugeridas"), size=12, font="F2", color=(0.10, 0.45, 0.91))
        for m in e.mejoras:
            marca = "[X]" if m.aplicada else "[ ]"
            doc.text_flow(f"{marca} {m.titulo}", size=9, font="F2", indent=8)
            doc.text_flow(m.detalle, size=8, indent=16, color=(0.3, 0.3, 0.3))
            if m.comentario:
                doc.text_flow(f"Comentario: {m.comentario}", size=8, font="F3", indent=16)
        doc.spacer(4)

    if e.diferencias:
        doc.text_flow(_sec("Cambios detectados (antes vs después)"), size=12, font="F2",
                      color=(0.10, 0.45, 0.91))
        for d in e.diferencias:
            doc.text_flow(
                f"{d.get('collector_id', '')} / {d.get('field_path', '')}: "
                f"{_fmt_valor_truncado(d.get('baseline_value'))}  ->  "
                f"{_fmt_valor_truncado(d.get('current_value'))}",
                size=8, indent=8)
        doc.spacer(4)

    if e.recomendaciones:
        doc.text_flow(_sec("Recomendaciones generales"), size=12, font="F2", color=(0.10, 0.45, 0.91))
        for rec in e.recomendaciones:
            doc.text_flow(f"- {rec}", size=9, indent=8)
        doc.spacer(4)

    doc.text_flow(_sec("Análisis por colector"), size=12, font="F2", color=(0.10, 0.45, 0.91))
    for c in e.colectores:
        estado = c.status
        doc.text_flow(f"{c.collector_id}  [{estado}]  ({c.duration_ms} ms)",
                      size=9, font="F2", indent=8)
        for line in c.resumen[:10]:
            doc.text_flow(line, size=8, indent=16, color=(0.25, 0.25, 0.25))
        for err in c.errores:
            doc.text_flow(f"Observación: {err}", size=8, indent=16, color=(0.7, 0, 0.13))
        doc.spacer(2)

    if e.observaciones:
        doc.text_flow(_sec("Observaciones generales"), size=12, font="F2", color=(0.10, 0.45, 0.91))
        doc.text_flow(e.observaciones, size=9, indent=8)

    doc.spacer(30)
    doc.text_flow("____________________________________          ____________________________________",
                  size=9, indent=8)
    doc.text_flow("Firma del técnico                                        Conformidad del cliente",
                  size=8, font="F3", indent=8, color=(0.4, 0.4, 0.4))
    doc.spacer(4)
    doc.text_flow(f"Código de verificación: {codigo_verificacion(e)}",
                  size=8, font="F3", indent=8, color=(0.4, 0.4, 0.4))

    doc.header_every_page(f"DiagUSB - Informe: {e.paquete.get('label', '')} - {_fmt_fecha(e.generado_en)}")
    return doc.save()
