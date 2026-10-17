#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Servidor web interactivo para DiagUSB."""

import http.server
import json
import re
import secrets
import socket
import socketserver
import sys
import threading
import uuid
import webbrowser
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Agregar src al path (padre de diagusb/)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from diagusb.core.registry import discover_packages
from diagusb.core.models import CollectorResult, QueryInfo, Snapshot, ComputerId
from diagusb.core.comparator import compare_snapshots
from diagusb.core import almacen
from diagusb.core import integridad
from diagusb.core import rutas
from diagusb.core.rules import diagnose_symptoms
from diagusb.core.metricas import calcular_metricas, tendencia
from diagusb.core import knowledge_base as kb
from diagusb.core.informe import (
    ESTADOS_ACCION,
    _limitado_de,
    informe_a_doc,
    informe_a_pdf,
    informe_desde_diagnostico,
    mejoras_sugeridas,
    soluciones_para,
)

_REPO_ROOT = rutas.dir_base()
DIR_BASE = _REPO_ROOT
BASELINE_PATH = rutas.dir_reports() / "snapshot_antes.json"
REGISTRO_PATH = rutas.dir_config() / "registro_analisis.json"
BIND_HOST = "127.0.0.1"
MAX_CUERPO = 10 * 1024 * 1024
_SESSION_TOKEN = None


def _token_sesion() -> str:
    """Token de sesion (se genera una vez por proceso)."""
    global _SESSION_TOKEN
    if _SESSION_TOKEN is None:
        _SESSION_TOKEN = secrets.token_urlsafe(32)
    return _SESSION_TOKEN


def _paquete_seguro(package) -> str:
    """Nombre de paquete apto para usar en un archivo (solo [A-Za-z0-9_-])."""
    texto = "" if package is None else str(package)
    limpio = "".join(c for c in texto
                     if c.isascii() and (c.isalnum() or c in "_-"))
    return limpio or "equipo"


_ID_REGISTRO = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")


def _id_registro_valido(valor) -> bool:
    return bool(valor) and _ID_REGISTRO.match(str(valor)) is not None


REGISTRO_MAX = 200
_REGISTRO_LOCK = threading.Lock()


def _is_elevated() -> bool | None:
    """Indica si el proceso (y por lo tanto los colectores) corre como Administrador."""
    try:
        from .core.elevation import is_elevado
        return is_elevado()
    except Exception:
        return None


def _observations_from_results(results: list) -> list[CollectorResult]:
    """Convierte los results planos de un diagnostico en CollectorResult."""
    observations: list[CollectorResult] = []
    for r in results:
        if isinstance(r, dict) and r.get("collector_id"):
            q = r.get("query", {}) or {}
            observations.append(CollectorResult(
                collector_id=r["collector_id"],
                data=r.get("data", {}),
                query=QueryInfo(
                    status=q.get("status", "unknown"),
                    duration_ms=q.get("duration_ms", 0),
                    timeout_seconds=q.get("timeout_seconds", 15),
                ),
            ))
    return observations


def _metricas_de_results(results: list, package: str, package_label: str) -> dict:
    """Metricas de un lado de la comparacion re-evaluando las reglas.

    El snapshot guarda ``results`` (``collector_id`` + ``data``), que es la
    misma entrada que leen las reglas: se reconstruyen las observaciones y se
    evaluan con funciones puras.
    """
    symptoms: list[str] = []
    for p in discover_packages():
        symptoms.extend(p.symptoms)
    findings, _ = diagnose_symptoms(list(dict.fromkeys(symptoms)),
                                     _observations_from_results(results))
    return calcular_metricas({
        "package": package or "",
        "package_label": package_label or package or "",
        "results": results,
        "findings": [asdict(f) for f in findings],
        "modulos_ejecutados": 1,
    })


def _metricas_de_full_scan(diagnostics: list) -> dict:
    """Metricas combinadas de una revision total (un modulo por paquete)."""
    combinado = {
        "package": "full-scan",
        "package_label": "Revisión Total",
        "results": [r for d in diagnostics for r in (d.get("results") or [])],
        "findings": [f for d in diagnostics for f in (d.get("findings") or [])],
    }
    metricas = calcular_metricas(combinado, modulos=len(diagnostics))
    categorias = []
    for d in diagnostics:
        categorias.extend(calcular_metricas(d).get("categorias") or [])
    metricas["categorias"] = categorias
    return metricas


