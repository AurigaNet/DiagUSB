# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Metricas de salud de DiagUSB: funciones puras, sin I/O.

El puntaje es ORIENTATIVO y se calcula solo sobre los hallazgos reales del
analisis ejecutado. No reemplaza al diagnostico ni inventa datos: si no hay
modulos ejecutados no hay puntaje (``None`` / "Sin datos").
"""

VERSION_FORMULA = 2

PESOS = {"critical": 15, "error": 8, "warning": 3, "ok": 0}
LABEL_SEVERIDAD = {"critical": "Crítico", "error": "Error",
                   "warning": "Advertencia", "ok": "OK"}
LEYENDA_PUNTAJE = "Puntaje orientativo sobre los módulos ejecutados"

_COBERTURA_PARCIAL = 60.0

# Definicion UNICA de estados de colector. Todo el documento y la interfaz
# derivan de esta misma clasificacion (nunca de dos criterios distintos).
ESTADOS = ("ok", "sin_datos", "error", "timeout", "denegado", "no_disponible")
ESTADO_LABEL = {
    "ok": "OK", "sin_datos": "Sin datos", "error": "Error",
    "timeout": "Tiempo agotado", "denegado": "Denegado",
    "no_disponible": "No disponible",
}
_ESTADO_POR_STATUS = {
    "ok": "ok", "empty": "sin_datos", "error": "error", "timeout": "timeout",
    "denied": "denegado", "not_available": "no_disponible",
}

# Umbrales de los medidores (porcentaje de uso). "verde" por debajo del umbral
# verde, "ambar" hasta el umbral ambar (inclusive) y "rojo" por encima.
UMBRALES = {
    "discos": {"verde": 75, "ambar": 90},
    "memoria": {"verde": 80, "ambar": 90},
}
LEYENDA_UMBRALES = ("Discos: verde < 75%, ámbar 75-89%, rojo >= 90%. "
                    "Memoria: verde < 80%, ámbar 80-89%, rojo >= 90%.")


def estado_de(status: str) -> str:
    """Normaliza el status crudo de un colector a uno de ``ESTADOS``."""
    return _ESTADO_POR_STATUS.get((status or "").lower(), "no_disponible")


def nivel_medidor(tipo: str, pct) -> str:
    """Nivel ('verde' / 'ambar' / 'rojo') de un medidor segun su umbral."""
    u = UMBRALES.get(tipo, {"verde": 75, "ambar": 90})
    try:
        valor = float(pct)
    except (TypeError, ValueError):
        return "verde"
    if valor >= u["ambar"]:
        return "rojo"
    if valor >= u["verde"]:
        return "ambar"
    return "verde"


def recomendaciones_de(conteos: dict) -> list[str]:
    """Recomendaciones derivadas de los conteos de severidad del analisis.

    Una sola definicion: mientras exista algun problema (critical/error/
    warning) nunca se emite "No se detectaron problemas obvios.".
    """
    c = conteos or {}
    criticos = int(c.get("critical") or 0)
    errores = int(c.get("error") or 0)
    advertencias = int(c.get("warning") or 0)
    if criticos == 0 and errores == 0 and advertencias == 0:
        return ["No se detectaron problemas obvios."]
    recs = []
    if criticos > 0:
        recs.append("Problema crítico detectado. Requiere atención inmediata.")
    if errores > 0:
        recs.append("Errores detectados. Revise la configuración.")
    if advertencias > 0:
        recs.append("Advertencias detectadas. Monitoree la situación.")
    return recs


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


def _categorias(collectors: list, findings: list, paquetes: list | None,
                default_id: str, default_label: str) -> list[dict]:
    """Filas por paquete con la definicion UNICA de estados y sus hallazgos.

    ``paquetes`` (opcional) es una lista de ``{"id", "label", "collectors"}``
    con los ids de colector de cada paquete (el mapa real de paquetes). Si no
    se informa, se genera una sola fila con la etiqueta del analisis.
    """
    filas: list[dict] = []
    mapa: dict[str, dict] = {}
    defecto: dict | None = None

    def _nueva(pid: str, label: str) -> dict:
        fila = {
            "paquete": label or pid or "", "paquete_id": pid or "",
            "ok": 0, "sin_datos": 0, "error": 0, "timeout": 0,
            "denegado": 0, "no_disponible": 0,
            "hallazgos": {"critical": 0, "error": 0, "warning": 0},
        }
        filas.append(fila)
        return fila

    if paquetes:
        for p in paquetes:
            if not isinstance(p, dict):
                continue
            fila = _nueva(p.get("id"), p.get("label"))
            for cid in (p.get("collectors") or []):
                mapa[str(cid)] = fila
    else:
        defecto = _nueva(default_id, default_label)

    for r in collectors:
        fila = mapa.get(str(r.get("collector_id"))) or defecto
        if fila is None:
            continue
        fila[estado_de(_status(r))] += 1

    for f in findings:
        if _es_no_evaluado(f):
            continue
        sev = f.get("severity")
        if sev not in ("critical", "error", "warning"):
            continue
        fila = mapa.get(str(f.get("collector_id"))) or defecto
        if fila is None:
            continue
        fila["hallazgos"][sev] += 1

    for fila in filas:
        fila["total"] = sum(fila[e] for e in ESTADOS)
        fila["evaluados"] = fila["ok"] + fila["sin_datos"]
        fila["no_evaluado"] = (fila["timeout"] + fila["denegado"]
                               + fila["no_disponible"])
        fila["advertencia"] = fila["hallazgos"]["warning"]
    return filas


def calcular_metricas(resultado: dict, modulos: int | None = None) -> dict:
    """Calcula las metricas orientativas de un diagnostico (puro).

    ``resultado`` es el payload de un diagnostico (``/api/diagnose``, una
    entrada del registro o el combinado de una revision total) con al menos
    ``results``/``colectores`` y ``findings``. ``modulos`` permite informar
    cuantos modulos (paquetes) se ejecutaron cuando no se puede inferir.
    ``paquetes`` (opcional) permite agrupar las categorias por paquete real.
    """
    resultado = resultado or {}
    collectors = _collectors(resultado)
    ejecutados = len(collectors)

    # Definicion UNICA de estados: todo se deriva de aqui.
    estados = {e: 0 for e in ESTADOS}
    for r in collectors:
        estados[estado_de(_status(r))] += 1
    ok = estados["ok"]
    sin_datos = estados["sin_datos"]
    con_error = estados["error"] + estados["timeout"]
    denegados = estados["denegado"] + estados["no_disponible"]
    no_evaluados = con_error + denegados
    evaluados = ok + sin_datos
    porcentaje = round(evaluados / ejecutados * 100, 1) if ejecutados else 0.0

    if modulos is None:
        modulos = resultado.get("modulos_ejecutados")
        if not isinstance(modulos, int):
            modulos = 1 if ejecutados else 0

    findings = [f for f in (resultado.get("findings") or [])
                if isinstance(f, dict)]
    conteos = {"critical": 0, "error": 0, "warning": 0, "ok": 0}
    for f in findings:
        if _es_no_evaluado(f):
            continue
        sev = f.get("severity")
        if sev in conteos:
            conteos[sev] += 1

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

    categorias = []
    if ejecutados:
        categorias = _categorias(
            collectors, findings, resultado.get("paquetes"),
            pkg, resultado.get("package_label") or pkg or "")

    medidores = {}
    for r in collectors:
        if _status(r) != "ok":
            continue
        cid = r.get("collector_id")
        if cid == "memory_status":
            d = _primer_dict(r.get("data"))
            if d and d.get("physical_memory_usage_percent") is not None:
                pct = d.get("physical_memory_usage_percent")
                medidores["memoria"] = {
                    "usado_porcentaje": pct,
                    "total_kb": d.get("total_visible_memory_kb"),
                    "libre_kb": d.get("free_physical_memory_kb"),
                    "nivel": nivel_medidor("memoria", pct),
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
                        "nivel": nivel_medidor("discos", x.get("used_percent")),
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
            "colectores_sin_datos": sin_datos,
            "colectores_vacios": sin_datos,
            "colectores_evaluados": evaluados,
            "con_error": con_error,
            "denegados": denegados,
            "no_evaluados": no_evaluados,
            "porcentaje": porcentaje,
            "estados": dict(estados),
        },
        "estados": dict(estados),
        "severidad": conteos,
        "categorias": categorias,
        "umbrales": UMBRALES,
        "leyenda_medidores": LEYENDA_UMBRALES,
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
