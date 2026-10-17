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
from diagusb.core import knowledge_base as kb
from diagusb.core.informe import (
    ESTADOS_ACCION,
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


def run_powershell(script_path: str, timeout: int = 30) -> dict:
    """Ejecuta un script PowerShell y devuelve el resultado JSON."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        data = _parse_json_output(result.stdout)
        if data is not None:
            return data
        detail = (result.stderr or "").strip().splitlines()
        message = detail[-1] if detail else "Sin salida"
        return {"query": {"status": "error", "message": message}, "data": {}}
    except subprocess.TimeoutExpired:
        return {"query": {"status": "timeout", "message": f"Timeout de {timeout}s"}, "data": {}}
    except Exception as e:
        return {"query": {"status": "error", "message": str(e)}, "data": {}}


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

    return {
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
    return {
        "id": f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}",
        "fecha": diag.get("timestamp") or datetime.now().isoformat(),
        "tipo": tipo,
        "paquete": diag.get("package") or "",
        "paquete_label": diag.get("package_label") or diag.get("package") or "",
        "sintoma": diag.get("symptom") or "",
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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DiagUSB - Diagnóstico Interactivo</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container { max-width: 1400px; margin: 0 auto; }
        
        /* Header */
        .header {
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #0f3460, #1a1a2e);
            border-radius: 16px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        
        .header h1 {
            font-size: 36px;
            margin-bottom: 8px;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .header .subtitle { color: #888; font-size: 14px; }
        
        /* Buttons Grid */
        .buttons-section {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }
        
        .buttons-section h2 {
            font-size: 18px;
            margin-bottom: 16px;
            color: #00d9ff;
        }
        
        .btn-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 12px;
        }
        
        .btn {
            padding: 16px 20px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
        }
        
        .btn:hover:not(:disabled) {
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .btn-full {
            background: linear-gradient(135deg, #e94560, #c23a51);
            color: white;
            font-size: 16px;
            padding: 20px;
        }
        
        .btn-impresion { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
        .btn-redes { background: linear-gradient(135deg, #11998e, #38ef7d); color: white; }
        .btn-disco { background: linear-gradient(135deg, #fc4a1a, #f7b733); color: white; }
        .btn-memoria { background: linear-gradient(135deg, #8e2de2, #4a00e0); color: white; }
        .btn-servicios { background: linear-gradient(135deg, #00b4db, #0083b0); color: white; }
        .btn-seguridad { background: linear-gradient(135deg, #f093fb, #f5576c); color: white; }
        .btn-wifi { background: linear-gradient(135deg, #4facfe, #00f2fe); color: #1a1a2e; }
        .btn-windows { background: linear-gradient(135deg, #0f3460, #1a1a2e); color: white; border: 2px solid #00d9ff; }
        .btn-drivers { background: linear-gradient(135deg, #434343, #000000); color: white; }
        .btn-eventos { background: linear-gradient(135deg, #f85032, #e73827); color: white; }
        .btn-contexto { background: linear-gradient(135deg, #2c3e50, #3498db); color: white; }
        .btn-kb { background: linear-gradient(135deg, #232526, #414345); color: white; border: 2px solid #4facfe; }
        .btn-kb.btn-open { border-color: #00d9ff; box-shadow: 0 0 14px rgba(0,217,255,0.45); }
        .btn-registro { background: linear-gradient(135deg, #134e5e, #49a078); color: white; border: 2px solid #49a078; }
        .btn-registro.btn-open { border-color: #a0e8b8; box-shadow: 0 0 14px rgba(113,178,128,0.45); }
        
        .btn-icon { font-size: 24px; }
        .btn-label { font-size: 13px; }
        
        /* Results Section */
        .results-section {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
        }
        
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .results-header h2 { color: #00d9ff; font-size: 18px; }
        
        .results-actions { display: flex; gap: 12px; }
        
        .btn-small {
            padding: 8px 16px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
        }
        
        .btn-copy { background: #00d9ff; color: #1a1a2e; }
        .btn-clear { background: #666; color: white; }
        .btn-word { background: #2b579a; color: white; }
        .btn-pdf { background: #d93025; color: white; }
        .btn-snap { background: #7c5cbf; color: white; }
        
        /* Acciones del tecnico */
        .acciones-section {
            margin-top: 16px;
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
            padding: 16px;
        }
        .acciones-section h3 { color: #00d9ff; font-size: 15px; margin-bottom: 12px; }
        .acciones-campos { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
        .acciones-campos label {
            display: flex; flex-direction: column; gap: 4px;
            font-size: 12px; color: #aaa; flex: 1; min-width: 180px;
        }
        .acciones-campos input, .problema-accion input, .problema-accion select,
        .acciones-section textarea {
            background: #0a0a0f; border: 1px solid #333; color: #eee;
            border-radius: 6px; padding: 8px; font-size: 12px; font-family: inherit;
        }
        .acciones-section textarea { width: 100%; resize: vertical; }
        .problema-item {
            background: rgba(255,255,255,0.04); border-left: 4px solid #888;
            border-radius: 8px; padding: 10px; margin: 8px 0;
        }
        .problema-titulo { font-size: 13px; }
        .problema-accion { display: flex; gap: 8px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
        .problema-accion select { min-width: 180px; }
        .acciones-hint { color: #888; font-size: 11px; margin-top: 10px; }
        .opcion {
            display: flex; gap: 8px; align-items: flex-start;
            font-size: 12px; color: #ccc; margin: 4px 0; cursor: pointer;
        }
        .opcion input { margin-top: 2px; }
        .soluciones-box { margin-top: 6px; padding: 8px; background: rgba(255,255,255,0.03); border-radius: 6px; }
        .kb-box { margin-top: 8px; padding: 8px 10px; background: rgba(79,172,254,0.08); border: 1px solid rgba(79,172,254,0.35); border-radius: 6px; font-size: 12.5px; line-height: 1.45; }
        .kb-box .kb-line { margin-bottom: 4px; }
        .kb-box .kb-line:last-child { margin-bottom: 0; }
        .kb-box .kb-muted { color: #aaa; }
        .kb-search { width: 100%; padding: 8px 10px; margin: 8px 0 12px 0; background: rgba(255,255,255,0.06); border: 1px solid #444; border-radius: 6px; color: #eee; font-size: 13px; }
        .kb-card { margin-bottom: 12px; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid #333; border-left: 4px solid #4facfe; border-radius: 6px; }
        .kb-card h4 { margin: 0 0 2px 0; font-size: 14px; color: #4facfe; }
        .kb-card .kb-cat { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #888; }
        .kb-card .kb-body { font-size: 12.5px; line-height: 1.5; margin-top: 6px; }
        .kb-card .kb-body b { color: #ddd; }
        .kb-card ol { margin: 4px 0 0 18px; padding: 0; }
        .kb-card ol li { margin-bottom: 3px; }
        .mejoras-title { color: #4facfe; font-size: 14px; margin: 14px 0 6px 0; }
        
        /* Status Bar */
        .status-bar {
            background: rgba(0,0,0,0.3);
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 16px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #666;
        }
        
        .status-dot.ready { background: #00ff88; }
        .status-dot.running { background: #ffaa00; animation: pulse 1s infinite; }
        .status-dot.error { background: #ff4444; }
        
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        
        /* Results Content */
        .results-content {
            background: rgba(0,0,0,0.2);
            border-radius: 12px;
            padding: 20px;
            max-height: 600px;
            overflow-y: auto;
        }
        
        .results-empty {
            text-align: center;
            padding: 60px;
            color: #666;
        }
        
        .results-empty-icon { font-size: 48px; margin-bottom: 16px; }
        
        /* Diagnostic Card */
        .diag-card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            border-left: 4px solid #00d9ff;
        }
        
        .diag-card.success { border-color: #00ff88; }
        .diag-card.warning { border-color: #ffaa00; }
        .diag-card.error { border-color: #ff4444; }
        
        .diag-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .diag-title { font-weight: 600; font-size: 16px; }
        .diag-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
        }
        
        .diag-badge.ok { background: #00ff88; color: #000; }
        .diag-badge.warning { background: #ffaa00; color: #000; }
        .diag-badge.error { background: #ff4444; color: #fff; }
        
        .diag-stats {
            display: flex;
            gap: 16px;
            margin-bottom: 12px;
            font-size: 13px;
            color: #888;
        }
        
        .diag-json {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 16px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }
        
        /* Loading Spinner */
        .loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px;
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(0,217,255,0.2);
            border-top-color: #00d9ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .loading-text { margin-top: 16px; color: #888; }
        
        /* Footer */
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }

        /* Banner de permisos de Administrador */
        .elev-banner {
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 14px;
            font-size: 13px;
            line-height: 1.5;
        }
        .elev-banner.warn { background: #fff4e5; border: 1px solid #f0a742; color: #7a4b00; }
        .elev-banner.ok { background: #e8f5e9; border: 1px solid #4caf50; color: #1b5e20; }
        .elev-banner .elev-btn {
            margin-left: 8px; padding: 4px 12px; border-radius: 5px; cursor: pointer;
            border: 1px solid #b26a00; background: #f0a742; color: #3a2400;
            font-size: 13px; font-weight: 600;
        }
        .elev-banner .elev-btn:disabled { opacity: 0.6; cursor: default; }
        .elev-banner .elev-msg { margin-top: 6px; font-size: 12px; }

        .integridad-banner {
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 14px;
            font-size: 13px;
            line-height: 1.5;
            background: #fdecea;
            border: 1px solid #e53935;
            color: #8a1c17;
        }

        .respaldo-banner {
            padding: 10px 14px;
            border-radius: 6px;
            margin-bottom: 14px;
            font-size: 13px;
            line-height: 1.5;
            background: #fff8e1;
            border: 1px solid #ffb300;
            color: #7a5b00;
        }

        /* Seccion de diferencias antes/despues */
        .diff-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px; }
        .diff-table th, .diff-table td { border: 1px solid #444; padding: 6px 8px; text-align: left; vertical-align: top; word-break: break-word; }
        .diff-table th { background: #1e2a3a; color: #cfe3ff; }
        .diff-sin-cambios { color: #7bd88f; font-size: 13px; margin-top: 8px; }

        /* Editor de la base de conocimiento */
        .kb-form { display: none; background: #16212f; border: 1px solid #33506e; border-radius: 6px; padding: 12px; margin-bottom: 14px; }
        .kb-form.open { display: block; }
        .kb-form label { display: block; font-size: 12px; color: #aab; margin-top: 8px; }
        .kb-form input[type=text], .kb-form textarea, .kb-form select {
            width: 100%; margin-top: 4px; padding: 7px 9px; border-radius: 5px;
            border: 1px solid #3a4a5e; background: #0f1722; color: #e8eef7; font-size: 13px; font-family: inherit;
        }
        .kb-form textarea { min-height: 70px; resize: vertical; }
        .kb-form .kb-form-actions { margin-top: 12px; display: flex; gap: 8px; }
        .kb-card-actions { display: flex; gap: 8px; margin-top: 8px; }
        .kb-card-actions button { font-size: 12px; padding: 4px 10px; border-radius: 5px; border: 1px solid #3a4a5e; background: #22354a; color: #cfe3ff; cursor: pointer; }
        .kb-card-actions button.kb-del { background: #4a2226; color: #ffc9ce; border-color: #7a3a40; }
        .grupo-extra { margin-top: 6px; font-size: 12px; }
        .grupo-extra summary { cursor: pointer; color: #9fc3ff; }
        .grupo-extra li { color: #b9c4d4; margin-left: 16px; }
        .badge-grupo { display: inline-block; background: #2b4a75; color: #d6e6ff; font-size: 11px; border-radius: 9px; padding: 1px 7px; margin-left: 6px; vertical-align: middle; }
        
        /* Responsive */
        @media (max-width: 768px) {
            .btn-grid { grid-template-columns: repeat(2, 1fr); }
            .btn-full { grid-column: span 2; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>DiagUSB</h1>
            <p class="subtitle">Herramienta de Diagnóstico Interactiva v0.1.0</p>
        </div>

        <div class="elev-banner" id="elevBanner" style="display:none;"></div>

        <div class="integridad-banner" id="integridadBanner" style="display:none;"></div>

        <div class="respaldo-banner" id="respaldoBanner" style="display:none;"></div>
        
        <!-- Buttons Section -->
        <div class="buttons-section">
            <h2>Diagnósticos Rápidos</h2>
            
            <div class="btn-grid">
                <button class="btn btn-full" onclick="runFullScan()">
                    <span class="btn-icon">🔍</span>
                    <span class="btn-label">Revisión Total</span>
                </button>
                
                <button class="btn btn-impresion" onclick="runDiagnostic('impresion')">
                    <span class="btn-icon">🖨️</span>
                    <span class="btn-label">Impresión</span>
                </button>
                
                <button class="btn btn-redes" onclick="runDiagnostic('redes')">
                    <span class="btn-icon">🌐</span>
                    <span class="btn-label">Red Cableada</span>
                </button>
                
                <button class="btn btn-wifi" onclick="runDiagnostic('wifi')">
                    <span class="btn-icon">📶</span>
                    <span class="btn-label">WiFi</span>
                </button>
                
                <button class="btn btn-disco" onclick="runDiagnostic('disco')">
                    <span class="btn-icon">💾</span>
                    <span class="btn-label">Disco</span>
                </button>
                
                <button class="btn btn-memoria" onclick="runDiagnostic('memoria')">
                    <span class="btn-icon">🧠</span>
                    <span class="btn-label">Memoria</span>
                </button>
                
                <button class="btn btn-servicios" onclick="runDiagnostic('servicios')">
                    <span class="btn-icon">⚙️</span>
                    <span class="btn-label">Servicios</span>
                </button>
                
                <button class="btn btn-seguridad" onclick="runDiagnostic('seguridad')">
                    <span class="btn-icon">🔒</span>
                    <span class="btn-label">Seguridad</span>
                </button>
                
                <button class="btn btn-windows" onclick="runDiagnostic('windows_update')">
                    <span class="btn-icon">🔄</span>
                    <span class="btn-label">Windows Update</span>
                </button>
                
                <button class="btn btn-drivers" onclick="runDiagnostic('drivers')">
                    <span class="btn-icon">📦</span>
                    <span class="btn-label">Drivers</span>
                </button>
                
                <button class="btn btn-eventos" onclick="runDiagnostic('eventos')">
                    <span class="btn-icon">📋</span>
                    <span class="btn-label">Eventos Críticos</span>
                </button>
                
                <button class="btn btn-contexto" onclick="runDiagnostic('contexto')">
                    <span class="btn-icon">💻</span>
                    <span class="btn-label">Contexto Sistema</span>
                </button>
                
                <button class="btn btn-kb btn-full" id="btnKb" onclick="toggleKb()">
                    <span class="btn-icon">📖</span>
                    <span class="btn-label">Base de Conocimiento</span>
                </button>
                
                <button class="btn btn-registro btn-full" id="btnRegistro" onclick="toggleRegistro()">
                    <span class="btn-icon">🗂️</span>
                    <span class="btn-label">Registro de análisis</span>
                </button>
            </div>
        </div>
        
        <!-- Results Section -->
        <div class="results-section">
            <div class="results-header">
                <h2>Resultados</h2>
                <div class="results-actions">
                    <button class="btn-small btn-word" id="btnWord" style="display:none;" onclick="downloadReport('doc')">Descargar Word</button>
                    <button class="btn-small btn-pdf" id="btnPdf" style="display:none;" onclick="downloadReport('pdf')">Descargar PDF</button>
                    <button class="btn-small btn-snap" id="btnSnapAntes" style="display:none;" onclick="saveSnapshotAntes()">Guardar ANTES</button>
                    <button class="btn-small btn-snap" id="btnSnapCompara" style="display:none;" onclick="compareSnapshot()">Comparar DESPUÉS</button>
                    <button class="btn-small btn-copy" onclick="copyResults()">Copiar</button>
                    <button class="btn-small btn-clear" onclick="clearResults()">Limpiar</button>
                </div>
            </div>
            
            <div class="status-bar">
                <div class="status-dot" id="statusDot"></div>
                <span id="statusText">Listo para ejecutar diagnósticos</span>
            </div>
            
            <div class="results-content" id="resultsContent">
                <div class="results-empty">
                    <div class="results-empty-icon">🔧</div>
                    <p>Haga clic en un botón para ejecutar un diagnóstico</p>
                </div>
            </div>

            <div class="acciones-section" id="diffSection" style="display:none;">
                <h3>Comparación antes / después</h3>
                <div id="diffTabla"></div>
            </div>
            
            <div class="acciones-section" id="accionesSection" style="display:none;">
                <h3 id="accionesTitulo">Acciones del técnico - Generación de informe</h3>
                <div id="problemasLista"></div>
                <div class="acciones-campos">
                    <label>Tecnico
                        <input id="tecnico" type="text" placeholder="Nombre del técnico">
                    </label>
                    <label>Cliente / Sector
                        <input id="cliente" type="text" placeholder="Cliente o área">
                    </label>
                </div>
                <div id="mejorasLista"></div>
                <label style="display:block; margin-top:12px; font-size:12px; color:#aaa;">
                    Observaciones generales
                    <textarea id="observaciones" rows="3" placeholder="Notas adicionales del trabajo realizado..."></textarea>
                </label>
                <p class="acciones-hint">Complete el estado y la acción implementada para cada problema; quedarán registradas en el informe Word/PDF.</p>
            </div>
            
            <div class="acciones-section" id="kbSection" style="display:none;">
                <h3>Base de conocimiento local</h3>
                <p class="acciones-hint">Cómo debe estar cada componente para que funcione bien, cómo lograrlo y cómo comprobarlo. Busque por síntoma, componente o palabra clave.</p>
                <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
                    <input id="kbSearch" class="kb-search" type="text" placeholder="Buscar... (ej: impresora, firewall, disco, sin internet, memoria)" style="flex:1;">
                    <button class="btn-small btn-copy" id="btnKbNueva" onclick="openKbForm(null)">+ Nueva entrada</button>
                </div>
                <div class="kb-form" id="kbForm">
                    <h4 id="kbFormTitulo" style="margin-bottom:4px;">Nueva entrada</h4>
                    <label>ID (minúsculas y guiones bajos, ej: spooler_sucio)
                        <input id="kbf_id" type="text"></label>
                    <label>Título
                        <input id="kbf_titulo" type="text"></label>
                    <label>Categoría
                        <input id="kbf_categoria" type="text" placeholder="Servicios, Red, Disco, Impresión..."></label>
                    <label>Colectores asociados (separados por coma)
                        <input id="kbf_colectores" type="text" placeholder="critical_services, service_failures"></label>
                    <label>Síntomas asociados (separados por coma)
                        <input id="kbf_sintomas" type="text" placeholder="servicio_detenido, no_hay_internet"></label>
                    <label>Cómo debe estar (estado esperado)
                        <textarea id="kbf_estado_esperado"></textarea></label>
                    <label>Por qué importa
                        <textarea id="kbf_por_que_importa"></textarea></label>
                    <label>Soluciones (una por línea)
                        <textarea id="kbf_soluciones"></textarea></label>
                    <label>Verificación (cómo comprobar que quedó bien)
                        <textarea id="kbf_verificacion"></textarea></label>
                    <div class="kb-form-actions">
                        <button class="btn-small btn-word" onclick="saveKbForm()">Guardar</button>
                        <button class="btn-small btn-clear" onclick="closeKbForm()">Cancelar</button>
                    </div>
                </div>
                <div id="kbLista"></div>
            </div>
            
            <div class="acciones-section" id="registroSection" style="display:none;">
                <h3>Registro de análisis</h3>
                <p class="acciones-hint">Todo diagnóstico que ejecute queda guardado automáticamente aquí de forma persistente. Puede consultar el detalle, eliminar análisis individuales o vaciar el registro completo.</p>
                <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
                    <input id="regSearch" class="kb-search" type="text" placeholder="Buscar... (paquete, síntoma, problema)" oninput="filterRegistro()" style="flex:1;">
                    <button class="btn-small btn-copy" onclick="loadRegistro(true)">Actualizar</button>
                    <button class="btn-small btn-clear" id="btnRegVaciar" onclick="vaciarRegistro()" style="display:none;">Vaciar registro</button>
                </div>
                <div id="regLista"></div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p>DiagUSB v0.1.0 | Copyright (C) 2026 Daniel Ricardo Novoa | GPL-3.0-or-later</p>
        </div>
    </div>
    
    <script>
        let isRunning = false;
        let currentDiag = null;
        let lastDiffs = null;
        let lastComparacionForzada = false;

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s == null ? '' : String(s);
            return d.innerHTML;
        }

        function formKey(f) {
            return [f.package_label || '', f.severity || '', f.collector_id || '', f.message || ''].join('|');
        }

        function loadForm() {
            try { return JSON.parse(localStorage.getItem('diagusb_form') || '{}') || {}; }
            catch (e) { return {}; }
        }

        function saveForm() {
            const data = loadForm();
            data.tecnico = (document.getElementById('tecnico') || {}).value || '';
            data.cliente = (document.getElementById('cliente') || {}).value || '';
            data.observaciones = (document.getElementById('observaciones') || {}).value || '';
            data.problemas = data.problemas || {};
            const findings = (currentDiag && currentDiag.findings) || [];
            findings.forEach((f, i) => {
                const key = formKey(f);
                const sols = f.solutions || [];
                data.problemas[key] = {
                    estado: (document.getElementById('estado_' + i) || {}).value || '',
                    solucion: (document.getElementById('solucion_' + i) || {}).value || '',
                    soluciones: sols.map((s, j) => {
                        const el = document.getElementById('sol_' + i + '_' + j);
                        return (el && el.checked) ? j : -1;
                    }).filter(x => x >= 0)
                };
            });
            data.mejoras = data.mejoras || {};
            ((currentDiag && currentDiag.improvements) || []).forEach((m, i) => {
                data.mejoras[m.id] = {
                    aplicada: !!((document.getElementById('mejora_' + i) || {}).checked),
                    comentario: (document.getElementById('mejora_coment_' + i) || {}).value || ''
                };
            });
            try { localStorage.setItem('diagusb_form', JSON.stringify(data)); } catch (e) {}
        }

        function applyForm() {
            const data = loadForm();
            if (data.tecnico != null) document.getElementById('tecnico').value = data.tecnico;
            if (data.cliente != null) document.getElementById('cliente').value = data.cliente;
            if (data.observaciones != null) document.getElementById('observaciones').value = data.observaciones;
            const saved = data.problemas || {};
            const findings = (currentDiag && currentDiag.findings) || [];
            findings.forEach((f, i) => {
                const st = saved[formKey(f)];
                if (!st) return;
                const sel = document.getElementById('estado_' + i);
                if (sel && st.estado) sel.value = st.estado;
                const inp = document.getElementById('solucion_' + i);
                if (inp && st.solucion) inp.value = st.solucion;
                (st.soluciones || []).forEach(j => {
                    const cb = document.getElementById('sol_' + i + '_' + j);
                    if (cb) cb.checked = true;
                });
            });
            const ms = data.mejoras || {};
            ((currentDiag && currentDiag.improvements) || []).forEach((m, i) => {
                const st = ms[m.id];
                if (!st) return;
                const cb = document.getElementById('mejora_' + i);
                if (cb) cb.checked = !!st.aplicada;
                const com = document.getElementById('mejora_coment_' + i);
                if (com && st.comentario) com.value = st.comentario;
            });
        }

        function hideAcciones() {
            currentDiag = null;
            lastDiffs = null;
            lastComparacionForzada = false;
            document.getElementById('accionesSection').style.display = 'none';
            document.getElementById('btnWord').style.display = 'none';
            document.getElementById('btnPdf').style.display = 'none';
            document.getElementById('btnSnapAntes').style.display = 'none';
            document.getElementById('btnSnapCompara').style.display = 'none';
            document.getElementById('diffSection').style.display = 'none';
        }
        
        function renderProblemas(findings) {
            const section = document.getElementById('accionesSection');
            const titulo = document.getElementById('accionesTitulo');
            const lista = document.getElementById('problemasLista');
            const mejorasLista = document.getElementById('mejorasLista');
            const colores = {critical: '#b00020', error: '#d93025', warning: '#e37400', ok: '#188038'};
            const sevLabel = {critical: 'CRITICO', error: 'ERROR', warning: 'ADVERTENCIA', ok: 'OK'};
            const estados = (currentDiag && currentDiag.estados_accion) ||
                ['Pendiente', 'Resuelto', 'Resuelto parcialmente', 'No reproducido', 'Requiere repuestos', 'Derivado / escalar'];
            
            if (!findings || findings.length === 0) {
                lista.innerHTML = '';
                titulo.textContent = 'Acciones del técnico - Generación de informe';
            } else {
                titulo.textContent = 'Problemas detectados y base de conocimiento - Acciones del técnico';
                let html = '';
                findings.forEach((f, i) => {
                    const color = colores[f.severity] || '#888';
                    const gt = (f.details && f.details.grupo_total) || 0;
                    const gmens = (f.details && f.details.grupo_mensajes) || [];
                    html += '<div class="problema-item" style="border-left-color:' + color + ';">';
                    html += '<div class="problema-titulo"><span class="diag-badge" style="background:' + color + '; color:#fff;">' +
                        escHtml(sevLabel[f.severity] || f.severity) + '</span> ' + escHtml(f.message) +
                        (gt > 1 ? '<span class="badge-grupo" title="Casos agrupados con el mismo problema">×' + gt + '</span>' : '') +
                        ' <span class="muted">(' + escHtml(f.package_label ? f.package_label + ' / ' : '') + escHtml(f.collector_id) + ')</span></div>';
                    if (gmens.length > 0) {
                        html += '<details class="grupo-extra"><summary>' + gmens.length +
                            ' caso(s) más del mismo problema</summary><ul>';
                        gmens.forEach(m => { html += '<li>' + escHtml(m) + '</li>'; });
                        html += '</ul></details>';
                    }
                    const kbinfo = f.knowledge;
                    if (kbinfo && kbinfo.estado_esperado) {
                        html += '<div class="kb-box">';
                        html += '<div class="kb-line"><b>Cómo debe estar:</b> ' + escHtml(kbinfo.estado_esperado) + '</div>';
                        if (kbinfo.por_que_importa) {
                            html += '<div class="kb-line kb-muted"><b>Por qué importa:</b> ' + escHtml(kbinfo.por_que_importa) + '</div>';
                        }
                        if (kbinfo.verificacion) {
                            html += '<div class="kb-line"><b>Cómo verificar que quedó bien:</b> ' + escHtml(kbinfo.verificacion) + '</div>';
                        }
                        html += '</div>';
                    }
                    const sols = f.solutions || [];
                    if (sols.length > 0) {
                        html += '<div class="soluciones-box"><div class="acciones-hint">' +
                            (kbinfo && kbinfo.id ? 'Pasos de corrección según la base de conocimiento - marque la(s) que aplicó:' :
                             'Soluciones posibles - marque la(s) que aplicó:') + '</div>';
                        sols.forEach((s, j) => {
                            html += '<label class="opcion"><input type="checkbox" id="sol_' + i + '_' + j + '" value="' +
                                escHtml(s) + '"> <span>' + escHtml(s) + '</span></label>';
                        });
                        html += '</div>';
                    }
                    html += '<div class="problema-accion">';
                    html += '<select id="estado_' + i + '">' +
                        estados.map(e => '<option value="' + escHtml(e) + '">' + escHtml(e) + '</option>').join('') +
                        '</select>';
                    html += '<input id="solucion_' + i + '" type="text" style="flex:1; min-width:240px;" placeholder="Detalle de la acción implementada (opcional)...">';
                    html += '</div></div>';
                });
                lista.innerHTML = html;
            }
            
            // Mejoras sugeridas
            const mejoras = (currentDiag && currentDiag.improvements) || [];
            if (mejoras.length === 0) {
                mejorasLista.innerHTML = '';
            } else {
                let mh = '<div class="mejoras-title">Mejoras sugeridas (marque las que implementó):</div>';
                mejoras.forEach((m, i) => {
                    mh += '<div class="problema-item" style="border-left-color:#4facfe;">';
                    mh += '<label class="opcion"><input type="checkbox" id="mejora_' + i + '"> <span><b>' +
                        escHtml(m.titulo) + '</b></span></label>';
                    mh += '<div class="acciones-hint">' + escHtml(m.detalle) + '</div>';
                    mh += '<input id="mejora_coment_' + i + '" type="text" style="width:100%; margin-top:6px;" placeholder="Comentario sobre la mejora (opcional)...">';
                    mh += '</div>';
                });
                mejorasLista.innerHTML = mh;
            }

            section.style.display = 'block';
            document.getElementById('btnWord').style.display = '';
            document.getElementById('btnPdf').style.display = '';
            document.getElementById('btnSnapAntes').style.display = '';
            document.getElementById('btnSnapCompara').style.display = '';
            applyForm();
        }
        
        function collectPayload() {
            const findings = (currentDiag && currentDiag.findings) || [];
            const acciones = findings.map((f, i) => {
                const sols = f.solutions || [];
                const elegidas = sols
                    .map((s, j) => ({s: s, el: document.getElementById('sol_' + i + '_' + j)}))
                    .filter(x => x.el && x.el.checked)
                    .map(x => x.s);
                return {
                    indice: i + 1,
                    estado: (document.getElementById('estado_' + i) || {}).value || 'Pendiente',
                    solucion_elegida: elegidas.join('; '),
                    solucion: (document.getElementById('solucion_' + i) || {}).value || ''
                };
            });
            const mejoras = ((currentDiag && currentDiag.improvements) || []).map((m, i) => ({
                id: m.id,
                aplicada: !!((document.getElementById('mejora_' + i) || {}).checked),
                comentario: (document.getElementById('mejora_coment_' + i) || {}).value || ''
            }));
            return {
                diagnostico: currentDiag,
                acciones: acciones,
                mejoras: mejoras,
                tecnico: (document.getElementById('tecnico') || {}).value || '',
                cliente: (document.getElementById('cliente') || {}).value || '',
                observaciones: (document.getElementById('observaciones') || {}).value || '',
                diferencias: lastDiffs || [],
                comparacion_forzada: !!lastComparacionForzada
            };
        }

        async function saveSnapshotAntes() {
            if (!currentDiag) return;
            setStatus('running', 'Guardando snapshot ANTES...');
            try {
                const resp = await fetch('/api/snapshot', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({results: currentDiag.results || []})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                setStatus('ready', 'Snapshot ANTES guardado (' + d.collectors + ' colectores, ' + d.captured_at.slice(0, 19) + ')');
            } catch (e) {
                setStatus('error', 'Error al guardar el snapshot: ' + e.message);
            }
        }

        function renderDiff(diffs, baselineEn) {
            const sec = document.getElementById('diffSection');
            const el = document.getElementById('diffTabla');
            lastDiffs = diffs || [];
            let html = '<div class="acciones-hint">Snapshot de referencia: ' + escHtml(baselineEn || '-') + '</div>';
            if (!lastDiffs.length) {
                html += '<div class="diff-sin-cambios">✓ Sin cambios entre el estado ANTES y el actual.</div>';
            } else {
                html += '<table class="diff-table"><tr><th>Colector</th><th>Campo</th><th>Antes</th><th>Después</th></tr>';
                lastDiffs.forEach(d => {
                    const fmt = v => {
                        if (v && typeof v === 'object') return '[' + (Array.isArray(v) ? v.length + ' registros' : Object.keys(v).length + ' campos') + ']';
                        const s = v == null ? '-' : String(v);
                        return s.length > 140 ? s.slice(0, 137) + '...' : s;
                    };
                    html += '<tr><td>' + escHtml(d.collector_id || '') + '</td><td>' + escHtml(d.field_path || '') +
                        '</td><td>' + escHtml(fmt(d.baseline_value)) + '</td><td>' + escHtml(fmt(d.current_value)) + '</td></tr>';
                });
                html += '</table>';
            }
            el.innerHTML = html;
            sec.style.display = 'block';
            sec.scrollIntoView({behavior: 'smooth', block: 'nearest'});
        }

        async function compareSnapshot(forzar) {
            if (!currentDiag) return;
            setStatus('running', 'Comparando contra el snapshot ANTES...');
            try {
                const resp = await fetch('/api/compare', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({results: currentDiag.results || [], forzar: !!forzar})
                });
                const d = await resp.json();
                if (resp.status === 409) {
                    const msg = d.error || 'El snapshot ANTES pertenece a otro equipo.';
                    if (confirm(msg + '  ¿Comparar de todos modos?')) {
                        return compareSnapshot(true);
                    }
                    setStatus('ready', 'Comparación cancelada por el técnico.');
                    return;
                }
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                lastComparacionForzada = !!d.equipos_distintos;
                renderDiff(d.diferencias || [], d.baseline_en);
                let texto = 'Comparación lista: ' + (lastDiffs ? lastDiffs.length : 0) + ' diferencia(s). Incluirán en el informe.';
                if (lastComparacionForzada) {
                    texto = 'ADVERTENCIA: comparación entre equipos distintos. ' + texto;
                } else if (d.advertencia) {
                    texto = d.advertencia + ' ' + texto;
                }
                setStatus(lastComparacionForzada ? 'error' : 'ready', texto);
            } catch (e) {
                setStatus('error', 'Error al comparar: ' + e.message);
            }
        }
        
        async function downloadReport(format) {
            if (!currentDiag) {
                alert('Ejecute primero un diagnóstico individual (no la Revisión Total).');
                return;
            }
            setStatus('running', 'Generando informe ' + format.toUpperCase() + '...');
            try {
                const resp = await fetch('/api/report?format=' + format, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(collectPayload())
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.error || ('HTTP ' + resp.status));
                }
                const blob = await resp.blob();
                const cd = resp.headers.get('Content-Disposition') || '';
                const m = cd.match(/filename=\"?([^\";]+)/);
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = m ? m[1] : 'informe.' + format;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
                setStatus('ready', 'Informe ' + format.toUpperCase() + ' descargado');
            } catch (e) {
                setStatus('error', 'Error al generar informe: ' + e.message);
            }
        }
        
        function mostrarIntegridad(lista) {
            const b = document.getElementById('integridadBanner');
            if (!b) return;
            if (lista && lista.length) {
                b.textContent = 'Integridad: ' + lista.length + ' colector(es) modificado(s): ' +
                    lista.join(', ') + '. No se ejecutaron. Regenere el kit desde una copia confiable.';
                b.style.display = 'block';
            } else {
                b.style.display = 'none';
            }
        }

        function setStatus(status, text) {
            const dot = document.getElementById('statusDot');
            const textEl = document.getElementById('statusText');
            dot.className = 'status-dot ' + status;
            textEl.textContent = text;
        }
        
        function showLoading(message) {
            return '<div class="loading"><div class="spinner"></div><p class="loading-text">' + message + '</p></div>';
        }
        
        function formatJson(data) {
            try {
                return JSON.stringify(data, null, 2);
            } catch (e) {
                return String(data);
            }
        }
        
        function getStatusBadge(ok, errors, problems, empty) {
            problems = problems || 0;
            empty = empty || 0;
            if (errors > 0) return '<span class="diag-badge error">' + errors + ' error(es)</span>';
            if (problems > 0) return '<span class="diag-badge error">' + problems + ' problema(s)</span>';
            if (ok > 0) return '<span class="diag-badge ok">OK</span>';
            if (empty > 0) return '<span class="diag-badge warning">Sin datos: ' + empty + '</span>';
            return '<span class="diag-badge warning">Sin datos</span>';
        }
        
        async function runDiagnostic(package) {
            if (isRunning) return;
            isRunning = true;
            
            const buttons = document.querySelectorAll('.btn:not(#btnKb):not(#btnRegistro)');
            buttons.forEach(b => b.disabled = true);
            
            setStatus('running', 'Ejecutando diagnóstico de ' + package + '...');
            document.getElementById('resultsContent').innerHTML = showLoading('Ejecutando colectores...');
            
            try {
                const response = await fetch('/api/diagnose?package=' + encodeURIComponent(package));
                const data = await response.json();
                
                if (data.error) {
                    hideAcciones();
                    mostrarIntegridad([]);
                    document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>' + data.error + '</p></div>';
                    setStatus('error', 'Error: ' + data.error);
                } else {
                    currentDiag = data;
                    lastDiffs = null;
                    lastComparacionForzada = false;
                    mostrarIntegridad(data.integridad_fallida);
                    document.getElementById('diffSection').style.display = 'none';
                    const nProblemas = (data.findings || []).length;
                    renderProblemas(data.findings || []);
                    let html = '<div class="diag-card ' + ((data.error_count > 0 || nProblemas > 0) ? 'warning' : 'success') + '">';
                    html += '<div class="diag-header">';
                    html += '<span class="diag-title">' + data.package_label + '</span>';
                    html += getStatusBadge(data.ok_count, data.error_count, nProblemas, data.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>Colectores: ' + data.collectors_count + '</span>';
                    html += '<span>OK: ' + data.ok_count + '</span>';
                    html += '<span>Errores: ' + data.error_count + '</span>';
                    html += '<span>Sin datos: ' + (data.empty_count || 0) + '</span>';
                    html += '<span>Problemas: ' + nProblemas + '</span>';
                    html += '<span>' + data.timestamp + '</span>';
                    html += '</div>';
                    
                    // Mostrar resultados expandidos
                    for (const result of data.results) {
                        const status = result.query?.status || 'unknown';
                        const cardClass = status === 'ok' ? 'success' : (status === 'error' ? 'error' : 'warning');
                        html += '<div class="diag-card ' + cardClass + '" style="margin-top: 12px; border-left-width: 2px;">';
                        html += '<div class="diag-header">';
                        html += '<span class="diag-title">' + (result.collector_id || 'unknown') + '</span>';
                        html += '<span class="diag-badge ' + (status === 'ok' ? 'ok' : 'error') + '">' + status + '</span>';
                        html += '</div>';
                        html += '<div class="diag-json">' + formatJson(result.data || result) + '</div>';
                        html += '</div>';
                    }
                    
                    html += '</div>';
                    document.getElementById('resultsContent').innerHTML = html;
                    setStatus('ready', 'Diagnóstico completado: ' + data.package_label +
                        (data.registro_id ? ' · guardado en registro' : ''));
                }
            } catch (e) {
                hideAcciones();
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + e.message + '</p></div>';
                setStatus('error', 'Error de conexión');
            }
            
            buttons.forEach(b => b.disabled = false);
            isRunning = false;
        }
        
        async function runFullScan() {
            if (isRunning) return;
            isRunning = true;
            hideAcciones();
            
            const buttons = document.querySelectorAll('.btn:not(#btnKb):not(#btnRegistro)');
            buttons.forEach(b => b.disabled = true);
            
            setStatus('running', 'Ejecutando revisión total del equipo...');
            document.getElementById('resultsContent').innerHTML = showLoading('Ejecutando todos los diagnósticos...');
            
            try {
                const response = await fetch('/api/full-scan');
                const data = await response.json();
                
                const integridadTotal = [];
                (data.diagnostics || []).forEach(dg => (dg.integridad_fallida || []).forEach(x => {
                    if (integridadTotal.indexOf(x) === -1) integridadTotal.push(x);
                }));
                mostrarIntegridad(integridadTotal);
                
                let html = '';
                let totalErrors = 0;
                let totalOk = 0;
                let totalEmpty = 0;
                let totalProblems = 0;
                let totalCollectors = 0;
                const allFindings = [];
                const allImprovements = [];
                const allResults = [];
                const allRecommendations = [];
                const seenMejoras = {};
                
                for (const diag of data.diagnostics) {
                    const errors = diag.error_count || 0;
                    const ok = diag.ok_count || 0;
                    const problems = (diag.findings || []).length;
                    totalErrors += errors;
                    totalOk += ok;
                    totalEmpty += (diag.empty_count || 0);
                    totalProblems += problems;
                    totalCollectors += diag.collectors_count || (diag.results || []).length;
                    
                    (diag.results || []).forEach(r => allResults.push(r));
                    (diag.findings || []).forEach(f => {
                        const c = Object.assign({}, f);
                        c.package_label = diag.package_label;
                        allFindings.push(c);
                    });
                    (diag.improvements || []).forEach(m => {
                        if (!seenMejoras[m.id]) {
                            seenMejoras[m.id] = true;
                            allImprovements.push(m);
                        }
                    });
                    (diag.recommendations || []).forEach(rc => {
                        if (allRecommendations.indexOf(rc) === -1) allRecommendations.push(rc);
                    });
                    
                    const cardClass = (errors > 0 || problems > 0) ? 'warning' : 'success';
                    html += '<div class="diag-card ' + cardClass + '">';
                    html += '<div class="diag-header">';
                    html += '<span class="diag-title">' + diag.package_label + '</span>';
                    html += getStatusBadge(ok, errors, problems, diag.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>OK: ' + ok + '</span>';
                    html += '<span>Errores: ' + errors + '</span>';
                    html += '<span>Sin datos: ' + (diag.empty_count || 0) + '</span>';
                    html += '<span>Problemas: ' + problems + '</span>';
                    html += '</div>';
                    
                    // Mostrar colectores con problemas
                    for (const result of diag.results) {
                        const status = result.query?.status || 'unknown';
                        if (status === 'error') {
                            html += '<div class="diag-json" style="margin-top: 8px; padding: 8px;">';
                            html += '<strong>' + (result.collector_id || 'unknown') + ':</strong> ' + formatJson(result.data || result);
                            html += '</div>';
                        }
                    }
                    
                    html += '</div>';
                }
                
                // Resumen
                html = '<div class="diag-card ' + ((totalErrors > 0 || totalProblems > 0) ? 'warning' : 'success') + '" style="margin-bottom: 20px;">' +
                    '<div class="diag-header">' +
                    '<span class="diag-title">RESUMEN TOTAL</span>' +
                    getStatusBadge(totalOk, totalErrors, totalProblems, totalEmpty) +
                    '</div>' +
                    '<div class="diag-stats">' +
                    '<span>Paquetes: ' + data.diagnostics.length + '</span>' +
                    '<span>Colectores OK: ' + totalOk + '</span>' +
                    '<span>Colectores con error: ' + totalErrors + '</span>' +
                    '<span>Sin datos: ' + totalEmpty + '</span>' +
                    '<span>Problemas detectados: ' + totalProblems + '</span>' +
                    '</div>' +
                    '</div>' + html;

                // Seccion de acciones del tecnico e informe (igual que un diagnostico individual)
                lastDiffs = null;
                lastComparacionForzada = false;
                document.getElementById('diffSection').style.display = 'none';
                currentDiag = {
                    package: 'full-scan',
                    package_label: 'Revisión Total',
                    symptom: 'revision_total',
                    collectors_count: totalCollectors,
                    ok_count: totalOk,
                    error_count: totalErrors,
                    empty_count: totalEmpty,
                    findings: allFindings,
                    improvements: allImprovements,
                    results: allResults,
                    recommendations: allRecommendations,
                    estados_accion: (data.diagnostics[0] || {}).estados_accion,
                    timestamp: data.timestamp
                };
                renderProblemas(allFindings);
                
                document.getElementById('resultsContent').innerHTML = html;
                setStatus('ready', 'Revisión total completada' +
                    (data.registro_id ? ' · guardado en registro' : ''));
            } catch (e) {
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + e.message + '</p></div>';
                setStatus('error', 'Error de conexión');
            }
            
            buttons.forEach(b => b.disabled = false);
            isRunning = false;
        }
        
        function copyResults() {
            const content = document.getElementById('resultsContent').innerText;
            navigator.clipboard.writeText(content).then(() => {
                alert('Resultados copiados al portapapeles');
            });
        }
        
        function clearResults() {
            hideAcciones();
            document.getElementById('resultsContent').innerHTML = 
                '<div class="results-empty"><div class="results-empty-icon">🔧</div><p>Haga clic en un botón para ejecutar un diagnóstico</p></div>';
            setStatus('ready', 'Listo para ejecutar diagnósticos');
        }
        
        let kbEntradas = [];
        let kbRender = [];
        
        function renderKb(lista) {
            const el = document.getElementById('kbLista');
            if (!el) return;
            if (!kbEntradas.length) {
                el.innerHTML = '<p class="acciones-hint">Base de conocimiento no disponible (archivo base_conocimiento.json no encontrado o vacío).</p>';
                return;
            }
            if (!lista.length) {
                el.innerHTML = '<p class="acciones-hint">Sin resultados para esa búsqueda.</p>';
                return;
            }
            let html = '';
            kbRender = lista;
            lista.forEach((e, i) => {
                html += '<div class="kb-card">';
                html += '<div class="kb-cat">' + escHtml(e.categoria || 'General') + '</div>';
                html += '<h4>' + escHtml(e.titulo || e.id) + '</h4>';
                html += '<div class="kb-body">';
                if (e.estado_esperado) html += '<div><b>Cómo debe estar:</b> ' + escHtml(e.estado_esperado) + '</div>';
                if (e.por_que_importa) html += '<div class="kb-muted" style="color:#aaa; margin-top:4px;"><b>Por qué importa:</b> ' + escHtml(e.por_que_importa) + '</div>';
                if (e.soluciones && e.soluciones.length) {
                    html += '<div style="margin-top:6px;"><b>Solución:</b><ol>';
                    e.soluciones.forEach(s => { html += '<li>' + escHtml(s) + '</li>'; });
                    html += '</ol></div>';
                }
                if (e.verificacion) html += '<div style="margin-top:6px;"><b>Verificación:</b> ' + escHtml(e.verificacion) + '</div>';
                html += '</div>';
                html += '<div class="kb-card-actions">' +
                    '<button class="kb-edit" data-kb-idx="' + i + '">Editar</button>' +
                    '<button class="kb-del" data-kb-idx="' + i + '">Eliminar</button>' +
                    '</div>';
                html += '</div>';
            });
            el.innerHTML = html;
        }
        
        function filterKb() {
            const q = ((document.getElementById('kbSearch') || {}).value || '').trim().toLowerCase();
            if (!q) { renderKb(kbEntradas); return; }
            const lista = kbEntradas.filter(e =>
                JSON.stringify(e).toLowerCase().indexOf(q) !== -1);
            renderKb(lista);
        }
        
        async function loadKnowledge() {
            try {
                const r = await fetch('/api/knowledge');
                const d = await r.json();
                kbEntradas = d.entradas || [];
                renderKb(kbEntradas);
            } catch (e) {
                const el = document.getElementById('kbLista');
                if (el) el.innerHTML = '<p class="acciones-hint">No se pudo cargar la base de conocimiento.</p>';
            }
        }
        
        function toggleKb() {
            const sec = document.getElementById('kbSection');
            const btn = document.getElementById('btnKb');
            const abierto = sec.style.display === 'block';
            if (abierto) {
                sec.style.display = 'none';
                btn.classList.remove('btn-open');
                closeKbForm();
            } else {
                if (!kbEntradas.length) loadKnowledge();
                sec.style.display = 'block';
                btn.classList.add('btn-open');
                sec.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        }

        let kbEditId = null;

        function openKbForm(entrada) {
            const form = document.getElementById('kbForm');
            kbEditId = entrada ? entrada.id : null;
            document.getElementById('kbFormTitulo').textContent =
                entrada ? ('Editar entrada: ' + (entrada.titulo || entrada.id)) : 'Nueva entrada';
            document.getElementById('kbf_id').value = entrada ? (entrada.id || '') : '';
            document.getElementById('kbf_id').disabled = !!entrada;
            document.getElementById('kbf_titulo').value = entrada ? (entrada.titulo || '') : '';
            document.getElementById('kbf_categoria').value = entrada ? (entrada.categoria || '') : '';
            document.getElementById('kbf_colectores').value = entrada && entrada.colectores ? entrada.colectores.join(', ') : '';
            document.getElementById('kbf_sintomas').value = entrada && entrada.sintomas ? entrada.sintomas.join(', ') : '';
            document.getElementById('kbf_estado_esperado').value = entrada ? (entrada.estado_esperado || '') : '';
            document.getElementById('kbf_por_que_importa').value = entrada ? (entrada.por_que_importa || '') : '';
            document.getElementById('kbf_soluciones').value = entrada && entrada.soluciones ? entrada.soluciones.join('\\n') : '';
            document.getElementById('kbf_verificacion').value = entrada ? (entrada.verificacion || '') : '';
            form.classList.add('open');
            form.scrollIntoView({behavior: 'smooth', block: 'nearest'});
        }

        function openKbFormById(id) {
            const e = kbEntradas.find(x => x.id === id);
            if (e) openKbForm(e);
        }

        function closeKbForm() {
            const form = document.getElementById('kbForm');
            if (form) form.classList.remove('open');
            kbEditId = null;
        }

        const splitCsv = v => (v || '').split(',').map(x => x.trim()).filter(Boolean);

        async function saveKbForm() {
            const id = kbEditId || (document.getElementById('kbf_id').value || '').trim().toLowerCase();
            const titulo = (document.getElementById('kbf_titulo').value || '').trim();
            if (!id || !titulo) {
                alert('El ID y el título son obligatorios.');
                return;
            }
            const entrada = {
                id: id,
                titulo: titulo,
                categoria: (document.getElementById('kbf_categoria').value || '').trim() || 'General',
                colectores: splitCsv(document.getElementById('kbf_colectores').value),
                sintomas: splitCsv(document.getElementById('kbf_sintomas').value),
                estado_esperado: document.getElementById('kbf_estado_esperado').value || '',
                por_que_importa: document.getElementById('kbf_por_que_importa').value || '',
                soluciones: (document.getElementById('kbf_soluciones').value || '').split('\\n').map(x => x.trim()).filter(Boolean),
                verificacion: document.getElementById('kbf_verificacion').value || ''
            };
            try {
                const resp = await fetch('/api/knowledge', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'guardar', entrada: entrada})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                kbEntradas = d.entradas || [];
                closeKbForm();
                filterKb();
                setStatus('ready', 'Entrada de la base de conocimiento guardada (capa local)');
            } catch (e) {
                alert('No se pudo guardar: ' + e.message);
            }
        }

        async function deleteKb(id, titulo) {
            if (!confirm('¿Eliminar la entrada "' + titulo + '" de la base de conocimiento local?')) return;
            try {
                const resp = await fetch('/api/knowledge', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'eliminar', id: id})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                kbEntradas = d.entradas || [];
                filterKb();
                setStatus('ready', 'Entrada eliminada de la base de conocimiento local');
            } catch (e) {
                alert('No se pudo eliminar: ' + e.message);
            }
        }

        // ---------------------------------------------------------------
        // Registro persistente de análisis
        // ---------------------------------------------------------------
        let regEntradas = [];
        
        function renderRegistro(lista) {
            const el = document.getElementById('regLista');
            if (!el) return;
            const vaciar = document.getElementById('btnRegVaciar');
            if (vaciar) vaciar.style.display = regEntradas.length ? '' : 'none';
            if (!regEntradas.length) {
                el.innerHTML = '<p class="acciones-hint">Todavía no hay análisis registrados. Cada diagnóstico que ejecute quedará guardado automáticamente aquí.</p>';
                return;
            }
            if (!lista.length) {
                el.innerHTML = '<p class="acciones-hint">Sin resultados para esa búsqueda.</p>';
                return;
            }
            let html = '';
            lista.forEach(e => {
                const c = e.conteos || {};
                const fecha = (e.fecha || '').replace('T', ' ').slice(0, 19);
                const tipo = e.tipo === 'full-scan' ? 'Revisión total' : 'Paquete';
                html += '<div class="kb-card">';
                html += '<div class="kb-cat">' + escHtml(tipo) + ' · ' + escHtml(fecha) + '</div>';
                html += '<h4>' + escHtml(e.paquete_label || e.paquete || '-') + '</h4>';
                html += '<div class="kb-body">';
                html += '<div><b>Síntoma:</b> ' + escHtml(e.sintoma || '-') + '</div>';
                html += '<div style="margin-top:4px;">Colectores OK: ' + (c.ok || 0) +
                    ' · Con error: ' + (c.error || 0) +
                    ' · Sin datos: ' + (c.empty || 0) +
                    ' · <b>Problemas: ' + (c.findings || 0) + '</b></div>';
                html += '<div id="regdet_' + e.id + '" style="display:none; margin-top:8px;"></div>';
                html += '</div>';
                html += '<div class="kb-card-actions">' +
                    '<button class="reg-det" data-reg-det="' + e.id + '">Ver detalle</button>' +
                    '<button class="kb-del" data-reg-del="' + e.id + '">Eliminar</button>' +
                    '</div>';
                html += '</div>';
            });
            el.innerHTML = html;
            el.querySelectorAll('[data-reg-del]').forEach(b =>
                b.addEventListener('click', () => eliminarRegistro(b.getAttribute('data-reg-del'))));
            el.querySelectorAll('[data-reg-det]').forEach(b =>
                b.addEventListener('click', () => toggleRegDetalle(b.getAttribute('data-reg-det'), b)));
        }
        
        async function toggleRegDetalle(id, btn) {
            const cont = document.getElementById('regdet_' + id);
            if (!cont) return;
            if (cont.style.display === 'block') {
                cont.style.display = 'none';
                btn.textContent = 'Ver detalle';
                return;
            }
            if (!cont.innerHTML) {
                try {
                    const r = await fetch('/api/registro?id=' + encodeURIComponent(id));
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    let h = '';
                    const findings = d.findings || [];
                    if (!findings.length) {
                        h += '<div class="acciones-hint">Sin problemas detectados en ese análisis.</div>';
                    }
                    findings.forEach(f => {
                        const color = f.severity === 'error' ? '#ff6b6b' :
                                     (f.severity === 'warning' ? '#ffd166' : '#8ef0a0');
                        h += '<div style="margin-bottom:6px; border-left:3px solid ' + color + '; padding-left:8px;">';
                        h += '<b style="color:' + color + '; text-transform:uppercase; font-size:11px;">' +
                            escHtml(f.severity || '') + '</b> ';
                        if (f.package_label) h += '<span class="acciones-hint">[' + escHtml(f.package_label) + '] </span>';
                        h += '<span class="acciones-hint">(' + escHtml(f.collector_id || '') + ')</span><br>';
                        h += escHtml(f.message || '');
                        if (f.solutions && f.solutions.length) {
                            h += '<ul style="margin:4px 0 0 16px;">';
                            f.solutions.forEach(s => { h += '<li style="font-size:12px;">' + escHtml(s) + '</li>'; });
                            h += '</ul>';
                        }
                        h += '</div>';
                    });
                    if (d.recommendations && d.recommendations.length) {
                        h += '<div style="margin-top:6px;"><b>Recomendaciones:</b><ul style="margin:4px 0 0 16px;">';
                        d.recommendations.forEach(rc => { h += '<li style="font-size:12px;">' + escHtml(rc) + '</li>'; });
                        h += '</ul></div>';
                    }
                    if (d.colectores && d.colectores.length) {
                        h += '<div class="acciones-hint" style="margin-top:6px;">Colectores: ';
                        h += d.colectores.map(c => escHtml(c.id) + ' [' + escHtml(c.status) + ']').join(' · ');
                        h += '</div>';
                    }
                    cont.innerHTML = h;
                } catch (e) {
                    cont.innerHTML = '<p class="acciones-hint">No se pudo cargar el detalle: ' + escHtml(e.message) + '</p>';
                }
            }
            cont.style.display = 'block';
            btn.textContent = 'Ocultar';
        }
        
        async function loadRegistro() {
            try {
                const r = await fetch('/api/registro');
                const d = await r.json();
                regEntradas = d.entradas || [];
                const lbl = document.querySelector('#btnRegistro .btn-label');
                if (lbl) {
                    lbl.textContent = regEntradas.length ?
                        ('Registro de análisis (' + regEntradas.length + ')') :
                        'Registro de análisis';
                }
                filterRegistro();
            } catch (e) {
                const el = document.getElementById('regLista');
                if (el) el.innerHTML = '<p class="acciones-hint">No se pudo cargar el registro.</p>';
            }
        }
        
        function filterRegistro() {
            const q = ((document.getElementById('regSearch') || {}).value || '').trim().toLowerCase();
            if (!q) { renderRegistro(regEntradas); return; }
            const lista = regEntradas.filter(e =>
                JSON.stringify(e).toLowerCase().indexOf(q) !== -1);
            renderRegistro(lista);
        }
        
        function toggleRegistro() {
            const sec = document.getElementById('registroSection');
            const btn = document.getElementById('btnRegistro');
            const abierto = sec.style.display === 'block';
            if (abierto) {
                sec.style.display = 'none';
                btn.classList.remove('btn-open');
            } else {
                loadRegistro();
                sec.style.display = 'block';
                btn.classList.add('btn-open');
                sec.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        }
        
        async function eliminarRegistro(id) {
            if (!confirm('¿Eliminar este análisis del registro?')) return;
            try {
                const r = await fetch('/api/registro?id=' + encodeURIComponent(id), {method: 'DELETE'});
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                setStatus('ready', 'Análisis eliminado del registro');
                await loadRegistro();
            } catch (e) {
                setStatus('error', 'Error al eliminar: ' + e.message);
            }
        }
        
        async function vaciarRegistro() {
            if (!regEntradas.length) return;
            if (!confirm('¿Eliminar TODOS los análisis del registro (' + regEntradas.length +
                         ')? Esta acción no se puede deshacer.')) return;
            try {
                const r = await fetch('/api/registro', {method: 'DELETE'});
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                setStatus('ready', 'Registro vaciado (' + d.eliminados + ' análisis eliminados)');
                await loadRegistro();
            } catch (e) {
                setStatus('error', 'Error al vaciar: ' + e.message);
            }
        }
        
        async function loadElevation() {
            try {
                const r = await fetch('/api/elevation');
                const d = await r.json();
                const b = document.getElementById('elevBanner');
                const rb = document.getElementById('respaldoBanner');
                if (rb) {
                    if (d.respaldo) {
                        rb.textContent = 'Aviso: la carpeta junto al ejecutable no es escribible; los datos (config/ y reports/) se guardan en ' + d.ruta_base + '.';
                        rb.style.display = 'block';
                    } else {
                        rb.style.display = 'none';
                    }
                }
                if (d.is_elevated === true) {
                    b.className = 'elev-banner ok';
                    b.innerHTML = '<b>Permisos de Administrador:</b> activos. Los colectores pueden leer inventario completo (software, discos, eventos).';
                    b.style.display = 'block';
                } else if (d.is_elevated === false) {
                    b.className = 'elev-banner warn';
                    b.innerHTML = '<b>Modo estándar:</b> algunos diagnósticos tendrán datos limitados ' +
                        '(eventos de seguridad, inventario de software). ' +
                        '<button type="button" class="elev-btn" id="elevBtn">Dar permisos de administrador</button>' +
                        '<div class="elev-msg" id="elevMsg"></div>';
                    b.style.display = 'block';
                    const eb = document.getElementById('elevBtn');
                    if (eb) eb.addEventListener('click', solicitarElevacion);
                }
            } catch (e) {}
        }

        async function solicitarElevacion() {
            const btn = document.getElementById('elevBtn');
            const msg = document.getElementById('elevMsg');
            if (btn) { btn.disabled = true; btn.textContent = 'Solicitando permisos...'; }
            if (msg) msg.textContent = '';
            try {
                const r = await fetch('/api/elevar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: '{}'
                });
                const d = await r.json();
                if (d.ok) {
                    if (msg) msg.textContent = d.mensaje || ('Se abrió otra pestaña con permisos en el puerto ' + d.puerto + '.');
                } else {
                    if (msg) msg.textContent = d.error || d.mensaje || 'No se otorgaron los permisos.';
                    if (btn) { btn.disabled = false; btn.textContent = 'Dar permisos de administrador'; }
                }
            } catch (e) {
                if (msg) msg.textContent = 'Error: ' + e.message;
                if (btn) { btn.disabled = false; btn.textContent = 'Dar permisos de administrador'; }
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            const s = document.getElementById('kbSearch');
            if (s) s.addEventListener('input', filterKb);
            ['tecnico', 'cliente', 'observaciones'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.addEventListener('input', saveForm);
            });
            document.addEventListener('change', ev => {
                const t = ev.target;
                if (t && t.id && /^(estado_|solucion_|sol_|mejora_)/.test(t.id)) saveForm();
            });
            document.addEventListener('input', ev => {
                const t = ev.target;
                if (t && t.id && /^(solucion_|mejora_coment_)/.test(t.id)) saveForm();
            });
            const kbl = document.getElementById('kbLista');
            if (kbl) kbl.addEventListener('click', ev => {
                const b = ev.target.closest('button[data-kb-idx]');
                if (!b) return;
                const e = kbRender[parseInt(b.getAttribute('data-kb-idx'), 10)];
                if (!e) return;
                if (b.classList.contains('kb-del')) {
                    deleteKb(e.id, e.titulo || e.id);
                } else {
                    openKbForm(e);
                }
            });
            loadElevation();
        });
    </script>
</body>
</html>"""


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
        body = HTML_TEMPLATE.encode("utf-8")
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
                                           "paquete_label", "sintoma", "conteos")}
                    for e in entradas
                ]
                self._json_response({"total": len(entradas), "entradas": resumen})

        elif parsed.path == "/api/full-scan":
            # API para diagnostico completo (paquetes en paralelo)
            packages = discover_packages()
            
            with ThreadPoolExecutor(max_workers=4) as pool:
                diagnostics = list(pool.map(lambda p: run_diagnostic(p.name), packages))
            
            result = {"diagnostics": diagnostics, "timestamp": datetime.now().isoformat()}
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