def _snapshot_from_results(results: list) -> Snapshot:
    """Snapshot minimo (solo collector_id/data) apto para compare_snapshots."""
    return Snapshot(
        computer_id=ComputerId(),
        captured_at_utc=datetime.now().isoformat(),
        observations=_observations_from_results(results),
    )


_CLAVES_IDENTIDAD = ("smbios_uuid", "uuid", "bios_serial", "machine_guid",
                     "serial_number")


def _buscar_identificador(datos):
    """Primer valor de identidad (UUID/serial) hallado en los datos."""
    cola = [datos]
    vistos = 0
    while cola and vistos < 500:
        actual = cola.pop(0)
        vistos += 1
        if isinstance(actual, dict):
            for clave in _CLAVES_IDENTIDAD:
                valor = actual.get(clave)
                if isinstance(valor, str) and valor.strip():
                    return valor.strip()
            cola.extend(actual.values())
        elif isinstance(actual, list):
            cola.extend(actual)
    return ""


def _identidad_equipo(results) -> dict:
    """Identidad visible del equipo: nombre y UUID/serial si estan disponibles."""
    nombre = ""
    ident = ""
    for r in results or []:
        if not isinstance(r, dict):
            continue
        ctx = r.get("context") or {}
        if not nombre and str(ctx.get("computer_name") or "").strip():
            nombre = str(ctx["computer_name"]).strip()
        if not ident:
            ident = _buscar_identificador(r.get("data"))
    return {"computer_name": nombre, "hardware_id": ident}


def _identidad_coincide(base: dict, actual: dict) -> bool:
    """True si no se puede probar que los equipos sean distintos."""
    for clave in ("computer_name", "hardware_id"):
        a = str(base.get(clave) or "").strip().lower()
        b = str(actual.get(clave) or "").strip().lower()
        if a and b and a != b:
            return False
    return True


