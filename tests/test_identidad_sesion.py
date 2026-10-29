# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Identidad por sesion (core.identidad_sesion) y su cableado.

Todos los valores son inventados: ningun serial ni UUID real va al repo.
"""
import json
from pathlib import Path

import pytest

from diagusb import web_server as ws
from diagusb.core import identidad_sesion as ids

DATOS_ALTA = {
    "identidad": {"smbios_uuid": "UUID-PRUEBA-A1",
                  "machine_guid": "GUID-PRUEBA-ZZ",
                  "disco_arranque": "DISCO-PRUEBA-55"},
    "bios": [{"serial_number": "BIO-PRUEBA-77"}],
}
CRUDOS = ("UUID-PRUEBA-A1", "BIO-PRUEBA-77", "DISCO-PRUEBA-55", "GUID-PRUEBA-ZZ")


def _raw(data, nombre="PC-PRUEBA", estado="ok"):
    return {"query": {"status": estado}, "context": {"computer_name": nombre},
            "data": data}


class Runner:
    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas = 0

    def __call__(self, ruta, timeout=30):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.respuesta


def _reset():
    ids._CACHE.update(valor=None, hasta=0.0)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    _reset()
    monkeypatch.setattr(ids.integridad, "verificar", lambda ruta: (True, ""))
    monkeypatch.setattr(ids.integridad, "localizar_common", lambda ruta: None)
    yield
    _reset()


def test_fuerte_alta_sin_fugas():
    r = ids.para_diag(Runner(_raw(DATOS_ALTA)))
    assert r["nivel"] == "fuerte" and r["calidad"] == "alta"
    assert r["id"].startswith("dgu-")
    assert r["id_corto"].startswith("DGU-") and len(r["id_corto"]) == 13
    assert r["computer_name"] == "PC-PRUEBA"
    assert "error" not in r
    texto = json.dumps(r).lower()
    for crudo in CRUDOS:
        assert crudo.lower() not in texto


def test_data_como_lista_o_dict():
    a = ids.para_diag(Runner(_raw(DATOS_ALTA)))
    _reset()
    b = ids.para_diag(Runner(_raw([DATOS_ALTA])))
    assert a["id"] == b["id"] != ""


def test_una_sola_lectura_por_sesion():
    runner = Runner(_raw(DATOS_ALTA))
    ids.para_diag(runner)
    ids.para_diag(runner)
    assert runner.llamadas == 1


def test_error_se_ve_y_reintenta(monkeypatch):
    monkeypatch.setattr(ids, "_REINTENTO_S", 0.0)
    a = ids.para_diag(Runner(error=RuntimeError("x")))
    assert a["nivel"] == "ninguno" and a["id"] == "" and a["error"] is True
    assert "No se pudo leer" in a["aviso"]
    runner = Runner(_raw(DATOS_ALTA))
    b = ids.para_diag(runner)
    assert b["nivel"] == "fuerte" and runner.llamadas == 1


def test_error_se_cachea_un_rato():
    runner = Runner(error=RuntimeError("x"))
    ids.para_diag(runner)
    ids.para_diag(runner)
    assert runner.llamadas == 1


def test_estado_error_del_colector():
    r = ids.para_diag(Runner(_raw({}, estado="error")))
    assert r["nivel"] == "ninguno" and "estado error" in r["aviso"]
    assert "No se pudo leer" in r["aviso"]


def test_integridad_fallida_no_ejecuta(monkeypatch):
    monkeypatch.setattr(ids.integridad, "verificar", lambda ruta: (False, "x"))
    runner = Runner(_raw(DATOS_ALTA))
    r = ids.para_diag(runner)
    assert runner.llamadas == 0
    assert r["nivel"] == "ninguno" and "No se pudo leer" in r["aviso"]


def test_debil_por_respaldos():
    datos = {"identidad": {"smbios_uuid": "To Be Filled By O.E.M.",
                           "disco_arranque": "DISCO-PRUEBA-55"}}
    r = ids.para_diag(Runner(_raw(datos)))
    assert r["nivel"] == "debil"
    assert r["id"].startswith("dgw-") and r["id_corto"].startswith("DGW-")
    assert "d\u00e9bil" in r["aviso"]
    assert "disco-prueba-55" not in json.dumps(r).lower()


def test_sin_datos_unicos():
    datos = {"identidad": {"smbios_uuid": "To Be Filled By O.E.M."}}
    r = ids.para_diag(Runner(_raw(datos)))
    assert r["nivel"] == "ninguno" and r["id"] == ""
    assert "No se pudo identificar" in r["aviso"]
    assert "error" not in r


def test_respuesta_basura_no_rompe():
    for basura in (None, "texto", [], 42):
        _reset()
        r = ids.para_diag(Runner(basura))
        assert r["nivel"] == "ninguno" and r["error"] is True


def test_resumen_registro_solo_campos_seguros():
    ident = {"id": "dgu-0123456789abcdef", "id_corto": "DGU-0123-4567",
             "nivel": "fuerte", "calidad": "alta", "computer_name": "PC-PRUEBA",
             "aviso": "x", "componentes": {"smbios_uuid": "UUID-PRUEBA-A1"}}
    res = ids.resumen_registro(ident)
    assert set(res) == {"id", "computer_name", "id_corto", "nivel", "calidad"}
    assert "UUID-PRUEBA-A1" not in json.dumps(res)
    assert ids.resumen_registro(None) == {}


def test_registro_lleva_identidad():
    ident = {"id": "dgu-0123456789abcdef", "id_corto": "DGU-0123-4567",
             "nivel": "fuerte", "calidad": "alta", "computer_name": "PC-PRUEBA"}
    diag = {"identidad": ident, "results": [], "findings": [],
            "package": "temperatura", "package_label": "Temperatura"}
    entrada = ws._entrada_registro(diag, "paquete")
    assert entrada["identidad"]["id_corto"] == "DGU-0123-4567"


def test_cableado_web_server():
    src = Path(ws.__file__).read_text(encoding="utf-8", errors="replace")
    assert src.count("identidad_sesion.para_diag(run_powershell)") == 3
    assert 'parsed.path == "/api/identidad"' in src


def test_cableado_informe():
    ruta = Path(ws.__file__).parent / "core" / "informe.py"
    src = ruta.read_text(encoding="utf-8", errors="replace")
    assert 'equipo["id_equipo"]' in src
    assert '("ID del equipo", _g(eq.get("id_equipo")))' in src


def test_cableado_interfaz():
    st = Path(ws.__file__).parent / "static"
    js = (st / "app.js").read_text(encoding="utf-8", errors="replace")
    html = (st / "index.html").read_text(encoding="utf-8", errors="replace")
    css = (st / "app.css").read_text(encoding="utf-8", errors="replace")
    assert "function loadIdentidad" in js and "loadIdentidad();" in js
    assert "data.identidad.id_corto" in js
    assert 'id="identidadBanner"' in html
    assert ".identidad-banner" in css