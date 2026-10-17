# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Metricas de salud de DiagUSB: funciones puras, sin I/O.

El puntaje es ORIENTATIVO y se calcula solo sobre los hallazgos reales del
analisis ejecutado. No reemplaza al diagnostico ni inventa datos: si no hay
modulos ejecutados no hay puntaje (``None`` / "Sin datos").
"""

VERSION_FORMULA = 1

PESOS = {"critical": 15, "error": 8, "warning": 3, "ok": 0}
LABEL_SEVERIDAD = {"critical": "Crítico", "error": "Error",
                   "warning": "Advertencia", "ok": "OK"}
LEYENDA_PUNTAJE = "Puntaje orientativo sobre los módulos ejecutados"

_COBERTURA_PARCIAL = 60.0
_ESTADOS_ERROR = ("error", "timeout")
_ESTADOS_DENEGADO = ("denied", "not_available")
_RANGO_SEVERIDAD = {"critical": 3, "error": 2, "warning": 1, "ok": 0}


def _primer_dict(data):
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict):
                return x
    return None


def _collectors(resultado: dict) -> list[dict]:
    """Colectores del analisis (desde ``results`` o desde ``colectores``)."""
    res = resultado.get("results")
    if isinstance(res, list) and res:
        return [r for r in res if isinstance(r, dict)]
    col = resultado.get("colectores")
    if isinstance(col, list):
        return [{"collector_id": c.get("id"),
                 "query": {"status": c.get("status")}}
                for c in col if isinstance(c, dict)]
    return []


def _status(r: dict) -> str:
    return ((r.get("query") or {}).get("status") or "unknown")


def _es_no_evaluado(f: dict) -> bool:
    return bool((f.get("details") or {}).get("no_evaluado"))


def calcular_metricas(resultado: dict, modulos: int | None = None) -> dict:
    """Calcula las metricas orientativas de un diagnostico (puro).

    ``resultado`` es el payload de un diagnostico (``/api/diagnose``, una
    entrada del registro o el combinado de una revision total) con al menos
    ``results``/``colectores`` y ``findings``. ``modulos`` permite informar
    cuantos modulos (paquetes) se ejecutaron cuando no se puede inferir.
    """
    resultado = resultado or {}
    collectors = _collectors(resultado)
    ejecutados = len(collectors)
    ok = sum(1 for r in collectors if _status(r) == "ok")
    vacios = sum(1 for r in collectors if _status(r) == "empty")
    con_error = sum(1 for r in collectors if _status(r) in _ESTADOS_ERROR)
    denegados = sum(1 for r in collectors if _status(r) in _ESTADOS_DENEGADO)
    no_evaluados = con_error + denegados
    porcentaje = round(ok / ejecutados * 100, 1) if ejecutados else 0.0

    if modulos is None:
        modulos = resultado.get("modulos_ejecutados")
        if not isinstance(modulos, int):
            modulos = 1 if ejecutados else 0

    findings = [f for f in (resultado.get("findings") or [])
                if isinstance(f, dict)]
    conteos = {"critical": 0, "error": 0, "warning": 0, "ok": 0}
    severidad_por_collector: dict[str, int] = {}
    for f in findings:
        if _es_no_evaluado(f):
            continue
        sev = f.get("severity")
        if sev in conteos:
            conteos[sev] += 1
        cid = f.get("collector_id") or ""
        rango = _RANGO_SEVERIDAD.get(sev, 0)
        severidad_por_collector[cid] = max(
            severidad_por_collector.get(cid, 0), rango)

    if ejecutados == 0:
        puntaje = None
    else:
        resta = sum(PESOS.get(s, 0) * n for s, n in conteos.items())
        puntaje = max(0, 100 - resta)

    if puntaje is None:
        etiqueta = "Sin datos"
    elif porcentaje < _COBERTURA_PARCIAL:
        etiqueta = "Datos parciales"
    elif puntaje >= 85:
        etiqueta = "Bueno"
    elif puntaje >= 60:
        etiqueta = "Atención"
    else:
        etiqueta = "Crítico"

    pkg = resultado.get("package") or ""
    if pkg == "full-scan":
        alcance = "Puntaje de salud del equipo"
    else:
        label = resultado.get("package_label") or pkg or "análisis"
        alcance = f"Puntaje del paquete {label}"

    conteo_cat = {"ok": 0, "advertencia": 0, "error": 0, "no_evaluado": 0}
    for r in collectors:
        st = _status(r)
        if st in _ESTADOS_DENEGADO:
            conteo_cat["no_evaluado"] += 1
            continue
        if st in _ESTADOS_ERROR:
            conteo_cat["error"] += 1
            continue
        rango = severidad_por_collector.get(r.get("collector_id"), 0)
        if rango >= 2:
            conteo_cat["error"] += 1
        elif rango == 1:
            conteo_cat["advertencia"] += 1
        else:
            conteo_cat["ok"] += 1

    categorias = []
    if ejecutados:
        categorias.append({
            "paquete": resultado.get("package_label") or pkg or "",
            **conteo_cat,
        })

    medidores = {}
    for r in collectors:
        if _status(r) != "ok":
            continue
        cid = r.get("collector_id")
        if cid == "memory_status":
            d = _primer_dict(r.get("data"))
            if d and d.get("physical_memory_usage_percent") is not None:
                medidores["memoria"] = {
                    "usado_porcentaje": d.get("physical_memory_usage_percent"),
                    "total_kb": d.get("total_visible_memory_kb"),
                    "libre_kb": d.get("free_physical_memory_kb"),
                }
        elif cid == "logical_disks":
            discos = []
            for x in (r.get("data") or []):
                if isinstance(x, dict) and x.get("used_percent") is not None:
                    discos.append({
                        "unidad": x.get("device_id"),
                        "usado_porcentaje": x.get("used_percent"),
                        "libre_gb": x.get("free_gb"),
                        "total_gb": x.get("total_gb"),
                    })
            if discos:
                medidores["discos"] = discos

    metricas = {
        "version_formula": VERSION_FORMULA,
        "puntaje": puntaje,
        "etiqueta": etiqueta,
        "alcance": alcance,
        "leyenda": LEYENDA_PUNTAJE,
        "cobertura": {
            "modulos_ejecutados": modulos,
            "colectores_ejecutados": ejecutados,
            "colectores_ok": ok,
            "colectores_vacios": vacios,
            "con_error": con_error,
            "denegados": denegados,
            "no_evaluados": no_evaluados,
            "porcentaje": porcentaje,
        },
        "severidad": conteos,
        "categorias": categorias,
    }
    if medidores:
        metricas["medidores"] = medidores
    return metricas


def _puntaje_de_entrada(entrada: dict):
    p = entrada.get("puntaje")
    if isinstance(p, int):
        return p
    if entrada.get("findings"):
        return calcular_metricas({
            "package": entrada.get("paquete"),
            "package_label": entrada.get("paquete_label"),
            "colectores": entrada.get("colectores"),
            "findings": entrada.get("findings"),
            "modulos_ejecutados": 1,
        }).get("puntaje")
    return None


def tendencia(entradas_registro: list) -> list[dict]:
    """Serie ``{fecha, puntaje}`` de los ultimos 10 analisis del registro.

    Solo se usan entradas del MISMO ``tipo`` y ``paquete`` que la ultima
    (nunca se mezcla un paquete con una revision total).
    """
    entradas = [e for e in (entradas_registro or []) if isinstance(e, dict)]
    if not entradas:
        return []
    ult = entradas[0]
    tipo = ult.get("tipo")
    paquete = ult.get("paquete")
    puntos = []
    for e in entradas:
        if e.get("tipo") != tipo or e.get("paquete") != paquete:
            continue
        p = _puntaje_de_entrada(e)
        if p is None:
            continue
        puntos.append({"fecha": e.get("fecha") or "", "puntaje": p})
    puntos.sort(key=lambda x: x["fecha"])
    return puntos[-10:]
