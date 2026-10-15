# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Base de conocimiento local de DiagUSB.

Cada entrada describe COMO DEBE ESTAR un componente para que funcione bien
(estado esperado), por que importa, los pasos de correccion y como verificarlo.
Los sintomas y colectores solo son la puerta de entrada a cada entrada.

El archivo de datos es ``base_conocimiento.json`` (mismo directorio), en UTF-8,
y puede editarse sin tocar codigo. Si falta o esta corrupto, la base se carga
vacia y los catalogos de respaldo del informe siguen funcionando.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Base embebida (se distribuye con el codigo) y capa local editable en config/
_RUTA_EMBEBIDA = Path(__file__).with_name("base_conocimiento.json")
_RUTA_CONFIG = Path(__file__).resolve().parents[3] / "config" / "base_conocimiento.json"

_CAMPOS_ENTRADA = (
    "id", "titulo", "categoria", "colectores", "sintomas",
    "estado_esperado", "por_que_importa", "soluciones", "verificacion",
)

_indice_colector: dict[str, list[str]] = {}
_indice_sintoma: dict[str, list[str]] = {}
_por_id: dict[str, dict] = {}
_entradas: list[dict] = []
_cargada = False


def ruta_activa() -> Path:
    """Archivo vigente: la capa local config/ si existe, si no la base embebida."""
    return _RUTA_CONFIG if _RUTA_CONFIG.exists() else _RUTA_EMBEBIDA


def _leer_doc(ruta: Path) -> dict:
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("entradas"), list):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _normalizar(cruda: dict) -> dict | None:
    if not isinstance(cruda, dict) or not cruda.get("id"):
        return None
    entrada = {k: cruda.get(k) for k in _CAMPOS_ENTRADA}
    entrada["colectores"] = [str(c) for c in (entrada.get("colectores") or [])]
    entrada["sintomas"] = [str(s) for s in (entrada.get("sintomas") or [])]
    entrada["soluciones"] = [str(s) for s in (entrada.get("soluciones") or [])]
    return entrada


def _cargar(force: bool = False) -> None:
    global _cargada, _entradas, _por_id, _indice_colector, _indice_sintoma
    if _cargada and not force:
        return
    _entradas = []
    _por_id = {}
    _indice_colector = {}
    _indice_sintoma = {}
    for cruda in _leer_doc(ruta_activa()).get("entradas", []):
        entrada = _normalizar(cruda)
        if not entrada:
            continue
        _entradas.append(entrada)
        _por_id[entrada["id"]] = entrada
        for c in entrada["colectores"]:
            _indice_colector.setdefault(c, []).append(entrada["id"])
        for s in entrada["sintomas"]:
            _indice_sintoma.setdefault(s, []).append(entrada["id"])
    _cargada = True


def _doc_para_editar() -> dict:
    """Documento de trabajo para escritura: la capa local o una copia de la embebida."""
    if _RUTA_CONFIG.exists():
        doc = _leer_doc(_RUTA_CONFIG)
        if doc:
            return doc
    doc = _leer_doc(_RUTA_EMBEBIDA)
    if not doc:
        doc = {"version": 1, "entradas": []}
    return doc


def _escribir_config(doc: dict) -> None:
    _RUTA_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUTA_CONFIG, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    _cargar(force=True)


def guardar_entrada(entrada: dict) -> dict:
    """Crea o actualiza una entrada en la capa local (config/base_conocimiento.json)."""
    eid = str(entrada.get("id") or "").strip().lower()
    eid = re.sub(r"[^a-z0-9_]+", "_", eid).strip("_")
    if not eid:
        raise ValueError("La entrada requiere un id")
    if not (entrada.get("titulo") or "").strip():
        raise ValueError("La entrada requiere un titulo")
    if not (entrada.get("estado_esperado") or "").strip():
        raise ValueError("La entrada requiere el estado esperado")

    limpia = _normalizar(dict(entrada, id=eid))
    doc = _doc_para_editar()
    reemplazada = False
    for i, e in enumerate(doc.get("entradas", [])):
        if isinstance(e, dict) and e.get("id") == eid:
            doc["entradas"][i] = limpia
            reemplazada = True
            break
    if not reemplazada:
        doc.setdefault("entradas", []).append(limpia)
    _escribir_config(doc)
    return buscar(eid) or limpia


def eliminar_entrada(knowledge_id: str) -> bool:
    """Elimina una entrada de la capa local. Devuelve True si existia."""
    doc = _doc_para_editar()
    antes = len(doc.get("entradas", []))
    doc["entradas"] = [
        e for e in doc.get("entradas", [])
        if not (isinstance(e, dict) and e.get("id") == knowledge_id)
    ]
    if len(doc["entradas"]) == antes:
        return False
    _escribir_config(doc)
    return True


def entradas() -> list[dict]:
    """Todas las entradas de la base, en orden de archivo."""
    _cargar()
    return list(_entradas)


def version() -> int:
    _cargar()
    try:
        with open(ruta_activa(), "r", encoding="utf-8") as fh:
            return int(json.load(fh).get("version", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def buscar(knowledge_id: str | None) -> dict | None:
    """Entrada por su id explicito."""
    if not knowledge_id:
        return None
    _cargar()
    return _por_id.get(knowledge_id)


def por_colector(collector_id: str | None) -> list[dict]:
    """Entradas relacionadas con un colector dado."""
    if not collector_id:
        return []
    _cargar()
    return [e for eid in _indice_colector.get(collector_id, []) if (e := _por_id.get(eid))]


def por_sintoma(symptom: str | None) -> list[dict]:
    """Entradas relacionadas con un sintoma dado."""
    if not symptom:
        return []
    _cargar()
    return [e for eid in _indice_sintoma.get(symptom, []) if (e := _por_id.get(eid))]


def para_finding(finding: Any) -> dict | None:
    """Resuelve la entrada de conocimiento de un finding.

    Prefiere el ``knowledge_id`` explicito; si no tiene, busca por el
    ``collector_id`` del finding (la regla mas comun).
    """
    kid = getattr(finding, "knowledge_id", "") or ""
    e = buscar(kid)
    if e:
        return e
    candidatas = por_colector(getattr(finding, "collector_id", "") or "")
    if not candidatas:
        return None
    return candidatas[0]


def knowledge_json(finding: Any) -> dict | None:
    """Representacion JSON de la entrada de un finding (o None si no hay)."""
    return entrada_json(para_finding(finding))


def entrada_json(entrada: dict | None) -> dict | None:
    """Representacion JSON estandar de una entrada de la base."""
    if not isinstance(entrada, dict):
        return None
    return {
        "id": entrada.get("id", ""),
        "titulo": entrada.get("titulo", ""),
        "categoria": entrada.get("categoria", ""),
        "estado_esperado": entrada.get("estado_esperado", ""),
        "por_que_importa": entrada.get("por_que_importa", ""),
        "soluciones": list(entrada.get("soluciones") or []),
        "verificacion": entrada.get("verificacion", ""),
    }


def soluciones_de(finding: Any) -> list[str]:
    """Pasos de correccion de la entrada del finding (lista vacia si no hay)."""
    e = para_finding(finding)
    return list(e.get("soluciones") or []) if e else []


def attach_knowledge(findings: list[Any]) -> None:
    """Asigna ``knowledge_id`` a los findings que no lo traigan explicito."""
    for f in findings:
        if getattr(f, "knowledge_id", ""):
            continue
        candidatas = por_colector(getattr(f, "collector_id", "") or "")
        if candidatas:
            f.knowledge_id = candidatas[0].get("id", "")