def _parse_json_output(output: str):
    """Extrae el primer JSON valido (objeto o array) de la salida de PowerShell."""
    output = output.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        pass
    # PowerShell puede emitir warnings/errores antes del JSON: buscar el bloque
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = output.find(start_char)
        if start == -1:
            continue
        end = output.rfind(end_char)
        if end > start:
            try:
                return json.loads(output[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _matar_arbol_procesos(proc) -> None:
    """Termina el proceso y todo su arbol de hijos (taskkill /T /F).

    Necesario porque al vencer el timeout hay que cerrar tambien los nietos:
    si un hijo heredo el pipe de stdout, ``communicate`` seguiria bloqueado.
    """
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.kill()
    except Exception:
        pass


def run_powershell(script_path: str, timeout: int = 30) -> dict:
    """Ejecuta un script PowerShell y devuelve el resultado JSON.

    Al vencer ``timeout`` termina el arbol de procesos completo para que la
    duracion real no supere el limite aunque el script haya lanzado hijos.
    """
    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        return {"query": {"status": "error", "message": str(e)}, "data": {}}

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _matar_arbol_procesos(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return {"query": {"status": "timeout", "message": f"Timeout de {timeout}s"},
                "data": {}}
    except Exception as e:
        _matar_arbol_procesos(proc)
        return {"query": {"status": "error", "message": str(e)}, "data": {}}

    data = _parse_json_output(stdout)
    if data is not None:
        return data
    detail = (stderr or "").strip().splitlines()
    message = detail[-1] if detail else "Sin salida"
    return {"query": {"status": "error", "message": message}, "data": {}}


def _normalize_results(raw) -> list[dict]:
    """Normaliza la salida de un colector a una lista de resultados planos."""
    items = raw if isinstance(raw, list) else [raw]
    normalized = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"query": {"status": "error", "message": "Resultado no valido"}, "data": {}})
    return normalized


def run_diagnostic(package_name: str, symptom: str = None) -> dict:
    """Ejecuta un diagnostico completo para un paquete."""
    packages = discover_packages()

    pkg = next((p for p in packages if p.name == package_name), None)
    if not pkg:
        return {"error": f"Paquete '{package_name}' no encontrado"}
    results = []
    integridad_fallida = []

    # Ejecutar colectores
    collectors_dir = Path(__file__).parent / "packages" / package_name / "collectors"

    if collectors_dir.exists():
        for ps_file in sorted(collectors_dir.glob("*.ps1")):
            ok_firma, motivo = integridad.verificar(ps_file)
            if ok_firma:
                comun = integridad.localizar_common(ps_file)
                if comun is not None:
                    ok_firma, motivo = integridad.verificar(comun)
            if not ok_firma:
                integridad_fallida.append(ps_file.stem)
                results.append({
                    "collector_id": ps_file.stem,
                    "query": {"status": "error", "message": motivo, "duration_ms": 0},
                    "data": {},
                })
                continue
            raw = run_powershell(str(ps_file))
            results.extend(_normalize_results(raw))

    # Contar resultados
    def _status(r):
        return r.get("query", {}).get("status", "unknown") if isinstance(r, dict) else "error"

    ok = sum(1 for r in results if _status(r) == "ok")
    errors = sum(1 for r in results if _status(r) in ("error", "timeout", "not_available", "denied"))
    empty = sum(1 for r in results if _status(r) == "empty")

    is_elevated = None
    for r in results:
        ctx = r.get("context") if isinstance(r, dict) else None
        if isinstance(ctx, dict) and "is_elevated" in ctx:
            is_elevated = bool(ctx.get("is_elevated"))
            break

    if symptom is None:
        symptom = pkg.symptoms[0] if pkg.symptoms else "general"

    # Reglas de diagnostico sobre los resultados
    observations = _observations_from_results(results)

    findings, recommendations = diagnose_symptoms(list(pkg.symptoms), observations)
    findings_json = [
        {
            "severity": f.severity,
            "collector_id": f.collector_id,
            "message": f.message,
            "details": f.details,
            "knowledge": kb.knowledge_json(f),
            "solutions": kb.soluciones_de(f) or soluciones_para(f.collector_id, f.severity),
        }
        for f in findings
    ]

    salida = {
        "package": package_name,
        "package_label": pkg.label,
        "symptom": symptom,
        "collectors_count": len(results),
        "ok_count": ok,
        "error_count": errors,
        "empty_count": empty,
        "is_elevated": is_elevated,
        "results": results,
        "findings": findings_json,
        "improvements": mejoras_sugeridas(results),
        "integridad_fallida": integridad_fallida,
        "recommendations": recommendations,
        "estados_accion": ESTADOS_ACCION,
        "timestamp": datetime.now().isoformat()
    }
    salida["metricas"] = calcular_metricas(salida, modulos=1)
    return salida


# ---------------------------------------------------------------------------
# Registro persistente de análisis (config/registro_analisis.json)
# ---------------------------------------------------------------------------

def _cargar_registro() -> list[dict]:
    """Carga el registro persistente de análisis; lista vacía si no existe."""
    data = almacen.leer_json(REGISTRO_PATH, preservar=True)
    return data if isinstance(data, list) else []


def _guardar_registro(entradas: list[dict]) -> None:
    """Escribe el registro completo en disco (llamar con _REGISTRO_LOCK tomado)."""
    almacen.escribir_json_atomico(REGISTRO_PATH, entradas, indent=1)


def _entrada_registro(diag: dict, tipo: str) -> dict:
    """Construye una entrada compacta del registro para un diagnostico."""
    results = [r for r in (diag.get("results") or []) if isinstance(r, dict)]
    findings = diag.get("findings") or []
    modo = "administrador" if diag.get("is_elevated") else "estándar"
    no_eval = [r.get("collector_id") or "" for r in results
               if (r.get("query") or {}).get("status") in
               ("denied", "not_available", "error", "timeout")]
    limitados = []
    for r in results:
        cid = r.get("collector_id") or ""
        motivo = _limitado_de(cid, r.get("data"),
                              (r.get("query") or {}).get("status", ""))
        if motivo:
            limitados.append(f"{cid} ({motivo})")
    alcance = (f"Alcance: modo {modo}; no evaluados: "
               + (", ".join([x for x in no_eval if x]) or "ninguno"))
    if limitados:
        alcance += "; datos limitados: " + ", ".join(limitados)
    metricas = calcular_metricas({
        "package": diag.get("package") or "",
        "package_label": diag.get("package_label") or "",
        "results": results,
        "findings": findings,
        "modulos_ejecutados": 1,
    })
    return {
        "id": f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}",
        "fecha": diag.get("timestamp") or datetime.now().isoformat(),
        "tipo": tipo,
        "paquete": diag.get("package") or "",
        "paquete_label": diag.get("package_label") or diag.get("package") or "",
        "sintoma": diag.get("symptom") or "",
        "puntaje": metricas["puntaje"],
        "alcance": alcance,
        "conteos": {
            "collectors": diag.get("collectors_count") or len(results),
            "ok": diag.get("ok_count") or 0,
            "error": diag.get("error_count") or 0,
            "empty": diag.get("empty_count") or 0,
            "findings": len(findings),
        },
        "findings": findings,
        "recommendations": diag.get("recommendations") or [],
        "colectores": [
            {
                "id": r.get("collector_id") or "",
                "status": (r.get("query") or {}).get("status", "unknown"),
                "duration_ms": (r.get("query") or {}).get("duration_ms", 0),
            }
            for r in results
        ],
    }


def registrar_analisis(diag: dict, tipo: str) -> dict | None:
    """Guarda un diagnostico en el registro persistente (mas reciente primero).

    Devuelve la entrada guardada o None si no hay nada que guardar.
    """
    if not isinstance(diag, dict) or diag.get("error"):
        return None
    entrada = _entrada_registro(diag, tipo)
    with _REGISTRO_LOCK:
        entradas = _cargar_registro()
        entradas.insert(0, entrada)
        del entradas[REGISTRO_MAX:]
        _guardar_registro(entradas)
    return entrada


def _registrar_full_scan(diagnostics: list[dict]) -> dict | None:
    """Guarda una revision total (todos los paquetes) como una sola entrada."""
    validos = [d for d in diagnostics
               if isinstance(d, dict) and not d.get("error")]
    if not validos:
        return None
    findings = []
    for d in validos:
        for f in d.get("findings") or []:
            c = dict(f)
            c["package_label"] = d.get("package_label") or d.get("package") or ""
            findings.append(c)
    diag = {
        "package": "full-scan",
        "package_label": "Revisión Total",
        "symptom": "revision_total",
        "collectors_count": sum(d.get("collectors_count") or 0 for d in validos),
        "ok_count": sum(d.get("ok_count") or 0 for d in validos),
        "error_count": sum(d.get("error_count") or 0 for d in validos),
        "empty_count": sum(d.get("empty_count") or 0 for d in validos),
        "findings": findings,
        "recommendations": list(dict.fromkeys(
            r for d in validos for r in d.get("recommendations") or [])),
        "results": [r for d in validos for r in d.get("results") or []],
        "timestamp": datetime.now().isoformat(),
    }
    return registrar_analisis(diag, "full-scan")


def eliminar_analisis(registro_id: str) -> bool:
    """Elimina un analisis del registro por id. Devuelve True si existia."""
    with _REGISTRO_LOCK:
        entradas = _cargar_registro()
        nueva = [e for e in entradas if e.get("id") != registro_id]
        if len(nueva) == len(entradas):
            return False
        _guardar_registro(nueva)
        return True


def vaciar_registro() -> int:
    """Elimina todos los analisis del registro. Devuelve cuantos habia."""
    with _REGISTRO_LOCK:
        entradas = _cargar_registro()
        _guardar_registro([])
        return len(entradas)


_STATIC_DIR = Path(__file__).with_name("static")
_PAGINA_CACHE = None


def _cargar_pagina() -> str:
    """Ensambla la pagina servida en ``/`` desde los archivos de static/.

    ``index.html``, ``app.css`` y ``app.js`` se leen una sola vez y se
    combinan reemplazando sus marcadores.
    """
    global _PAGINA_CACHE
    if _PAGINA_CACHE is None:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        css = (_STATIC_DIR / "app.css").read_text(encoding="utf-8")
        js = (_STATIC_DIR / "app.js").read_text(encoding="utf-8")
        _PAGINA_CACHE = (html.replace("@@DIAGUSB_CSS@@", css)
                             .replace("@@DIAGUSB_JS@@", js))
    return _PAGINA_CACHE


def _puerto_libre(desde: int) -> int | None:
    """Primer puerto local libre a partir de ``desde`` + 1."""
    for puerto in range(int(desde) + 1, int(desde) + 60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((BIND_HOST, puerto))
            return puerto
        except OSError:
            continue
        finally:
            s.close()
    return None


def _comando_web_elevado(puerto: int) -> list:
    """Linea de comandos para relanzar el servidor web elevado en ``puerto``."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "web", "--port", str(puerto)]
    return [sys.executable, "-B", "-m", "diagusb", "web", "--port", str(puerto)]


class DiagUSBHandler(http.server.BaseHTTPRequestHandler):
    """Handler para DiagUSB web (sin herencia de servidor de archivos)."""
    
    def _host_valido(self):
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        if host.startswith("["):
            nombre = host.split("]")[0] + "]"
        else:
            nombre = host.split(":")[0]
        return nombre in ("127.0.0.1", "localhost", "[::1]")

    def _origen_valido(self):
        origen = self.headers.get("Origin")
        if not origen:
            return True
        origen = origen.strip().lower()
        if origen == "null":
            return False
        try:
            host = urlparse(origen).hostname
        except ValueError:
            return False
        return host in ("127.0.0.1", "localhost", "::1")

    def _validar_solicitud(self):
        if self._host_valido() and self._origen_valido():
            return True
        self.send_error(403, "Origen no permitido")
        return False

    def _token_recibido(self):
        params = parse_qs(urlparse(self.path).query)
        if params.get("t"):
            return params["t"][0]
        for parte in self.headers.get("Cookie", "").split(";"):
            clave, _, valor = parte.strip().partition("=")
            if clave == "diagusb_token":
                return valor
        return None

    def _token_valido(self):
        return secrets.compare_digest(self._token_recibido() or "", _token_sesion())

    def _servir_index(self):
        body = _cargar_pagina().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirigir_con_cookie(self):
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie",
                         f"diagusb_token={_token_sesion()}; "
                         "HttpOnly; SameSite=Strict; Path=/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _pagina_sin_token(self):
        body = (
            '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">'
            "<title>DiagUSB</title></head>"
            '<body style="font-family:system-ui,sans-serif;padding:2rem">'
            "<h1>Acceso restringido</h1>"
            "<p>Abra la URL con el token de sesion que muestra la consola de "
            "DiagUSB.</p></body></html>"
        ).encode("utf-8")
        self.send_response(403)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Maneja GET requests."""
        try:
            if not self._validar_solicitud():
                return
            parsed = urlparse(self.path)
            if parsed.path == "/":
                if not self._token_valido():
                    self._pagina_sin_token()
                elif parse_qs(parsed.query).get("t"):
                    self._redirigir_con_cookie()
                else:
                    self._servir_index()
                return
            if parsed.path.startswith("/api/") and not self._token_valido():
                self._json_response({"error": "No autorizado"}, 401)
                return
            self._handle_get()
        except Exception as e:
            try:
                body = json.dumps({"error": f"Error interno: {e}"}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

    def _handle_get(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/api/diagnose":
            # API para diagnostico individual
            params = parse_qs(parsed.query)
            package = params.get("package", [None])[0]
            
            result = run_diagnostic(package) if package else {"error": "Package required"}
            if not result.get("error"):
                entrada = registrar_analisis(result, "paquete")
                if entrada:
                    result["registro_id"] = entrada["id"]
            
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            
        elif parsed.path == "/api/knowledge":
            # Base de conocimiento local (estado esperado + soluciones)
            result = {
                "version": kb.version(),
                "entradas": kb.entradas(),
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

        elif parsed.path == "/api/elevation":
            # Indica si los colectores corren con permisos de Administrador
            result = {"is_elevated": _is_elevated(),
                      "respaldo": rutas.usa_respaldo(),
                      "ruta_base": str(rutas.dir_base())}

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

        elif parsed.path == "/api/registro":
            # Registro persistente de analisis (lista o detalle por id)
            params = parse_qs(parsed.query)
            registro_id = params.get("id", [None])[0]
            entradas = _cargar_registro()
            if registro_id:
                if not _id_registro_valido(registro_id):
                    self._json_response({"error": "Id invalido"}, 400)
                    return
                entrada = next((e for e in entradas
                                if e.get("id") == registro_id), None)
                if entrada:
                    self._json_response(entrada)
                else:
                    self._json_response({"error": "Análisis no encontrado"}, 404)
            else:
                resumen = [
                    {k: e.get(k) for k in ("id", "fecha", "tipo", "paquete",
                                           "paquete_label", "sintoma", "puntaje",
                                           "conteos")}
                    for e in entradas
                ]
                self._json_response({"total": len(entradas), "entradas": resumen})

        elif parsed.path == "/api/full-scan":
            # API para diagnostico completo (paquetes en paralelo)
            packages = discover_packages()
            
            with ThreadPoolExecutor(max_workers=4) as pool:
                diagnostics = list(pool.map(lambda p: run_diagnostic(p.name), packages))
            
            result = {"diagnostics": diagnostics, "timestamp": datetime.now().isoformat()}
            result["metricas"] = _metricas_de_full_scan(diagnostics)
            entrada = _registrar_full_scan(diagnostics)
            if entrada:
                result["registro_id"] = entrada["id"]
            
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            
        else:
            self.send_error(404, "No encontrado")
    
    def do_POST(self):
        """APIs POST: informes, snapshot, comparacion y base de conocimiento."""
        if not self._validar_solicitud():
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.send_error(415, "Content-Type debe ser application/json")
            return
        if not self._token_valido():
            self._json_response({"error": "No autorizado"}, 401)
            return
        try:
            largo = int(self.headers.get("Content-Length", ""))
        except (TypeError, ValueError):
            self.send_error(400, "Content-Length requerido o invalido")
            return
        if largo < 0:
            self.send_error(400, "Content-Length invalido")
            return
        if largo > MAX_CUERPO:
            self.send_error(413, "Cuerpo demasiado grande")
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/report":
            self._post_report()
        elif parsed.path == "/api/snapshot":
            self._post_snapshot()
        elif parsed.path == "/api/compare":
            self._post_compare()
        elif parsed.path == "/api/knowledge":
            self._post_knowledge()
        elif parsed.path == "/api/elevar":
            self._post_elevar()
        else:
            self.send_error(404, "Not found")

    def do_DELETE(self):
        """APIs DELETE: borrado del registro de analisis."""
        try:
            if not self._validar_solicitud():
                return
            if not self._token_valido():
                self._json_response({"error": "No autorizado"}, 401)
                return
            self._handle_delete()
        except Exception as e:
            try:
                self._json_response({"error": f"Error interno: {e}"}, 500)
            except Exception:
                pass

    def _handle_delete(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/registro":
            self._json_response({"error": "Not found"}, 404)
            return
        params = parse_qs(parsed.query)
        registro_id = params.get("id", [None])[0]
        if registro_id:
            if not _id_registro_valido(registro_id):
                self._json_response({"error": "Id invalido"}, 400)
                return
            ok = eliminar_analisis(registro_id)
            if ok:
                self._json_response({"ok": True, "eliminado": registro_id})
            else:
                self._json_response({"error": "Análisis no encontrado"}, 404)
        else:
            n = vaciar_registro()
            self._json_response({"ok": True, "eliminados": n})

    def _json_response(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            data = json.loads(raw.decode("cp1252", errors="replace"))
        return data if isinstance(data, dict) else {}

    def _post_snapshot(self):
        """Guarda el estado 'antes' a partir de los results de un diagnostico."""
        try:
            payload = self._read_payload()
            results = payload.get("results") or []
            ident = _identidad_equipo(results)
            doc = {
                "captured_at": datetime.now().isoformat(),
                "computer_name": ident["computer_name"],
                "hardware_id": ident["hardware_id"],
                "results": results,
            }
            almacen.escribir_json_atomico(BASELINE_PATH, doc, indent=1)
            self._json_response({"ok": True, "guardado_en": str(BASELINE_PATH),
                                 "collectors": len(results),
                                 "computer_name": ident["computer_name"],
                                 "captured_at": doc["captured_at"]})
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _post_compare(self):
        """Compara el estado actual contra el snapshot 'antes' guardado."""
        try:
            if not BASELINE_PATH.exists():
                self._json_response(
                    {"error": "No hay snapshot 'antes' guardado. Use el boton Guardar ANTES."},
                    404)
                return
            payload = self._read_payload()
            base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            ident_base = {
                "computer_name": base.get("computer_name") or "",
                "hardware_id": base.get("hardware_id") or "",
            }
            ident_actual = _identidad_equipo(payload.get("results") or [])
            tiene_identidad = bool(ident_base["computer_name"] or ident_base["hardware_id"])
            equipos_distintos = False
            advertencia = ""
            if tiene_identidad and not _identidad_coincide(ident_base, ident_actual):
                if not payload.get("forzar"):
                    nombre_guardado = ident_base["computer_name"] or "(sin nombre)"
                    nombre_actual = ident_actual["computer_name"] or "(sin nombre)"
                    self._json_response({
                        "error": (f"El snapshot ANTES pertenece a otro equipo "
                                  f"(guardado: '{nombre_guardado}', actual: "
                                  f"'{nombre_actual}'). Confirme para comparar de "
                                  f"todos modos."),
                        "requiere_confirmacion": True,
                        "equipo_guardado": nombre_guardado,
                        "equipo_actual": nombre_actual,
                    }, 409)
                    return
                equipos_distintos = True
            elif not tiene_identidad:
                advertencia = ("El snapshot ANTES no tiene identidad de equipo; se "
                               "compara sin poder verificarla.")
            diffs = compare_snapshots(
                _snapshot_from_results(base.get("results") or []),
                _snapshot_from_results(payload.get("results") or []),
            )
            self._json_response({
                "ok": True,
                "baseline_en": base.get("captured_at"),
                "equipos_distintos": equipos_distintos,
                "advertencia": advertencia,
                "diferencias": [asdict(d) for d in diffs],
                "metricas_base": _metricas_de_results(
                    base.get("results") or [],
                    payload.get("package") or "",
                    payload.get("package_label") or ""),
                "metricas_actual": _metricas_de_results(
                    payload.get("results") or [],
                    payload.get("package") or "",
                    payload.get("package_label") or ""),
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 400)

    def _post_knowledge(self):
        """Guarda o elimina entradas de la base de conocimiento (capa local)."""
        try:
            payload = self._read_payload()
            accion = payload.get("accion") or "guardar"
            if accion == "eliminar":
                ok = kb.eliminar_entrada(str(payload.get("id") or ""))
                if not ok:
                    self._json_response({"error": "Entrada no encontrada"}, 404)
                    return
            else:
                kb.guardar_entrada(payload.get("entrada") or {})
            self._json_response({"ok": True, "version": kb.version(),
                                 "entradas": kb.entradas()})
        except ValueError as e:
            self._json_response({"error": str(e)}, 400)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _post_elevar(self):
        """Relanza el servidor elevado en un puerto nuevo y cierra este proceso."""
        from .core.elevation import elevar_servidor
        if _is_elevated() is True:
            self._json_response({"ok": False,
                                 "mensaje": "El proceso ya tiene permisos de administrador."})
            return
        base = getattr(self.server, "diagusb_port", None) or 8080
        nuevo = _puerto_libre(base)
        if nuevo is None:
            self._json_response(
                {"ok": False,
                 "error": "No se encontró un puerto libre para el proceso elevado."}, 500)
            return
        linea = _comando_web_elevado(nuevo)
        if elevar_servidor(linea, nuevo):
            self._json_response({
                "ok": True, "puerto": nuevo,
                "mensaje": (f"Permisos otorgados. Se abrió otra pestaña en el puerto "
                            f"{nuevo}; esta ventana se cerrará.")})
            threading.Timer(1.5, self._apagar_servidor).start()
        else:
            self._json_response(
                {"ok": False,
                 "error": ("No se otorgaron los permisos de administrador "
                           "(el diálogo UAC se canceló).")})

    def _apagar_servidor(self):
        """Detiene serve_forever para que el proceso original termine."""
        try:
            self.server.shutdown()
        except Exception:
            pass

    def _post_report(self):
        params = parse_qs(urlparse(self.path).query)
        fmt = params.get("format", ["pdf"])[0].lower()

        try:
            payload = self._read_payload()
            diag = payload.get("diagnostico") or {}
            if not diag.get("package"):
                raise ValueError("Falta el diagnostico")

            informe = informe_desde_diagnostico(
                diag,
                acciones=payload.get("acciones"),
                mejoras_acciones=payload.get("mejoras"),
                tecnico=payload.get("tecnico", ""),
                cliente=payload.get("cliente", ""),
                observaciones=payload.get("observaciones", ""),
                diferencias=payload.get("diferencias"),
                comparacion_forzada=bool(payload.get("comparacion_forzada")),
            )
            paquete = _paquete_seguro(diag["package"])

            if fmt == "doc":
                data = informe_a_doc(informe, resultados_completos=diag.get("results"))
                content_type = "application/msword"
                filename = f"informe_{paquete}_{datetime.now():%Y%m%d_%H%M%S}.doc"
            else:
                data = informe_a_pdf(informe)
                content_type = "application/pdf"
                filename = f"informe_{paquete}_{datetime.now():%Y%m%d_%H%M%S}.pdf"

            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            body = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args):
        mensaje = str(args[0]) if args else ""
        if "t=" in mensaje:
            antes, _, resto = mensaje.partition("t=")
            fin = len(resto)
            for sep in ("&", " ", ";"):
                p = resto.find(sep)
                if p != -1:
                    fin = min(fin, p)
            mensaje = antes + "t=[oculto]" + resto[fin:]
        print(f"[DiagUSB] {mensaje}")


def run_server(port: int = 8080, elevar: bool = False,
               comando: list | None = None):
    """Ejecuta el servidor web (sin elevacion salvo que se pida con elevar=True)."""

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
    except (AttributeError, ValueError):
        pass

    from .core.elevation import (comando_relanzable, desactivada,
                                 elevar_servidor, is_elevado, puerto_en_uso)

    if puerto_en_uso(port):
        print(f"Error: ya hay algo escuchando en el puerto {port}.")
        print("Si es una instancia anterior de DiagUSB, cierre su ventana de consola "
              "e intente de nuevo.")
        sys.exit(1)

    if elevar:
        if not desactivada() and not is_elevado():
            linea = comando or comando_relanzable("diagusb.web_server")
            print("Solicitando permisos de Administrador (acepte el dialogo de Windows)...")
            if elevar_servidor(linea, port):
                print("DiagUSB se reinicio como Administrador.")
                sys.exit(0)
            print("Aviso: no se obtuvieron permisos de Administrador (dialogo UAC "
                  "rechazado).")
            print("         El servidor continuara con permisos limitados: algunos "
                  "colectores mostraran")
            print("         datos parciales o 'denied'. Reinicie y acepte el dialogo "
                  "para un diagnostico completo.\n")

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        httpd = ThreadedTCPServer((BIND_HOST, port), DiagUSBHandler)
    except OSError:
        print(f"Error: no se pudo abrir el puerto {port}.")
        print("¿Ya hay otra instancia de DiagUSB corriendo? Cierrela e intente de nuevo.")
        sys.exit(1)

    httpd.diagusb_port = port

    with httpd:
        url = f"http://localhost:{port}/?t={_token_sesion()}"
        print(f"""
+===========================================================+
|  DiagUSB - Servidor Web Interactivo                       |
|                                                           |
|  Abriendo el navegador con el token de sesion.            |
|                                                           |
|  Si no abre solo, copie esta URL exacta:                  |
|  {url}
|                                                           |
|  Presiona Ctrl+C para detener                             |
+===========================================================+
        """, flush=True)
        
        webbrowser.open(url)
        httpd.serve_forever()


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    
    try:
        run_server(port)
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        sys.exit(0)
