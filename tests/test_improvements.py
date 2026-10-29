# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de las mejoras: agrupacion, reglas nuevas, informe, KB editable y contadores."""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from validar_pdf import validar_pdf

from diagusb.core import knowledge_base as kb
from diagusb.core.informe import (
    InformeColector,
    InformeData,
    InformeProblema,
    _fmt_fecha,
    _resumen_datos,
    codigo_verificacion,
    html_de_doc,
    informe_a_doc,
    informe_a_html,
    informe_a_pdf,
    informe_desde_diagnostico,
    linea_alcance,
)
from diagusb.core.models import CollectorResult, ContextInfo, Finding, QueryInfo
from diagusb.core.rules import RuleEngine, _agrupar_findings
from diagusb.__main__ import _obs_a_dict


def _abrir_servidor():
    import threading
    import socketserver
    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _cookie():
    import diagusb.web_server as ws
    return {"Cookie": f"diagusb_token={ws._token_sesion()}"}



def create_mock_result(collector_id: str, data: list | dict, status: str = "ok") -> CollectorResult:
    return CollectorResult(
        schema_version=1,
        collector_id=collector_id,
        captured_at_utc=datetime.utcnow().isoformat(),
        query={"status": status, "duration_ms": 100, "timeout_seconds": 15},
        context={},
        metadata={},
        data=data,
        errors=[],
        notes=[],
    )


# ---------------------------------------------------------------------------
# Agrupacion de findings
# ---------------------------------------------------------------------------

def test_agrupa_mismo_problema():
    fs = [
        Finding(severity="warning", collector_id="logical_disks",
                message="Espacio limitado en disco C: 15.0% libre", details={}),
        Finding(severity="warning", collector_id="logical_disks",
                message="Espacio limitado en disco D: 12.0% libre", details={}),
        Finding(severity="critical", collector_id="logical_disks",
                message="Espacio crítico en E: 5.0% libre", details={}),
    ]
    out = _agrupar_findings(fs)
    assert len(out) == 2, f"esperaba 2 grupos, obtuve {len(out)}"
    adv = [f for f in out if f.severity == "warning"][0]
    assert adv.details["grupo_total"] == 2
    assert len(adv.details["grupo_mensajes"]) == 2
    assert adv.message.startswith("Espacio limitado en disco C:")


def test_agrupa_sin_repetidos_no_altera():
    fs = [
        Finding(severity="error", collector_id="critical_events",
                message="1 evento(s) críticos", details={}),
    ]
    out = _agrupar_findings(fs)
    assert len(out) == 1
    assert "grupo_total" not in (out[0].details or {})


def test_diagnose_symptoms_agrupa():
    from diagusb.core.rules import diagnose_symptoms
    r1 = create_mock_result("critical_services",
                            [{"services": [{"name": "SpSvc", "state": "Stopped",
                                            "start_mode": "Auto"}]}])
    findings, _ = diagnose_symptoms(["servicio_detenido"], [r1])
    # la regla de servicios fallidos puede emitir varios mensajes del mismo
    # problema (uno por servicio): deben quedar agrupados en uno solo
    if len(findings) > 1:
        assert "grupo_total" in (findings[0].details or {})


# ---------------------------------------------------------------------------
# Reglas nuevas
# ---------------------------------------------------------------------------

def test_updates_pendientes_con_criticas():
    engine = RuleEngine()
    r = create_mock_result("pending_updates", {
        "status": "ok",
        "actualizaciones_pendientes": 3,
        "actualizaciones": [
            {"kb": "KB5000001", "titulo": "Actualización A", "importancia": "Critical"},
            {"kb": "KB5000002", "titulo": "Actualización B", "importancia": "Low"},
            {"kb": "KB5000003", "titulo": "Actualización C", "importancia": "Crítica"},
        ],
    })
    findings = engine._check_pending_updates([r])
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].details["pendientes"] == 3
    assert findings[0].details["criticas"] == 2


def test_updates_pendientes_sin_criticas():
    engine = RuleEngine()
    r = create_mock_result("pending_updates", {
        "status": "ok",
        "actualizaciones_pendientes": 1,
        "actualizaciones": [{"kb": "KB5000009", "titulo": "Opcional", "importancia": "Low"}],
    })
    findings = engine._check_pending_updates([r])
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_updates_sin_pendientes():
    engine = RuleEngine()
    r = create_mock_result("pending_updates", {"status": "ok", "actualizaciones_pendientes": 0})
    assert engine._check_pending_updates([r]) == []


def test_wifi_senal_debil():
    engine = RuleEngine()
    r = create_mock_result("wifi_networks", [
        {"ssid": "Casa", "connected": True, "signal": 25},
        {"ssid": "Oficina", "connected": False, "signal": [80, 75]},
    ])
    findings = engine._check_wifi_signal([r])
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "Casa" in findings[0].message
    assert "Oficina" not in findings[0].message


def test_wifi_senal_fuerte():
    engine = RuleEngine()
    r = create_mock_result("wifi_networks", [
        {"ssid": "Casa", "connected": True, "signal": [90, 85]}
    ])
    assert engine._check_wifi_signal([r]) == []


def test_bsod_reciente_error():
    engine = RuleEngine()
    ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    r = create_mock_result("bsod_events", [{"time_created": ts}])
    findings = engine._check_bsod_events([r])
    assert len(findings) == 1
    assert findings[0].severity == "error"


def test_bsod_viejo_warning():
    engine = RuleEngine()
    ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    r = create_mock_result("bsod_events", [{"time_created": ts}])
    findings = engine._check_bsod_events([r])
    assert len(findings) == 1
    assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# Informe: diferencias, grupo y resumen humano
# ---------------------------------------------------------------------------

def _diag_minimo():
    return {
        "package": "disco",
        "package_label": "Disco",
        "symptom": "disco_lleno",
        "results": [
            {"collector_id": "logical_disks", "query": {"status": "ok", "duration_ms": 12},
             "data": [{"device_id": "C:", "free_percent": 12.4}]},
            {"collector_id": "physical_disks", "query": {"status": "ok", "duration_ms": 9},
             "data": [{"friendly_name": "SSD 1TB", "media_type": "SSD", "temperature": 36}]},
        ],
        "findings": [
            {"severity": "warning", "collector_id": "logical_disks",
             "message": "Espacio limitado en disco C: 12.4% libre",
             "details": {"grupo_total": 2, "grupo_mensajes": [
                 "Espacio limitado en disco C: 12.4% libre",
                 "Espacio limitado en disco D: 9.0% libre"]}},
        ],
        "improvements": [],
        "recommendations": ["Advertencias detectadas."],
    }


def test_informe_diferencias_y_grupo():
    difs = [{"collector_id": "logical_disks", "field_path": "C.free_percent",
             "baseline_value": 30.0, "current_value": 12.4}]
    inf = informe_desde_diagnostico(_diag_minimo(), diferencias=difs)
    assert len(inf.diferencias) == 1
    assert len(inf.problemas) == 1
    assert len(inf.problemas[0].grupo) == 1

    html = informe_a_html(inf, con_anexo=False)
    assert "Otros casos del mismo problema" in html
    assert "Espacio limitado en disco D: 9.0% libre" in html

    pdf = informe_a_pdf(inf)
    assert pdf.startswith(b"%PDF")
    texto = pdf.decode("latin-1", errors="replace")
    assert "Otros casos del mismo problema" in texto
    assert "Espacio limitado en disco C" in texto


def test_informe_sin_diferencias():
    inf = informe_desde_diagnostico(_diag_minimo())
    assert inf.diferencias == []
    html = informe_a_html(inf, con_anexo=False)
    assert "Cambios detectados" not in html


def test_resumen_datos_humano():
    lineas = _resumen_datos([{"device_id": "C:", "free_percent": 34.0, "size_gb": 512}],
                            "logical_disks")
    assert any("C:" in l and "34%" in l for l in lineas), lineas
    lineas = _resumen_datos([{"device_name": "a"}, {"device_name": "b"}], "installed_software")
    assert lineas == ["Software instalado: 2 aplicaciones"]
    lineas = _resumen_datos({"physical_memory_usage_percent": 61.5}, "memory_status")
    assert lineas == ["Uso de memoria física: 62%"]


def test_fmt_fecha_informe():
    assert _fmt_fecha("2026-10-15T18:48:23.123456") == "15/10/2026 18:48"
    assert _fmt_fecha("2026-10-15T18:48:23") == "15/10/2026 18:48"
    assert _fmt_fecha("2026-10-15T18:48:23.123456+00:00") == "15/10/2026 18:48"
    assert _fmt_fecha("") == ""
    assert _fmt_fecha(None) == ""
    assert _fmt_fecha("no-es-fecha") == "no-es-fecha"


def _numeros_seccion_html(html):
    return [int(n) for n in re.findall(r"<h2>(\d+)\.", html)]


def test_informe_secciones_correlativas():
    inf = informe_desde_diagnostico(_diag_minimo())
    html = informe_a_html(inf, con_anexo=False)
    nums = _numeros_seccion_html(html)
    assert nums == list(range(1, len(nums) + 1)), nums
    assert nums[-1] == 9
    assert "1. Datos del servicio" in html
    assert "9. Cierre" in html

    sin_reco = informe_desde_diagnostico(_diag_minimo())
    sin_reco.recomendaciones = []
    html2 = informe_a_html(sin_reco, con_anexo=False)
    assert _numeros_seccion_html(html2) == list(range(1, 10))


def test_doc_css_y_anexo_opcional():
    inf = informe_desde_diagnostico(_diag_minimo())
    resultados = [{"collector_id": "logical_disks", "data": 1}]
    texto = html_de_doc(informe_a_doc(inf, resultados_completos=resultados)).decode("utf-8")
    for regla in ("table-layout:fixed", "word-wrap:break-word", ".mono",
                  "Consolas", ".muted", ".firma", ".badge", "border-collapse:collapse"):
        assert regla in texto, regla
    assert "xmlns:w='urn:schemas-microsoft-com:office:word'" in texto
    assert "Datos crudos de los colectores" not in texto

    con = html_de_doc(informe_a_doc(inf, resultados_completos=resultados, con_anexo=True)).decode("utf-8")
    assert "Datos crudos de los colectores" in con
    assert "collector_id" in con


def test_pdf_fecha_y_secciones():
    inf = informe_desde_diagnostico(_diag_minimo())
    inf.generado_en = "2026-10-15T18:48:23.123456"
    texto = informe_a_pdf(inf).decode("latin-1", errors="replace")
    assert "15/10/2026 18:48" in texto
    secciones = ["Datos del servicio", "Indicadores", "Resumen ejecutivo",
                 "Panel gr", "Problemas detectados", "Plan de acci",
                 "Ficha t", "Anexo t", "Cierre"]
    for n, frag in enumerate(secciones, 1):
        assert f"{n}. {frag}" in texto, (n, frag)
    assert "Página 2 de" in texto


def _diag_con_metricas():
    diag = _diag_minimo()
    diag["metricas"] = {
        "version_formula": 1,
        "puntaje": 69,
        "etiqueta": "Atención",
        "alcance": "Paquete Disco",
        "leyenda": "Puntaje orientativo del paquete.",
        "cobertura": {"porcentaje": 80.0, "colectores_ok": 8,
                      "colectores_ejecutados": 10},
        "severidad": {"critical": 1, "error": 2, "warning": 3, "ok": 9},
        "categorias": [{"paquete": "Disco", "ok": 2, "advertencia": 1,
                        "error": 0, "no_evaluado": 0}],
        "medidores": {"memoria": {"usado_porcentaje": 61.5},
                      "discos": [{"unidad": "C:", "usado_porcentaje": 87.6}]},
    }
    return diag


def test_informe_grafico_html_doc_pdf():
    diag = _diag_con_metricas()
    inf = informe_desde_diagnostico(
        diag,
        metricas_base={"puntaje": 100, "etiqueta": "Bueno"},
        metricas_actual={"puntaje": 69, "etiqueta": "Atención"},
    )
    assert inf.metricas["puntaje"] == 69
    assert inf.metricas_base["puntaje"] == 100

    html = informe_a_html(inf, con_anexo=False)
    assert "4. Panel gráfico" in html
    assert "69/100" in html
    assert "<svg" in html
    assert "Problemas por severidad" in html
    assert "Estado por paquete" in html
    assert "Disco C:" in html
    assert "Comparación antes / después" in html

    doc = html_de_doc(informe_a_doc(inf, resultados_completos=diag["results"])).decode("utf-8")
    assert "Panel gráfico" in doc
    assert "69/100" in doc
    assert "bgcolor=" in doc
    assert "<svg" not in doc

    pdf = informe_a_pdf(inf).decode("latin-1", errors="replace")
    assert "Panel gr" in pdf
    assert "69/100" in pdf
    assert "Memoria en uso" in pdf


def test_informe_grafico_sin_metricas():
    inf = informe_desde_diagnostico(_diag_minimo())
    assert inf.metricas == {}
    html = informe_a_html(inf, con_anexo=False)
    assert "4. Panel gráfico" in html
    assert "Sin datos para graficar." in html
    pdf = informe_a_pdf(inf).decode("latin-1", errors="replace")
    assert "Sin datos para graficar." in pdf


def test_pdf_panel_omite_graficos_vacios():
    diag = _diag_con_metricas()
    diag["metricas"]["severidad"] = {}
    diag["metricas"]["medidores"] = {}
    diag["metricas"]["estados"] = {"ok": 1}
    inf = informe_desde_diagnostico(diag)
    pdf = informe_a_pdf(inf).decode("latin-1", errors="replace")
    assert "(Estado de los colectores) Tj" in pdf
    assert "(Problemas por severidad) Tj" not in pdf
    assert "(Memoria) Tj" not in pdf
    assert "(Memoria en uso) Tj" not in pdf


def test_api_report_incluye_grafico():
    import urllib.request

    diag = _diag_con_metricas()
    cuerpo = json.dumps({
        "diagnostico": diag,
        "metricas_base": {"puntaje": 100, "etiqueta": "Bueno"},
        "metricas_actual": {"puntaje": 69, "etiqueta": "Atención"},
    }).encode("utf-8")
    httpd, base = _abrir_servidor()
    try:
        for fmt, codec in (("doc", "utf-8"), ("pdf", "latin-1")):
            cabeceras = dict(_cookie())
            cabeceras["Content-Type"] = "application/json"
            req = urllib.request.Request(
                base + "/api/report?format=" + fmt, data=cuerpo,
                headers=cabeceras, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200, resp.status
                datos = resp.read()
            if fmt == "pdf":
                assert datos[:4] == b"%PDF"
                texto = datos.decode(codec, errors="replace")
            else:
                assert b"multipart/related" in datos[:200]
                assert b"<html" in html_de_doc(datos)
                texto = html_de_doc(datos).decode(codec, errors="replace")
            assert "Panel gr" in texto, fmt
            assert ("Cobertura" in texto) or ("COBERTURA" in texto), fmt
            assert "Comparación antes" in texto, fmt
            assert "/100" in texto, fmt
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_api_report_metricas_recalculadas():
    import urllib.request

    diag = _diag_minimo()
    diag["metricas"] = {"puntaje": 999, "etiqueta": "<script>alert(1)</script>"}
    cuerpo = json.dumps({
        "diagnostico": diag,
        "metricas_base": {"puntaje": 999, "etiqueta": "<script>x</script>"},
        "metricas_actual": {"puntaje": -5, "severidad": {"error": 3}},
    }).encode("utf-8")
    httpd, base = _abrir_servidor()
    try:
        for fmt, codec in (("doc", "utf-8"), ("pdf", "latin-1")):
            cabeceras = dict(_cookie())
            cabeceras["Content-Type"] = "application/json"
            req = urllib.request.Request(
                base + "/api/report?format=" + fmt, data=cuerpo,
                headers=cabeceras, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200, resp.status
                datos = resp.read()
            texto = html_de_doc(datos).decode(codec, errors="replace")
            assert "999/100" not in texto, fmt
            assert "<script>" not in texto, fmt
            assert "&lt;script&gt;" not in texto, fmt
            assert "97/100" in texto, fmt
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# Base de conocimiento editable (capa local en un archivo temporal)
# ---------------------------------------------------------------------------
def test_informe_cifras_coherentes():
    import diagusb.web_server as ws
    from diagusb.core.metricas import ESTADOS

    diag = {
        "package": "full-scan", "package_label": "Revisión Total",
        "symptom": "revision_total",
        "results": [
            {"collector_id": "system_context", "query": {"status": "ok"}, "data": []},
            {"collector_id": "bsod_events", "query": {"status": "empty"}, "data": []},
            {"collector_id": "printers", "query": {"status": "ok"}, "data": []},
            {"collector_id": "security_events", "query": {"status": "denied"}, "data": []},
        ],
        "findings": [
            {"severity": "critical", "collector_id": "printers", "message": "c",
             "details": {}},
            {"severity": "warning", "collector_id": "system_context", "message": "w",
             "details": {}},
        ],
    }
    m = ws._metricas_de_reporte(diag)
    inf = informe_desde_diagnostico({**diag, "metricas": m})
    html = informe_a_html(inf)
    pdf = informe_a_pdf(inf).decode("latin-1", errors="replace")

    cob = m["cobertura"]
    # Una sola definicion: estados suman los ejecutados y derivan la cobertura.
    assert sum(m["estados"][e] for e in ESTADOS) == cob["colectores_ejecutados"]
    assert cob["colectores_evaluados"] == cob["colectores_ok"] + cob["colectores_sin_datos"]
    assert cob["porcentaje"] == round(
        cob["colectores_evaluados"] / cob["colectores_ejecutados"] * 100, 1)
    # Documento y PDF muestran la misma cobertura y los mismos estados.
    assert "2. Indicadores" in html
    assert f"{cob['porcentaje']}%" in html, html[:500]
    assert f"{m['estados']['ok']} OK" in html
    assert f"{cob['porcentaje']}%" in pdf
    assert f"{m['estados']['ok']} OK" in pdf
    # La severidad del documento sale de los mismos hallazgos.
    assert int(m["severidad"]["critical"]) == 1
    assert int(m["severidad"]["warning"]) == 1
    total_hall = {"critical": 0, "error": 0, "warning": 0}
    for c in m["categorias"]:
        for k in total_hall:
            total_hall[k] += (c.get("hallazgos") or {}).get(k, 0)
    assert total_hall == {"critical": 1, "error": 0, "warning": 1}


def test_informe_recomendaciones_coherentes():
    import diagusb.web_server as ws

    diag = {
        "package": "full-scan", "package_label": "Revisión Total",
        "results": [{"collector_id": "printers", "query": {"status": "ok"},
                     "data": []}],
        "findings": [{"severity": "critical", "collector_id": "printers",
                      "message": "c", "details": {}}],
        "recommendations": ["No se detectaron problemas obvios.",
                            "Problema crítico detectado. Requiere atención inmediata."],
    }
    m = ws._metricas_de_reporte(diag)
    inf = informe_desde_diagnostico({**diag, "metricas": m})
    inf.recomendaciones = __import__("diagusb.core.metricas", fromlist=["x"]) \
        .recomendaciones_de(m["severidad"])
    html = informe_a_html(inf)
    assert "No se detectaron problemas obvios." not in html
    assert "Problema crítico detectado. Requiere atención inmediata." in html


def test_kb_guardar_y_eliminar():
    tmp_dir = Path(tempfile.mkdtemp(prefix="diagusb_kb_"))
    tmp = tmp_dir / "base_conocimiento.json"
    old = kb._RUTA_CONFIG
    kb._RUTA_CONFIG = tmp
    try:
        guardada = kb.guardar_entrada({
            "id": "Prueba Demo",
            "titulo": "Entrada de prueba",
            "estado_esperado": "Debe pasar esta prueba",
            "colectores": ["spooler_service"],
            "soluciones": ["Paso uno", "Paso dos"],
        })
        assert guardada["id"] == "prueba_demo"
        assert kb.buscar("prueba_demo") is not None
        assert tmp.exists()

        # actualizacion de la misma entrada (no duplica)
        kb.guardar_entrada({
            "id": "prueba_demo",
            "titulo": "Entrada de prueba editada",
            "estado_esperado": "Debe seguir pasando",
        })
        assert len([e for e in kb.entradas() if e["id"] == "prueba_demo"]) == 1
        assert kb.buscar("prueba_demo")["titulo"] == "Entrada de prueba editada"

        assert kb.eliminar_entrada("prueba_demo") is True
        assert kb.buscar("prueba_demo") is None
        assert kb.eliminar_entrada("prueba_demo") is False
    finally:
        kb._RUTA_CONFIG = old
        kb._cargar(force=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_kb_valida_campos():
    tmp_dir = Path(tempfile.mkdtemp(prefix="diagusb_kb_"))
    tmp = tmp_dir / "base_conocimiento.json"
    old = kb._RUTA_CONFIG
    kb._RUTA_CONFIG = tmp
    try:
        for entrada in ({"id": "", "titulo": "x", "estado_esperado": "y"},
                        {"id": "sin_titulo", "titulo": "  ", "estado_esperado": "y"},
                        {"id": "sin_estado", "titulo": "ok", "estado_esperado": " "}):
            try:
                kb.guardar_entrada(entrada)
                raise AssertionError(f"debió rechazar {entrada}")
            except ValueError:
                pass
    finally:
        kb._RUTA_CONFIG = old
        kb._cargar(force=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_kb_embebida_intacta():
    ids = {e["id"] for e in kb.entradas()}
    assert "wifi_debil" in ids and "servicio_automatico_detenido" in ids
    assert "cpu_caliente" in ids
    entrada = kb.buscar("wifi_debil")
    assert "40%" in entrada["estado_esperado"]


# ---------------------------------------------------------------------------
# Contadores del servidor web (ok / error / empty) con PowerShell simulado
# ---------------------------------------------------------------------------

def test_run_diagnostic_contadores():
    import diagusb.web_server as ws
    from diagusb.core import integridad

    # Hermético: el test no depende de manifiesto_hashes.json (ignorado por git).
    contador = {"i": 0}

    def fake_powershell(script_path, timeout=30):
        i = contador["i"]
        contador["i"] += 1
        status = ("ok", "empty", "error")[i % 3]
        return {"collector_id": f"c{i}", "query": {"status": status},
                "data": {}, "errors": []}

    n = len(list((Path(ws.__file__).parent / "packages" / "servicios"
                  / "collectors").glob("*.ps1")))
    assert n >= 3, "el paquete servicios debe tener al menos 3 colectores"

    original_powershell = ws.run_powershell
    original_verificar = integridad.verificar
    ws.run_powershell = fake_powershell
    integridad.verificar = lambda ruta: (True, "")
    try:
        diag = ws.run_diagnostic("servicios")
    finally:
        ws.run_powershell = original_powershell
        integridad.verificar = original_verificar

    assert not diag.get("error"), diag.get("error")
    assert diag["collectors_count"] == n
    esperados_ok = sum(1 for i in range(n) if i % 3 == 0)
    esperados_empty = sum(1 for i in range(n) if i % 3 == 1)
    esperados_error = sum(1 for i in range(n) if i % 3 == 2)
    assert diag["ok_count"] == esperados_ok
    assert diag["empty_count"] == esperados_empty
    assert diag["error_count"] == esperados_error
    assert isinstance(diag.get("is_elevated"), (bool, type(None)))


def test_progreso_diagnostico():
    import diagusb.web_server as ws

    ws._progreso_reiniciar("paquete", "Demo", [("demo", "Demo", 2)])
    try:
        ws._progreso_iniciar_paquete("demo", "Demo", 2)
        ws._progreso_actual("demo", "get_uno")
        estado = ws._progreso_snapshot()
        assert estado["activo"] is True
        assert estado["total"] == 2
        assert estado["completados"] == 0
        assert estado["actual"] == "get_uno"

        ws._progreso_completado("demo")
        estado = ws._progreso_snapshot()
        assert estado["completados"] == 1
        assert estado["porcentaje"] == 50

        ws._progreso_paquete_fin("demo")
        estado = ws._progreso_snapshot()
        assert estado["activo"] is False
        assert estado["completados"] == 2
        assert estado["porcentaje"] == 100
        assert estado["paquetes"][0]["estado"] == "completado"
    finally:
        ws._progreso_reiniciar("", "", [])


def test_procesos_sin_ventana():
    import os
    import subprocess
    from diagusb.core.procesos import opciones_sin_ventana

    opciones = opciones_sin_ventana()
    if os.name == "nt":
        assert opciones["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert opciones["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    else:
        assert opciones == {}


def test_elevation_comando_y_desactivacion():
    import os
    from diagusb.core import elevation as elev

    cmd = elev.comando_relanzable("diagusb")
    assert "-m" in cmd and "diagusb" in cmd, cmd
    assert cmd[0] == sys.executable, cmd

    assert isinstance(elev.is_elevado(), bool)

    assert not elev.desactivada()
    os.environ[elev.DESACTIVADA_ENV] = "1"
    try:
        assert elev.desactivada()
    finally:
        del os.environ[elev.DESACTIVADA_ENV]
    assert not elev.desactivada()


def test_elevation_rechazo_uac():
    from diagusb.core import elevation as elev

    original = elev._lanzar_elevado
    elev._lanzar_elevado = lambda comando: None
    try:
        assert elev.elevar_cli(["x"]) is None
        assert elev.elevar_servidor(["x"], 8080, timeout=0.1) is False
    finally:
        elev._lanzar_elevado = original


def test_elevation_hijo_terminado():
    from diagusb.core import elevation as elev

    orig = (elev._lanzar_elevado, elev._proceso_vivo, elev._esperar_codigo,
            elev.puerto_en_uso)
    elev._lanzar_elevado = lambda comando: 1234
    elev._proceso_vivo = lambda handle, ms: False
    elev._esperar_codigo = lambda handle: 0
    elev.puerto_en_uso = lambda puerto: False
    try:
        assert elev.elevar_cli(["x"]) == 0
        assert elev.elevar_servidor(["x"], 8080, timeout=5.0) is False
    finally:
        (elev._lanzar_elevado, elev._proceso_vivo, elev._esperar_codigo,
         elev.puerto_en_uso) = orig


def test_elevation_hijo_sirve_puerto():
    from diagusb.core import elevation as elev

    orig = (elev._lanzar_elevado, elev.puerto_en_uso)
    elev._lanzar_elevado = lambda comando: 1
    elev.puerto_en_uso = lambda puerto: True
    try:
        assert elev.elevar_servidor(["x"], 8080, timeout=1.0) is True
    finally:
        elev._lanzar_elevado, elev.puerto_en_uso = orig


def test_outdated_drivers_advertencias_y_genericos():
    from diagusb.core.rules import RuleEngine

    engine = RuleEngine()
    drivers = [
        {"device_name": "Adaptador de video basico", "reasons": ["generico"],
         "config_error_code": 0},
        {"device_name": "Chipset antiguo", "reasons": ["antiguo"], "config_error_code": 0},
        {"device_name": "WiFi roto", "reasons": ["advertencia"], "config_error_code": 43,
         "config_error_text": "Windows ha detenido el dispositivo porque ha informado de problemas"},
        {"device_name": "Controlador sin driver", "reasons": ["advertencia", "antiguo"],
         "config_error_code": 28, "config_error_text": "Los controladores no estan instalados"},
    ]
    obs = [create_mock_result("outdated_drivers", drivers)]
    findings = engine._check_outdated_drivers(obs)

    errores = [f for f in findings if f.severity == "error"]
    avisos = [f for f in findings if f.severity == "warning"]
    assert len(errores) == 1, findings
    assert len(avisos) == 1, findings

    assert errores[0].details["total"] == 2
    assert errores[0].details["codigos"] == [28, 43]
    assert "2 dispositivo(s) con advertencia" in errores[0].message
    assert any("código 43" in e for e in errores[0].details["primeros"])

    assert avisos[0].details["genericos"] == 1
    assert avisos[0].details["antiguos"] == 2
    assert avisos[0].message == ("1 driver(s) genéricos y 2 con más de 5 años "
                                 "sin actualizar")


def test_outdated_drivers_sin_alertas():
    from diagusb.core.rules import RuleEngine

    engine = RuleEngine()
    obs = [create_mock_result("outdated_drivers", [
        {"device_name": "GPU basica", "reasons": ["generico"], "config_error_code": 0},
    ])]
    findings = engine._check_outdated_drivers(obs)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].message == "1 driver(s) genéricos (driver básico de Windows)"

    vacio = [create_mock_result("outdated_drivers", [])]
    assert engine._check_outdated_drivers(vacio) == []


# ---------------------------------------------------------------------------
# Registro persistente de analisis (config/registro_analisis.json)
# ---------------------------------------------------------------------------

def _diag_fake(i=0):
    return {
        "package": "disco",
        "package_label": "Disco",
        "symptom": "disco_salud",
        "collectors_count": 2,
        "ok_count": 1,
        "error_count": 0,
        "empty_count": 1,
        "results": [
            {"collector_id": "physical_disks",
             "query": {"status": "ok", "duration_ms": 10},
             "data": {"i": i}},
            {"collector_id": "smart_status",
             "query": {"status": "empty", "duration_ms": 5},
             "data": {}},
        ],
        "findings": [{
            "severity": "warning",
            "collector_id": "physical_disks",
            "message": f"p{i}",
            "details": {},
            "knowledge": {},
            "solutions": ["revisar el disco"],
        }],
        "recommendations": ["verificar temperatura"],
        "timestamp": "2026-10-15T09:00:00",
    }


def test_registro_persistente_unitario():
    import diagusb.web_server as ws

    tmp_dir = Path(tempfile.mkdtemp(prefix="diagusb_reg_"))
    old = ws.REGISTRO_PATH
    ws.REGISTRO_PATH = tmp_dir / "registro_analisis.json"
    try:
        assert ws._cargar_registro() == []

        e1 = ws.registrar_analisis(_diag_fake(1), "paquete")
        e2 = ws.registrar_analisis(_diag_fake(2), "paquete")
        assert e1 and e2 and e1["id"] != e2["id"]
        assert ws.REGISTRO_PATH.exists()

        entradas = ws._cargar_registro()
        assert len(entradas) == 2
        assert entradas[0]["id"] == e2["id"], "el mas reciente debe quedar primero"
        assert entradas[0]["conteos"] == {
            "collectors": 2, "ok": 1, "error": 0, "empty": 1, "findings": 1}
        assert entradas[0]["colectores"][0] == {
            "id": "physical_disks", "status": "ok", "duration_ms": 10}
        assert entradas[0]["findings"][0]["message"] == "p2"
        assert entradas[0]["findings"][0]["solutions"] == ["revisar el disco"]
        assert "results" not in entradas[0], "no debe guardar los results crudos"

        # un diagnostico con error no se guarda
        assert ws.registrar_analisis({"error": "Paquete no encontrado"},
                                     "paquete") is None
        assert len(ws._cargar_registro()) == 2

        # borrado individual
        assert ws.eliminar_analisis(e1["id"]) is True
        assert ws.eliminar_analisis(e1["id"]) is False
        assert len(ws._cargar_registro()) == 1

        # borrado total
        assert ws.vaciar_registro() == 1
        assert ws._cargar_registro() == []
        assert ws.vaciar_registro() == 0
    finally:
        ws.REGISTRO_PATH = old
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_registro_poda_y_full_scan():
    import diagusb.web_server as ws

    tmp_dir = Path(tempfile.mkdtemp(prefix="diagusb_reg_"))
    old = ws.REGISTRO_PATH
    old_max = ws.REGISTRO_MAX
    ws.REGISTRO_PATH = tmp_dir / "registro_analisis.json"
    ws.REGISTRO_MAX = 5
    try:
        for i in range(8):
            ws.registrar_analisis(_diag_fake(i), "paquete")
        entradas = ws._cargar_registro()
        assert len(entradas) == 5, "la poda debe dejar solo las 5 mas recientes"
        assert entradas[0]["findings"][0]["message"] == "p7"

        diags = [
            dict(_diag_fake(1), package="disco", package_label="Disco"),
            dict(_diag_fake(2), package="wifi", package_label="WiFi"),
            {"error": "Paquete 'x' no encontrado"},
        ]
        entrada = ws._registrar_full_scan(diags)
        assert entrada["tipo"] == "full-scan"
        assert entrada["paquete"] == "full-scan"
        assert len(entrada["findings"]) == 2
        assert entrada["findings"][0]["package_label"] == "Disco"
        assert entrada["conteos"]["collectors"] == 4
        assert entrada["conteos"]["ok"] == 2
        assert ws._registrar_full_scan([{"error": "x"}]) is None
    finally:
        ws.REGISTRO_PATH = old
        ws.REGISTRO_MAX = old_max
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_registro_endpoints():
    import threading
    import socketserver
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    tmp_dir = Path(tempfile.mkdtemp(prefix="diagusb_reg_"))
    old = ws.REGISTRO_PATH
    ws.REGISTRO_PATH = tmp_dir / "registro_analisis.json"
    httpd = None

    def _get(url):
        req = urllib.request.Request(url, headers=_cookie())
        return json.loads(urllib.request.urlopen(req, timeout=5)
                          .read().decode("utf-8"))

    def _delete(url):
        req = urllib.request.Request(url, method="DELETE", headers=_cookie())
        return json.loads(urllib.request.urlopen(req, timeout=5)
                          .read().decode("utf-8"))

    try:
        class ThreadedTCPServer(socketserver.ThreadingMixIn,
                                socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True

        httpd = ThreadedTCPServer(("127.0.0.1", 0), ws.DiagUSBHandler)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"

        d = _get(base + "/api/registro")
        assert d == {"total": 0, "entradas": []}

        e1 = ws.registrar_analisis(_diag_fake(1), "paquete")
        e2 = ws.registrar_analisis(_diag_fake(2), "full-scan")

        d = _get(base + "/api/registro")
        assert d["total"] == 2
        assert d["entradas"][0]["id"] == e2["id"]
        assert d["entradas"][0]["tipo"] == "full-scan"
        assert "findings" not in d["entradas"][0], "el listado es resumen"

        d = _get(base + f"/api/registro?id={e1['id']}")
        assert d["findings"][0]["message"] == "p1"
        assert d["colectores"][1]["status"] == "empty"

        try:
            _get(base + "/api/registro?id=nope")
            raise AssertionError("el id invalido debio dar 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400

        try:
            _get(base + "/api/registro?id=20200101_000000_deadbeef")
            raise AssertionError("el detalle inexistente debio dar 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404

        d = _delete(base + f"/api/registro?id={e1['id']}")
        assert d["ok"] is True and d["eliminado"] == e1["id"]
        assert len(ws._cargar_registro()) == 1

        try:
            _delete(base + "/api/registro?id=nope")
            raise AssertionError("el id invalido debio dar 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400

        try:
            _delete(base + "/api/registro?id=20200101_000000_deadbeef")
            raise AssertionError("el borrado inexistente debio dar 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404

        d = _delete(base + "/api/registro")
        assert d["ok"] is True and d["eliminados"] == 1
        assert ws._cargar_registro() == []

        try:
            _delete(base + "/api/otra")
            raise AssertionError("DELETE en otra ruta debio dar 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        ws.REGISTRO_PATH = old
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_sin_servidor_de_archivos():
    import http.server
    import threading
    import socketserver
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    assert not issubclass(ws.DiagUSBHandler, http.server.SimpleHTTPRequestHandler), \
        "el handler no debe heredar de SimpleHTTPRequestHandler"

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer(("127.0.0.1", 0), ws.DiagUSBHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(base + "/", headers=_cookie()), timeout=5)
        assert r.status == 200
        assert "text/html" in r.headers.get("Content-Type", "")
        assert "DiagUSB" in r.read().decode("utf-8")

        for ruta in ("/src/diagusb/web_server.py", "/README.md", "/noexiste",
                     "/src/diagusb/"):
            try:
                urllib.request.urlopen(base + ruta, timeout=5)
                raise AssertionError(f"{ruta} debio dar 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404, f"{ruta} -> {e.code}"

        req = urllib.request.Request(base + "/src/diagusb/web_server.py",
                                     method="HEAD")
        try:
            r = urllib.request.urlopen(req, timeout=5)
            raise AssertionError("HEAD no debio responder 200")
        except urllib.error.HTTPError as e:
            assert e.code in (404, 501), f"HEAD -> {e.code}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_bind_solo_loopback():
    import http.server
    import diagusb.web_server as ws

    assert ws.BIND_HOST == "127.0.0.1", ws.BIND_HOST
    httpd = http.server.HTTPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    try:
        assert httpd.server_address[0] == "127.0.0.1", httpd.server_address
        assert httpd.server_address[0] != "0.0.0.0"
    finally:
        httpd.server_close()


def test_sin_cabeceras_cors():
    import threading
    import socketserver
    import urllib.request
    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(base + "/", headers=_cookie()), timeout=5)
        assert r.headers.get("Access-Control-Allow-Origin") is None, \
            "no debe emitirse Access-Control-Allow-Origin"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_validacion_host_y_origin():
    import threading
    import socketserver
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(base + "/", headers={"Host": "evil.example.com"})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("Host ajeno debio dar 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code

        req = urllib.request.Request(base + "/",
                                     headers={"Origin": "http://evil.example.com"})
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("Origin ajeno debio dar 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code

        headers = dict(_cookie())
        headers["Origin"] = f"http://127.0.0.1:{port}"
        assert urllib.request.urlopen(
            urllib.request.Request(base + "/", headers=headers),
            timeout=5).status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_post_exige_json():
    import threading
    import socketserver
    import socket
    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, ctype=None):
        lineas = [
            f"POST {path} HTTP/1.1",
            f"Host: 127.0.0.1:{port}",
            f"Cookie: diagusb_token={ws._token_sesion()}",
            "Connection: close",
        ]
        if ctype:
            lineas.append(f"Content-Type: {ctype}")
        lineas.append("Content-Length: 2")
        lineas.append("")
        lineas.append("{}")
        pedido = "\r\n".join(lineas).encode("ascii")

        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            s.sendall(pedido)
            datos = b""
            while True:
                try:
                    trozo = s.recv(4096)
                except (ConnectionResetError, ConnectionAbortedError):
                    break
                if not trozo:
                    break
                datos += trozo
        finally:
            s.close()
        return int(datos.split(b" ", 2)[1])

    try:
        assert post("/api/snapshot") == 415
        assert post("/api/snapshot", "text/plain") == 415
        assert post("/api/noexiste", "application/json") == 404
        assert post("/api/noexiste", "application/json; charset=utf-8") == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_token_sesion():
    import http.client
    import io
    import contextlib
    import diagusb.web_server as ws

    httpd, base = _abrir_servidor()
    port = httpd.server_address[1]
    token = ws._token_sesion()

    def get(path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", path, headers=headers or {})
        r = conn.getresponse()
        r.read()
        conn.close()
        return r

    try:
        assert get("/").status == 403
        assert get("/api/elevation").status == 401

        r = get("/?t=" + token)
        assert r.status == 302, r.status
        assert r.getheader("Location") == "/"
        cookie = r.getheader("Set-Cookie") or ""
        assert "diagusb_token=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=Strict" in cookie
        assert "Path=/" in cookie

        assert get("/?t=invalido").status == 403

        ck = {"Cookie": f"diagusb_token={token}"}
        assert get("/", ck).status == 200
        assert get("/api/elevation", ck).status == 200

        bad = {"Cookie": "diagusb_token=nope"}
        assert get("/", bad).status == 403
        assert get("/api/elevation", bad).status == 401

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ws.DiagUSBHandler.log_message(None, "%s", "GET /?t=SECRETOX HTTP/1.1")
        salida = buf.getvalue()
        assert "SECRETOX" not in salida, "el token no debe aparecer en el log"
        assert "t=[oculto]" in salida
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_limite_de_cuerpo():
    import socket
    import diagusb.web_server as ws

    httpd, base = _abrir_servidor()
    port = httpd.server_address[1]
    token = ws._token_sesion()

    def status(req):
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(req)
        data = b""
        while b"\r\n" not in data:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        s.close()
        return int(data.split(b" ", 2)[1])

    def req_with(cl):
        cab = (f"POST /api/snapshot HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
               f"Content-Type: application/json\r\n"
               f"Cookie: diagusb_token={token}\r\n")
        if cl is not None:
            cab += f"Content-Length: {cl}\r\n"
        cab += "Connection: close\r\n\r\n"
        return cab.encode()

    try:
        assert status(req_with(None)) == 400
        assert status(req_with("abc")) == 400
        assert status(req_with("-5")) == 400
        assert status(req_with(str(11 * 1024 * 1024))) == 413
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_nombre_informe_seguro():
    import urllib.request
    import diagusb.web_server as ws

    assert ws._paquete_seguro("disco") == "disco"
    assert ws._paquete_seguro('../../x"y') == "xy"
    assert ws._paquete_seguro("") == "equipo"
    assert ws._paquete_seguro(None) == "equipo"

    httpd, base = _abrir_servidor()
    try:
        diag = _diag_minimo()
        diag["package"] = '../../evil"\r\nX-Inject: 1'
        cuerpo = json.dumps({"diagnostico": diag}).encode("utf-8")
        cabeceras = dict(_cookie())
        cabeceras["Content-Type"] = "application/json"
        req = urllib.request.Request(base + "/api/report?format=doc",
                                     data=cuerpo, headers=cabeceras)
        r = urllib.request.urlopen(req, timeout=30)
        assert r.status == 200
        cd = r.headers.get("Content-Disposition", "")
        assert "evil" in cd
        assert "/" not in cd and ".." not in cd
        assert "\r" not in cd and "\n" not in cd
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_id_registro_validado():
    import diagusb.web_server as ws

    assert ws._id_registro_valido("20261015_112427_229d0eda")
    assert not ws._id_registro_valido("nope")
    assert not ws._id_registro_valido("20261015_112427_229D0EDA")
    assert not ws._id_registro_valido("20261015_112427_229d0ed")
    assert not ws._id_registro_valido("")
    assert not ws._id_registro_valido(None)
    assert not ws._id_registro_valido("../etc/passwd")


def test_escritura_atomica_normal():
    import diagusb.core.almacen as almacen

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_atom_"))
    destino = tmp / "datos.json"
    almacen.escribir_json_atomico(destino, {"a": 1, "b": "ñ"})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"a": 1, "b": "ñ"}
    assert not (tmp / "datos.json.tmp").exists()


def test_escritura_atomica_fallo_preserva_original():
    import diagusb.core.almacen as almacen

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_atom_"))
    destino = tmp / "datos.json"
    almacen.escribir_json_atomico(destino, {"v": 1})

    original = almacen.os.replace

    def boom(a, b):
        raise OSError("fallo simulado entre tmp y replace")

    almacen.os.replace = boom
    try:
        try:
            almacen.escribir_json_atomico(destino, {"v": 2})
            raise AssertionError("debio fallar la escritura atomica")
        except OSError:
            pass
    finally:
        almacen.os.replace = original
    assert json.loads(destino.read_text(encoding="utf-8")) == {"v": 1}


def test_registro_corrupto_preservado():
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_reg_"))
    old = ws.REGISTRO_PATH
    ws.REGISTRO_PATH = tmp / "registro_analisis.json"
    try:
        ws.REGISTRO_PATH.write_text("{esto no es json", encoding="utf-8")
        assert ws._cargar_registro() == []
        corruptos = list(tmp.glob("registro_analisis.json.corrupto-*"))
        assert len(corruptos) == 1
        assert not ws.REGISTRO_PATH.exists()
    finally:
        ws.REGISTRO_PATH = old


def test_kb_corrupta_preservada():
    from diagusb.core import knowledge_base as kb

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_kb_"))
    old = kb._RUTA_CONFIG
    kb._RUTA_CONFIG = tmp / "base_conocimiento.json"
    try:
        kb._RUTA_CONFIG.write_text("no-json", encoding="utf-8")
        kb._cargar(force=True)
        corruptos = list(tmp.glob("base_conocimiento.json.corrupto-*"))
        assert len(corruptos) == 1
        assert not kb._RUTA_CONFIG.exists()
    finally:
        kb._RUTA_CONFIG = old
        kb._cargar(force=True)


def test_identidad_coincide_unitario():
    import diagusb.web_server as ws

    a = {"computer_name": "PC-A", "hardware_id": "S1"}
    assert ws._identidad_coincide(a, {"computer_name": "pc-a", "hardware_id": "s1"})
    # Renombrar la PC es normal: el hardware (S1) coincide, no invalida.
    assert ws._identidad_coincide(a, {"computer_name": "PC-B", "hardware_id": "S1"})
    assert not ws._identidad_coincide(a, {"computer_name": "PC-A", "hardware_id": "S2"})
    assert ws._identidad_coincide(a, {"computer_name": "", "hardware_id": ""})

    ident = ws._identidad_equipo([
        {"context": {"computer_name": "PC-A"},
         "data": {"bios": [{"serial_number": "XYZ"}]}}])
    assert ident == {"computer_name": "PC-A", "hardware_id": "XYZ"}


def test_identidad_equipo_comparacion():
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_cmp_"))
    old = ws.BASELINE_PATH
    ws.BASELINE_PATH = tmp / "snapshot_antes.json"
    httpd, base = _abrir_servidor()

    def post_status(path, obj):
        data = json.dumps(obj).encode("utf-8")
        h = dict(_cookie())
        h["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=data, headers=h)
        try:
            r = urllib.request.urlopen(req, timeout=20)
            return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def result(name, serial):
        return {"collector_id": "hardware", "query": {"status": "ok"},
                "context": {"computer_name": name},
                "data": {"bios": [{"serial_number": serial}]}}

    try:
        st, _ = post_status("/api/snapshot", {"results": [result("PC-A", "SER-1")]})
        assert st == 200
        guardado = json.loads(ws.BASELINE_PATH.read_text(encoding="utf-8"))
        assert guardado["computer_name"] == "PC-A"
        assert guardado["hardware_id"] == "SER-1"

        st, d = post_status("/api/compare", {"results": [result("PC-A", "SER-1")]})
        assert st == 200 and d["equipos_distintos"] is False

        st, d = post_status("/api/compare", {"results": [result("PC-B", "SER-9")]})
        assert st == 409
        assert d.get("requiere_confirmacion") is True
        assert "PC-A" in d["error"] and "PC-B" in d["error"]

        st, d = post_status("/api/compare",
                            {"results": [result("PC-B", "SER-9")], "forzar": True})
        assert st == 200 and d["equipos_distintos"] is True

        ws.BASELINE_PATH.write_text(json.dumps(
            {"captured_at": "2020-01-01T00:00:00", "results": [result("", "")]}),
            encoding="utf-8")
        st, d = post_status("/api/compare", {"results": [result("PC-A", "SER-1")]})
        assert st == 200
        assert d.get("advertencia")

        data = json.dumps({"diagnostico": _diag_minimo(),
                           "comparacion_forzada": True}).encode("utf-8")
        h = dict(_cookie())
        h["Content-Type"] = "application/json"
        req = urllib.request.Request(base + "/api/report?format=doc",
                                     data=data, headers=h)
        texto = html_de_doc(urllib.request.urlopen(req, timeout=30).read()).decode("utf-8")
        assert "ADVERTENCIA: la comparación se hizo entre equipos distintos" in texto
    finally:
        httpd.shutdown()
        httpd.server_close()
        ws.BASELINE_PATH = old


def test_integridad_colectores():
    import diagusb.core.integridad as integ

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_int_"))
    ps1 = tmp / "get_demo.ps1"
    ps1.write_text("Write-Output '{}'\n", encoding="utf-8")
    h = integ.hash_archivo(ps1)

    guardado = (integ._manifiesto, integ._cargado, integ._avisado)
    try:
        # hash correcto
        integ._manifiesto = {"get_demo.ps1": h}
        integ._cargado = True
        ok, motivo = integ.verificar(ps1)
        assert ok and motivo == ""

        # archivo alterado
        ps1.write_text("Write-Output 'tampered'\n", encoding="utf-8")
        ok, motivo = integ.verificar(ps1)
        assert not ok and motivo == integ.MENSAJE_MODIFICADO

        # manifiesto ausente -> modo desarrollo, no bloquea
        integ._manifiesto = None
        integ._cargado = True
        integ._avisado = True
        ok, motivo = integ.verificar(ps1)
        assert ok and motivo == ""
    finally:
        integ._manifiesto, integ._cargado, integ._avisado = guardado


def test_run_diagnostic_integridad_fallida():
    import diagusb.web_server as ws

    class FakeInteg:
        MENSAJE_MODIFICADO = "Integridad: el colector fue modificado"

        @staticmethod
        def verificar(ruta):
            return False, FakeInteg.MENSAJE_MODIFICADO

        @staticmethod
        def localizar_common(ruta):
            return None

    old = ws.integridad
    ws.integridad = FakeInteg
    try:
        diag = ws.run_diagnostic("disco")
        assert diag["integridad_fallida"]
        assert diag["error_count"] >= 1
        mensajes = [r["query"]["message"] for r in diag["results"]]
        assert FakeInteg.MENSAJE_MODIFICADO in mensajes
    finally:
        ws.integridad = old


def test_generar_manifiesto():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "generar_manifiesto", root / "scripts" / "generar_manifiesto.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_man_")) / "manifiesto_hashes.json"
    assert gen.main([str(tmp)]) == 0
    data = json.loads(tmp.read_text(encoding="utf-8"))
    assert data["total"] == len(data["archivos"])
    assert "_common.ps1" in data["archivos"]
    assert data["total"] >= 30


def test_web_server_rutas_base():
    import diagusb.web_server as ws
    from diagusb.core import rutas

    assert ws.REGISTRO_PATH == rutas.dir_config() / "registro_analisis.json"
    assert ws.BASELINE_PATH == rutas.dir_reports() / "snapshot_antes.json"


def test_rutas_portables():
    import diagusb.core.rutas as rutas

    rutas.resetear_cache()
    try:
        assert rutas.dir_base() == rutas._raiz_repositorio()
        assert rutas.dir_config() == rutas._raiz_repositorio() / "config"
        assert rutas.dir_reports() == rutas._raiz_repositorio() / "reports"
        assert rutas.usa_respaldo() is False

        tmp = Path(tempfile.mkdtemp(prefix="diagusb_exe_"))
        rutas.resetear_cache()
        old_frozen = getattr(sys, "frozen", None)
        old_exec = sys.executable
        sys.frozen = True
        sys.executable = str(tmp / "diagusb.exe")
        try:
            assert rutas.dir_base() == tmp.resolve()
            assert rutas.usa_respaldo() is False
        finally:
            if old_frozen is None:
                del sys.frozen
            else:
                sys.frozen = old_frozen
            sys.executable = old_exec

        appdata = Path(tempfile.mkdtemp(prefix="diagusb_appdata_"))
        rutas.resetear_cache()
        old_escr = rutas._escribible
        old_local = os.environ.get("LOCALAPPDATA")
        rutas._escribible = lambda carpeta: False
        os.environ["LOCALAPPDATA"] = str(appdata)
        try:
            assert rutas.dir_base() == appdata / "DiagUSB"
            assert rutas.usa_respaldo() is True
            assert rutas.dir_respaldo() == appdata / "DiagUSB"
        finally:
            rutas._escribible = old_escr
            if old_local is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local
    finally:
        rutas.resetear_cache()


def test_rutas_modo_instalado():
    import diagusb.core.rutas as rutas

    programa = Path(tempfile.mkdtemp(prefix="diagusb_programa_"))
    appdata = Path(tempfile.mkdtemp(prefix="diagusb_appdata_"))
    datos = appdata / "DiagUSB"
    (programa / "instalado.flag").write_text(
        f"# DiagUSB: datos de usuario\n{datos}\n", encoding="utf-8")

    old_frozen = getattr(sys, "frozen", None)
    old_exec = sys.executable
    old_local = os.environ.get("LOCALAPPDATA")
    sys.frozen = True
    sys.executable = str(programa / "DiagUSB.exe")
    os.environ["LOCALAPPDATA"] = str(appdata)
    rutas.resetear_cache()
    try:
        assert rutas.dir_base() == datos
        assert rutas.dir_config() == datos / "config"
        assert rutas.dir_reports() == datos / "reports"
        assert rutas.usa_respaldo() is False
    finally:
        rutas.resetear_cache()
        if old_frozen is None:
            del sys.frozen
        else:
            sys.frozen = old_frozen
        sys.executable = old_exec
        if old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = old_local


def test_entry_gui_puerto_elevado():
    import importlib.util

    ruta = Path(__file__).resolve().parent.parent / "build" / "entry_gui.py"
    spec = importlib.util.spec_from_file_location("diagusb_entry_gui_test", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert modulo._puerto_solicitado([]) == 8080
    assert modulo._puerto_solicitado(["web", "--port", "8093"]) == 8093
    assert modulo._puerto_solicitado(["web", "--port=8094"]) == 8094


def test_codigo_verificacion_informe():
    diag = _diag_minimo()
    a = informe_desde_diagnostico(diag)
    b = informe_desde_diagnostico(diag)
    b.generado_en = a.generado_en
    ca = codigo_verificacion(a)
    assert ca == codigo_verificacion(b)
    assert len(ca) == 16 and all(ch in "0123456789abcdef" for ch in ca)

    b2 = informe_desde_diagnostico(diag)
    b2.generado_en = a.generado_en
    b2.equipo = dict(b2.equipo)
    b2.equipo["computer_name"] = "PC-DISTINTA"
    assert codigo_verificacion(b2) != ca

    diag2 = _diag_minimo()
    diag2["package_label"] = "Otro distinto"
    c = informe_desde_diagnostico(diag2)
    c.generado_en = a.generado_en
    assert codigo_verificacion(c) != ca

    assert ca.encode("utf-8") in html_de_doc(informe_a_doc(a))
    assert ca.encode("latin-1") in informe_a_pdf(a)


def test_obs_a_dict_conserva_contexto():
    crudo = {
        "computer_name": "PC-RAW",
        "user": "DOMINIO\\tecnico",
        "is_elevated": True,
        "windows": {"caption": "Microsoft Windows 10 Pro",
                    "version": "10.0.19045", "build_number": "19045"},
    }
    obs = CollectorResult(
        collector_id="system_context",
        query=QueryInfo(status="ok", duration_ms=12),
        metadata={"context": crudo},
        data={"computer_name": "PC-RAW"},
    )
    d = _obs_a_dict(obs)
    assert d["context"]["computer_name"] == "PC-RAW"
    assert d["context"]["windows"]["caption"] == "Microsoft Windows 10 Pro"
    assert d["context"]["windows"]["build_number"] == "19045"
    assert d["query"]["status"] == "ok"

    diag = _diag_minimo()
    diag["results"] = [d]
    inf = informe_desde_diagnostico(diag)
    assert inf.equipo.get("computer_name") == "PC-RAW"
    assert inf.equipo.get("os") == "Microsoft Windows 10 Pro"
    assert inf.equipo.get("build") == "19045"
    assert "administrador" in linea_alcance(inf)

    respaldo = _obs_a_dict(CollectorResult(
        collector_id="otro",
        context=ContextInfo(computer_name="PC-TEST", user="usuario",
                            is_elevated=True),
    ))
    assert respaldo["context"]["computer_name"] == "PC-TEST"
    assert respaldo["context"]["is_elevated"] is True


def test_banner_flush():
    import io
    import diagusb.__main__ as cli

    class Falso(io.StringIO):
        def __init__(self):
            super().__init__()
            self.flushes = 0

        def flush(self):
            self.flushes += 1
            super().flush()

    f = Falso()
    old = sys.stdout
    sys.stdout = f
    try:
        cli.show_banner()
    finally:
        sys.stdout = old
    assert f.flushes >= 1
    assert "USB" in f.getvalue()


def _pdf_caso_base(**kw) -> InformeData:
    e = InformeData(generado_en="2026-10-15T21:00:00",
                    paquete={"label": "Disco", "symptom": "lento"})
    e.equipo = {"computer_name": "PC-01", "user": "ti", "is_elevated": False,
                "os": "Windows 10", "os_version": "10.0.19045", "build": "19045"}
    e.resumen = {"colectores_total": 3, "colectores_ok": 3, "colectores_error": 0,
                 "problemas_total": 1, "criticos": 0, "errores": 0, "advertencias": 1}
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def _pdf_casos() -> dict:
    """Casos de la ronda 6: normal, fuera de cp1252, parentesis/barras, mucho, vacio."""
    def prob(titulo, detalle=None):
        return InformeProblema(indice=1, severidad="warning", colector="logical_disks",
                               titulo=titulo, detalle=detalle or {}, recomendacion="revise",
                               soluciones=["opcion A", "opcion B"])

    casos = {}
    casos["normal"] = _pdf_caso_base(
        problemas=[prob("Espacio limitado en disco C: 15.0% libre",
                        {"device_id": "C:", "free_percent": 15.0, "size_gb": 512})],
        colectores=[InformeColector("logical_disks", "ok", 120, ["C: 15% libre, 512 GB"], [])],
        recomendaciones=["Libere espacio."])

    casos["no_cp1252"] = _pdf_caso_base(
        problemas=[prob("Emoji 😀 cirílico Привет chino 中文 comillas “x” guion — ok",
                        {"model": "Samsung SSD “EVO” — 500GB 🚀"})],
        observaciones="Привет 中文 😀 – — ‘ ’ “ ”",
        colectores=[InformeColector("logical_disks", "ok", 10, ["привет 中文 😀"], [])])

    casos["parentesis_barras"] = _pdf_caso_base(
        problemas=[prob("Ruta C:\\Windows\\System32 (x86) y (parentesis)",
                        {"path": "C:\\Program Files (x86)\\algo\\(sub)"})],
        observaciones="backslash \\ y (parentesis) y )cierre( ")

    casos["mucho"] = _pdf_caso_base(
        problemas=[prob(f"Problema numero {i} con texto de relleno " * 3,
                        {"device_id": f"D{i}"}) for i in range(1, 40)],
        colectores=[InformeColector(f"col{i}", "ok", i, [f"linea {j} " * 5 for j in range(10)], [])
                    for i in range(1, 25)],
        recomendaciones=[f"Recomendacion {i} " * 4 for i in range(1, 20)])

    casos["vacio"] = _pdf_caso_base(problemas=[], colectores=[], recomendaciones=[],
                                    observaciones="")
    return casos


def test_pdf_valido_casos():
    for nombre, inf in _pdf_casos().items():
        errores = validar_pdf(informe_a_pdf(inf))
        assert not errores, f"{nombre}: {errores}"


def test_pdf_validador_externo():
    try:
        import pypdf
    except ImportError:
        print("      (validador externo no disponible: NO VERIFICADO)")
        return
    import io
    for nombre, inf in _pdf_casos().items():
        r = pypdf.PdfReader(io.BytesIO(informe_a_pdf(inf)), strict=True)
        assert len(r.pages) >= 1, f"{nombre}: sin paginas"
        assert any((pg.extract_text() or "").strip() for pg in r.pages), f"{nombre}: sin texto"


# ---------------------------------------------------------------------------
# Arranque sin UAC y elevacion a pedido (ronda 11)
# ---------------------------------------------------------------------------

def test_arranque_sin_elevar():
    import inspect
    import diagusb.web_server as ws
    from diagusb.__main__ import construir_parser

    sig = inspect.signature(ws.run_server)
    assert sig.parameters["elevar"].default is False, \
        "el servidor web no debe elevarse por defecto"

    parser = construir_parser()
    assert parser.parse_args([]).elevar is False
    assert parser.parse_args(["web"]).elevar is False
    assert parser.parse_args(["--elevar", "web"]).elevar is True
    assert parser.parse_args(["--no-elevate", "web"]).no_elevate is True


def test_api_elevar_token():
    import http.client
    from diagusb.core import elevation as elev

    httpd, base = _abrir_servidor()
    port = httpd.server_address[1]

    def post(headers):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", "/api/elevar", body="{}", headers=headers)
        r = conn.getresponse()
        cuerpo = r.read()
        conn.close()
        return r.status, cuerpo

    original = elev.elevar_servidor
    elev.elevar_servidor = lambda linea, puerto, timeout=20.0: False
    try:
        estado, _ = post({"Content-Type": "application/json"})
        assert estado == 401, estado

        h = dict(_cookie())
        h["Content-Type"] = "application/json"
        estado, cuerpo = post(h)
        assert estado == 200, estado
        datos = json.loads(cuerpo.decode("utf-8"))
        assert "ok" in datos and datos["ok"] is False
    finally:
        elev.elevar_servidor = original
        httpd.shutdown()
        httpd.server_close()


def test_api_apagar_token():
    import http.client

    httpd, _ = _abrir_servidor()
    port = httpd.server_address[1]

    def post(headers):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", "/api/apagar", body="{}", headers=headers)
        r = conn.getresponse()
        cuerpo = r.read()
        conn.close()
        return r.status, cuerpo

    try:
        estado, _ = post({"Content-Type": "application/json"})
        assert estado == 401, estado

        h = dict(_cookie())
        h["Content-Type"] = "application/json"
        estado, cuerpo = post(h)
        assert estado == 200, estado
        datos = json.loads(cuerpo.decode("utf-8"))
        assert datos.get("ok") is True, datos
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_api_latido_y_despedida():
    import http.client
    import diagusb.web_server as ws

    httpd, _ = _abrir_servidor()
    port = httpd.server_address[1]
    h = dict(_cookie())
    h["Content-Type"] = "application/json"

    def post(ruta, cuerpo):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", ruta, body=cuerpo, headers=h)
        r = conn.getresponse()
        r.read()
        conn.close()
        return r.status

    ws._reiniciar_latidos()
    try:
        assert post("/api/latido", json.dumps({"id": "cliente-test"})) == 200
        assert "cliente-test" in ws._LATIDOS
        assert post("/api/despedida",
                    json.dumps({"id": "cliente-test"})) == 200
        assert "cliente-test" not in ws._LATIDOS
    finally:
        ws._reiniciar_latidos()
        httpd.shutdown()
        httpd.server_close()


def test_watchdog_cierra_al_cerrar_pestana():
    import threading
    import time
    import diagusb.web_server as ws

    class ServidorFalso:
        cerrado = False

        def shutdown(self):
            self.cerrado = True

    gracia_original = ws._CIERRE_GRACIA
    timeout_original = ws._LATIDO_TIMEOUT
    ws._CIERRE_GRACIA = 0.1
    ws._LATIDO_TIMEOUT = 2.0
    ws._reiniciar_latidos()
    servidor = ServidorFalso()
    hilo = threading.Thread(target=ws._vigilar_latidos,
                            args=(servidor,), daemon=True)
    hilo.start()
    try:
        ws._registrar_latido("pestana-test")
        time.sleep(1.2)
        assert not servidor.cerrado

        ws._quitar_latido("pestana-test")
        hilo.join(3)
        assert servidor.cerrado
        assert not hilo.is_alive()
    finally:
        ws._reiniciar_latidos()
        ws._CIERRE_GRACIA = gracia_original
        ws._LATIDO_TIMEOUT = timeout_original


def test_reglas_colector_denied():
    from diagusb.core.rules import diagnose_symptoms

    obs = [create_mock_result("security_events", [], status="denied")]
    findings, _ = diagnose_symptoms(["antivirus_apagado"], obs)

    no_eval = [f for f in findings if (f.details or {}).get("no_evaluado")]
    assert len(no_eval) == 1, findings
    assert no_eval[0].collector_id == "security_events"
    assert no_eval[0].message == "No evaluado (requiere administrador)"
    assert no_eval[0].details.get("requiere_admin") is True


def test_linea_alcance_informes():
    import diagusb.web_server as ws

    diag = {
        "timestamp": "2026-01-01T00:00:00",
        "package": "seguridad",
        "package_label": "Seguridad",
        "symptom": "antivirus_apagado",
        "is_elevated": False,
        "results": [
            {"collector_id": "security_events", "query": {"status": "denied"},
             "data": {}, "context": {"computer_name": "PC-01", "is_elevated": False}},
        ],
        "findings": [],
    }
    inf = informe_desde_diagnostico(diag)

    linea = linea_alcance(inf)
    assert linea == "Alcance: modo estándar; no evaluados: security_events", linea
    assert linea in informe_a_html(inf)
    assert b"Alcance" in informe_a_pdf(inf)
    assert b"Alcance" in html_de_doc(informe_a_doc(inf))

    entrada = ws._entrada_registro(diag, "diagnostico")
    assert "security_events" in entrada["alcance"]
    assert "modo estándar" in entrada["alcance"]


def test_datos_limitados_alcance():
    import diagusb.web_server as ws
    from diagusb.core.rules import diagnose_symptoms

    diag = {
        "timestamp": "2026-01-01T00:00:00",
        "package": "inventario_general",
        "package_label": "Inventario",
        "symptom": "general",
        "is_elevated": False,
        "results": [
            {"collector_id": "installed_software", "query": {"status": "ok"},
             "data": [{"installed_products": [{"name": "A"}],
                       "optional_features": [],
                       "optional_features_available": False}],
             "context": {"computer_name": "PC-01", "is_elevated": False}},
        ],
        "findings": [],
    }
    inf = informe_desde_diagnostico(diag)
    linea = linea_alcance(inf)
    assert linea.startswith("Alcance: modo estándar; no evaluados: ninguno"), linea
    assert "datos limitados: installed_software (requiere administrador)" in linea, linea
    assert "datos limitados: installed_software (requiere administrador)" in informe_a_html(inf)
    assert b"datos limitados" in html_de_doc(informe_a_doc(inf))
    assert b"Alcance" in informe_a_pdf(inf)

    entrada = ws._entrada_registro(diag, "diagnostico")
    assert "datos limitados: installed_software (requiere administrador)" in entrada["alcance"]

    obs = [create_mock_result(
        "installed_software",
        [{"optional_features": [], "optional_features_available": False}], status="ok")]
    findings, _ = diagnose_symptoms(["general"], obs)
    lim = [f for f in findings if (f.details or {}).get("datos_limitados")]
    assert len(lim) == 1, findings
    assert lim[0].collector_id == "installed_software"

    diag_ok = dict(diag)
    diag_ok["results"] = [dict(diag["results"][0],
                               data=[{"optional_features": [],
                                      "optional_features_available": True}])]
    assert "datos limitados" not in linea_alcance(informe_desde_diagnostico(diag_ok))
    obs_ok = [create_mock_result(
        "installed_software",
        [{"optional_features": [], "optional_features_available": True}], status="ok")]
    findings_ok, _ = diagnose_symptoms(["general"], obs_ok)
    assert not [f for f in findings_ok if (f.details or {}).get("datos_limitados")]


def test_physical_disks_usb_no_limita():
    import diagusb.web_server as ws
    from diagusb.core.informe import _limitado_de

    ruta = (Path(ws.__file__).parent / "packages" / "disco" / "collectors"
            / "get_physical_disks.ps1")
    texto = ruta.read_text(encoding="utf-8")
    assert "BusType" in texto and "'USB'" in texto
    assert "no aplica a unidades USB" in texto
    assert "Start-Job" in texto and "Wait-Job" in texto and "-Timeout 10" in texto
    assert "Stop-Job" in texto and "Remove-Job" in texto
    assert "sin respuesta en 10 s" in texto
    assert "reliability" in texto

    # Armado en paralelo: los jobs se lanzan en un bucle y se esperan con un
    # unico Wait-Job global (no uno por disco); sin discos no-USB no hay jobs.
    assert texto.count("Start-Job") == 1
    assert texto.count("Wait-Job") == 1
    assert texto.index("Start-Job") < texto.index("Wait-Job")
    assert "if ($jobs.Count -gt 0)" in texto

    usb = {"device_id": "3", "friendly_name": "USB pen", "bus_type": "USB",
           "reliability": None, "reliability_motivo": "no aplica a unidades USB"}
    sata_ok = {"device_id": "0", "friendly_name": "SSD", "bus_type": "SATA",
               "reliability": {"temperature": 36}, "reliability_motivo": None}
    sata_falla = {"device_id": "1", "friendly_name": "HDD", "bus_type": "SATA",
                  "reliability": None,
                  "reliability_motivo": "sin respuesta en 10 s"}

    # El USB con su motivo NO cuenta como dato limitado.
    assert _limitado_de("physical_disks", [usb], "ok") == ""
    # USB + no-USB con fiabilidad: tampoco.
    assert _limitado_de("physical_disks", [usb, sata_ok], "ok") == ""
    # Un no-USB sin fiabilidad si cuenta.
    assert _limitado_de("physical_disks", [usb, sata_ok, sata_falla], "ok") == \
        "confiabilidad no disponible"

    base = {
        "timestamp": "2026-01-01T00:00:00",
        "package": "disco", "package_label": "Disco", "symptom": "general",
        "is_elevated": True,
        "results": [
            {"collector_id": "physical_disks", "query": {"status": "ok"},
             "data": [usb, sata_ok],
             "context": {"computer_name": "PC-01", "is_elevated": True}}],
        "findings": [],
    }
    linea = linea_alcance(informe_desde_diagnostico(base))
    assert "datos limitados" not in linea, linea
    assert "no evaluados: ninguno" in linea
    assert "physical_disks" not in linea
    assert "datos limitados" not in informe_a_html(informe_desde_diagnostico(base))
    assert "datos limitados" not in ws._entrada_registro(base, "diagnostico")["alcance"]

    con_falla = dict(base)
    con_falla["results"] = [dict(base["results"][0], data=[usb, sata_ok, sata_falla])]
    esperado = "datos limitados: physical_disks (confiabilidad no disponible)"
    assert esperado in linea_alcance(informe_desde_diagnostico(con_falla))
    assert esperado in ws._entrada_registro(con_falla, "diagnostico")["alcance"]


def test_colector_temperatura_cpu_lhm():
    """Ruta simulada: la estructura del colector alimenta la regla del CPU.

    No ejecuta powershell ni consulta la red: usa los mismos campos que
    devuelve ``get_cpu_temperature.ps1`` (comprobado textualmente abajo).
    La prueba real con PowerShell queda como manual y omitida por defecto.
    """
    from diagusb.core.rules import RuleEngine

    # claves que introduces el colector en su resultado (get_cpu_temperature.ps1)
    texto_ps = (Path(__file__).parent.parent / "src" / "diagusb" / "packages"
                / "temperatura" / "collectors" / "get_cpu_temperature.ps1").read_text(
                    encoding="utf-8")
    for clave in ("source = 'librehardwaremonitor'", "url = $data.url",
                  "available = $true", "sampled_at_utc",
                  "cpu_name = $data.cpu_name", "package_temp_c",
                  "max_core_temp_c", "average_core_temp_c", "max_temp_c",
                  "sensor_count = $data.sensor_count", "sensors = $data.sensors"):
        assert clave in texto_ps, clave

    # datos simulados con la misma forma que produce el colector ante un
    # data.json simulado (Package 74, Tctl/Tdie 76, Cores 72/75)
    simulado = CollectorResult(
        collector_id="cpu_temperature",
        query=QueryInfo(status="ok", duration_ms=8, timeout_seconds=15),
        data=[{
            "source": "librehardwaremonitor",
            "url": "http://127.0.0.1:8085",
            "available": True,
            "sampled_at_utc": "2026-01-01T00:00:00Z",
            "cpu_name": "AMD Ryzen 7 5800H",
            "package_temp_c": 74.0,
            "max_core_temp_c": 75.0,
            "average_core_temp_c": 73.5,
            "max_temp_c": 76.0,
            "sensor_count": 4,
            "sensors": [
                {"name": "Package", "temperature_c": 74.0, "kind": "package"},
                {"name": "Core (Tctl/Tdie)", "temperature_c": 76.0, "kind": "package"},
            ],
        }],
    )

    engine = RuleEngine()
    # sin hallazgo por debajo del umbral
    assert engine._check_cpu_temperature([simulado]) == []

    caliente = CollectorResult(
        collector_id="cpu_temperature",
        query=QueryInfo(status="ok", duration_ms=8, timeout_seconds=15),
        data=[{**simulado.data[0], "max_temp_c": 91.0}],
    )
    cumplido = engine._check_cpu_temperature([caliente])
    assert len(cumplido) == 1
    assert cumplido[0].severity == "error"
    assert "91 °C" in cumplido[0].message
    assert cumplido[0].knowledge_id == "cpu_caliente"
    assert cumplido[0].details["package_temp_c"] == 74.0
    assert cumplido[0].details["sensor_count"] == 4


@pytest.mark.skipif(not os.environ.get("DIAGUSB_PRUEBAS_MANUALES"),
                    reason="manual: ejecuta PowerShell real; activar con "
                           "DIAGUSB_PRUEBAS_MANUALES=1")
def test_manual_colector_temperatura_cpu_lhm():
    import http.server
    import subprocess
    import threading

    from diagusb.core.procesos import opciones_sin_ventana

    if os.name != "nt":
        return

    payload = json.dumps({
        "Children": [
            {
                "Text": "AMD Ryzen 7 5800H",
                "ImageURL": "images_icon/cpu.png",
                "Children": [{
                    "Text": "Temperatures",
                    "Children": [
                        {"Text": "Package", "Value": "74.0 °C"},
                        {"Text": "Core (Tctl/Tdie)", "Value": "76.0 °C"},
                        {"Text": "Core #1", "Value": "72.0 °C"},
                        {"Text": "Core #2", "Value": "75.0 °C"},
                        {"Text": "Core Distance to TjMax", "Value": "-34.0 °C"},
                    ],
                }],
            },
            {
                "Text": "GeForce RTX 3070",
                "ImageURL": "images_icon/nvidia_gpu.png",
                "Children": [{"Text": "GPU Core", "Value": "58 °C"}],
            },
        ],
    }, ensure_ascii=False).encode("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/data.json":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    base = f"http://127.0.0.1:{servidor.server_port}"

    script = (Path(__file__).parent.parent / "src" / "diagusb" / "packages"
              / "temperatura" / "collectors" / "get_cpu_temperature.ps1")
    env = os.environ.copy()
    env["DIAGUSB_LHM_URL"] = base
    try:
        resultado = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25, env=env, **opciones_sin_ventana())
        assert resultado.returncode == 0, resultado.stderr
        salida = json.loads(resultado.stdout.strip())
        assert salida["query"]["status"] == "ok", salida
        data = salida["data"][0]
        assert data["available"] is True
        assert data["url"] == base
        assert data["cpu_name"] == "AMD Ryzen 7 5800H"
        assert data["package_temp_c"] == 76.0
        assert data["max_core_temp_c"] == 75.0
        assert data["average_core_temp_c"] == 73.5
        assert data["max_temp_c"] == 76.0
        assert data["sensor_count"] == 4
        nombres = {s["name"] for s in data["sensors"]}
        assert "Core Distance to TjMax" not in nombres
        assert not any("GPU" in n for n in nombres)
    finally:
        env.pop("DIAGUSB_LHM_URL", None)
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=2)


def test_pagina_desde_static():
    import diagusb.web_server as ws

    html = ws._cargar_pagina()
    assert "@@DIAGUSB" not in html
    base = Path(ws.__file__).with_name("static")
    for nombre in ("index.html", "app.css", "app.js"):
        assert (base / nombre).is_file(), nombre
    for pkg in ("impresion", "redes", "wifi", "disco", "memoria", "temperatura",
                "servicios", "seguridad", "windows_update", "drivers", "eventos",
                "contexto"):
        assert f"runDiagnostic('{pkg}')" in html, pkg
    assert "runFullScan()" in html
    assert "btnKb" in html and "btnRegistro" in html


def test_atributos_cuerpo_escapados():
    import diagusb.web_server as ws

    attrs = ws._atributos_cuerpo('0.1.0"><script>alert(1)</script>',
                                 '127.0.0.1:8080', 'C:\\datos & <x>')
    assert '<script>' not in attrs
    assert '&quot;' in attrs and '&lt;script&gt;' in attrs and '&amp;' in attrs
    page = ws._inyectar_atributos('<body><p>x</p></body>', attrs)
    assert page.startswith('<body data-version="')
    assert page.count('<body') == 1


def test_pagina_inyectada_datos():
    import diagusb.web_server as ws

    page = ws._inyectar_atributos(
        ws._cargar_pagina(),
        ws._atributos_cuerpo('0.1.0', '127.0.0.1:8080', 'C:\\Users\\X\\DiagUSB'))
    assert 'data-version="0.1.0"' in page
    assert 'data-hostport="127.0.0.1:8080"' in page
    assert 'data-datadir="C:\\Users\\X\\DiagUSB"' in page


def test_modulos_y_fetch_sin_cambios():
    import re
    import diagusb.web_server as ws

    html = ws._cargar_pagina()
    assert html.count('class="mod-btn') == 17
    assert "runDiagnostic('inventario_general')" in html
    assert "runDiagnostic('conectividad')" in html
    assert 'http://' not in html and 'https://' not in html
    js = (Path(ws.__file__).with_name("static") / "app.js").read_text(encoding="utf-8")
    assert "/api/capacidades" in js
    destinos = [u for _, u in re.findall(r"fetch\(\s*(['\"])(.*?)\1", js)]
    assert len(destinos) == 20, destinos
    assert set(destinos) == {
        '/api/snapshot', '/api/compare', '/api/report?format=',
        '/api/diagnose?package=', '/api/full-scan', '/api/knowledge',
        '/api/registro?id=', '/api/registro', '/api/datos', '/api/apagar',
        '/api/latido', '/api/progreso', '/api/elevation', '/api/elevar',
        '/api/identidad'}


def test_run_powershell_timeout_termina_arbol():
    import tempfile
    import time
    import diagusb.web_server as ws

    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "duerme.ps1"
        script.write_text(
            '& powershell.exe -NoProfile -Command "Start-Sleep -Seconds 20"\n'
            '\'{"query":{"status":"ok"},"data":{}}\'\n',
            encoding="utf-8",
        )
        t = time.monotonic()
        r = ws.run_powershell(str(script), timeout=2)
        dt = time.monotonic() - t

    assert (r.get("query") or {}).get("status") == "timeout", r
    assert dt < 5.0, f"run_powershell tardo {dt:.1f}s con timeout de 2s"


def _decodificar_png(data):
    """Decodifica un PNG RGB sin filtros (los que genera DiagUSB)."""
    import struct
    import zlib

    assert data[:8] == b"\x89PNG\r\n\x1a\n", "firma PNG invalida"
    pos = 8
    idat = b""
    ancho = alto = 0
    while pos < len(data):
        (largo,) = struct.unpack(">I", data[pos:pos + 4])
        tipo = data[pos + 4:pos + 8]
        cuerpo = data[pos + 8:pos + 8 + largo]
        pos += 12 + largo
        if tipo == b"IHDR":
            ancho, alto = struct.unpack(">II", cuerpo[:8])
        elif tipo == b"IDAT":
            idat += cuerpo
        elif tipo == b"IEND":
            break
    crudo = zlib.decompress(idat)
    paso = ancho * 3
    salida = bytearray()
    for y in range(alto):
        filtro = crudo[y * (paso + 1)]
        assert filtro == 0, "solo se esperan filas sin filtro"
        salida += crudo[y * (paso + 1) + 1:y * (paso + 1) + 1 + paso]
    return bytes(salida)


def test_graficos_png_valido():
    import struct
    import zlib

    from diagusb.core.graficos import porciones
    from diagusb.core.graficos_png import imagen_barra, imagen_dona, imagen_torta

    png = imagen_barra(100, "#2FBF71", ancho=40, alto=10)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">I", png[8:12])[0] == 13
    assert png[12:16] == b"IHDR"
    ancho, alto, bits, ctype = struct.unpack(">IIBB", png[16:26])
    assert (ancho, alto, bits, ctype) == (40, 10, 8, 2)
    assert struct.unpack(">I", png[29:33])[0] == (zlib.crc32(png[12:29]) & 0xFFFFFFFF)
    assert png.endswith(b"IEND\xaeB`\x82")

    pixeles = _decodificar_png(png)
    centro = (5 * 40 + 20) * 3
    assert pixeles[centro:centro + 3] == bytes((47, 191, 113))

    vacia = _decodificar_png(imagen_barra(0, "#2FBF71", ancho=40, alto=10))
    assert vacia[centro:centro + 3] == bytes((224, 227, 231))

    ps = porciones([("A", 1, "#C62839"), ("B", 1, "#2FBF71")])
    torta = _decodificar_png(imagen_torta(ps, 64))
    assert torta[32 * 64 * 3 + 32 * 3:32 * 64 * 3 + 32 * 3 + 3] != bytes((255, 255, 255))
    dona = _decodificar_png(imagen_dona(ps, 64))
    assert dona[32 * 64 * 3 + 32 * 3:32 * 64 * 3 + 32 * 3 + 3] == bytes((255, 255, 255))


def test_doc_mhtml_con_imagenes():
    import base64

    from diagusb.core.informe import informe_a_doc, informe_desde_diagnostico

    inf = informe_desde_diagnostico(_diag_con_metricas())
    datos = informe_a_doc(inf, resultados_completos=[])
    assert b"multipart/related" in datos[:200]
    assert b"Content-Type: image/png" in datos

    partes = datos.split(b"Content-Type: image/png")
    assert len(partes) >= 2
    cuerpo = partes[1].split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0]
    png = base64.b64decode(b"".join(cuerpo.split()))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png.endswith(b"IEND\xaeB`\x82")

    texto = html_de_doc(datos).decode("utf-8", errors="replace")
    assert "diagusb_severidad.png" in texto
    assert "diagusb_disco0.png" in texto
    assert "diagusb_memoria.png" in texto
    assert "v:imagedata" in texto
    assert "Sin datos para graficar." in texto


def test_saneamiento_redacta_estructuras():
    from diagusb.core.saneamiento import MARCA, redactar

    original = {
        "clave": "secreto123",
        "texto": ("SSID: Casa\n"
                  "Contenido de la clave : abc123\n"
                  "Key Content : xyz789\n"
                  "normal"),
        "lista": [{"Password": "p4ss"}, "token=abc123"],
    }
    saneado = redactar(original)
    assert saneado["clave"] == MARCA
    assert "abc123" not in saneado["texto"]
    assert "xyz789" not in saneado["texto"]
    assert "SSID: Casa" in saneado["texto"]
    assert "[OCULTO]" in saneado["texto"]
    assert "normal" in saneado["texto"]
    assert saneado["lista"][0]["Password"] == MARCA
    assert saneado["lista"][1] == MARCA
    assert original["clave"] == "secreto123"


def test_wifi_colector_no_pide_clave():
    ruta = (Path(__file__).parent.parent / "src" / "diagusb" / "packages" /
            "wifi" / "collectors" / "get_wifi_profiles.ps1")
    texto = ruta.read_text(encoding="utf-8")
    assert "key=clear" not in texto.lower()
    assert "netsh wlan show profile name=" in texto
    for campo in ("authentication", "cipher", "connection_mode",
                  "auto_connect"):
        assert campo in texto


def test_api_snapshot_sanea_antes_de_guardar():
    import urllib.request
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_sanea_"))
    original = ws.BASELINE_PATH
    ws.BASELINE_PATH = tmp / "snapshot_antes.json"
    httpd, base = _abrir_servidor()
    try:
        resultado = {
            "collector_id": "wifi_profiles",
            "captured_at_utc": datetime.utcnow().isoformat(),
            "query": {"status": "ok", "duration_ms": 1,
                      "timeout_seconds": 15},
            "context": {},
            "data": [{
                "name": "Casa",
                "details": "Contenido de la clave : secreto123",
                "password": "clave456",
            }],
            "errors": [],
        }
        cuerpo = json.dumps({"results": [resultado]}).encode("utf-8")
        cabeceras = dict(_cookie())
        cabeceras["Content-Type"] = "application/json"
        req = urllib.request.Request(base + "/api/snapshot", data=cuerpo,
                                     headers=cabeceras)
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status == 200
        guardado = ws.BASELINE_PATH.read_text(encoding="utf-8")
        assert "secreto123" not in guardado
        assert "clave456" not in guardado
        assert "[OCULTO]" in guardado
    finally:
        httpd.shutdown()
        httpd.server_close()
        ws.BASELINE_PATH = original


def test_saneo_pasa_puerta_y_dhcp_sin_enmascarar():
    """redactar no enmascara gateway_mac ni dhcp_server en snapshots locales.

    Los valores reales deben guardarse para que el comparador de instantáneas
    detecte cambios reales. El enmascarado (_enmascarar_mac, _enmascarar_ip)
    se reserva para la exportación de informes (Fase 4).
    """
    from diagusb.core.saneamiento import redactar

    dato = {
        "ip_configuration": [{
            "interface_alias": "Ethernet",
            "gateway_mac": "00-00-5E-00-53-01",
            "dhcp_server": "192.0.2.1",
            "mac_address": "00-00-5E-00-53-01",
        }],
        "clave_wifi": "secreto123",
        "password": "clave456",
    }
    limpio = redactar(dato)
    ip = limpio["ip_configuration"][0]
    assert ip["gateway_mac"] == "00-00-5E-00-53-01"
    assert ip["dhcp_server"] == "192.0.2.1"
    assert ip["mac_address"] == "00-00-5E-00-53-01"
    assert limpio["clave_wifi"] == "[OCULTO]"
    assert limpio["password"] == "[OCULTO]"


def _resultado_ip_config(mac: str, dhcp: str = "192.0.2.1") -> CollectorResult:
    return CollectorResult(
        collector_id="ip_configuration",
        data={
            "interface_alias": "Ethernet",
            "gateway_mac": mac,
            "dhcp_server": dhcp,
        },
    )


def test_snapshot_ronda_conserva_y_compara_mac_y_dhcp():
    """Guardar y cargar conserva gateway_mac y dhcp_server.

    Igual -> sin diferencias; gateway_mac distinto -> diferencia real.
    """
    import json
    import tempfile
    from pathlib import Path

    from diagusb.core.comparator import compare_snapshots, load_snapshot, save_snapshot
    from diagusb.core.models import CollectorResult, ComputerId, QueryInfo, Snapshot

    base = Snapshot(
        computer_id=ComputerId(),
        captured_at_utc="2026-01-01T00:00:00Z",
        observations=[_resultado_ip_config("00-00-5E-00-53-01")],
    )
    igual = Snapshot(
        computer_id=ComputerId(),
        captured_at_utc="2026-01-02T00:00:00Z",
        observations=[_resultado_ip_config("00-00-5E-00-53-01")],
    )
    distinto = Snapshot(
        computer_id=ComputerId(),
        captured_at_utc="2026-01-03T00:00:00Z",
        observations=[_resultado_ip_config("00-00-5E-00-53-02")],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        p_base = tmp_path / "antes.json"
        p_despues = tmp_path / "despues.json"
        save_snapshot(base, p_base)
        save_snapshot(igual, p_despues)

        guardado = json.loads(p_base.read_text(encoding="utf-8"))
        assert guardado["observations"][0]["data"]["gateway_mac"] == "00-00-5E-00-53-01"
        assert guardado["observations"][0]["data"]["dhcp_server"] == "192.0.2.1"

        diffs_igual = compare_snapshots(load_snapshot(p_base), load_snapshot(p_despues))
        assert not diffs_igual, diffs_igual

        save_snapshot(distinto, p_despues)
        diffs_distinto = compare_snapshots(load_snapshot(p_base), load_snapshot(p_despues))
        assert any(
            d.collector_id == "ip_configuration"
            and d.field_path == "gateway_mac"
            and d.baseline_value == "00-00-5E-00-53-01"
            and d.current_value == "00-00-5E-00-53-02"
            for d in diffs_distinto
        ), diffs_distinto


def test_registro_sanea_findings():
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_sanea_reg_"))
    original = ws.REGISTRO_PATH
    ws.REGISTRO_PATH = tmp / "registro_analisis.json"
    try:
        diag = {
            "package": "wifi",
            "findings": [{
                "severity": "warning",
                "collector_id": "wifi_profiles",
                "message": "Clave: secreto123",
                "details": {"Password": "clave456"},
            }],
            "recommendations": ["Cambiar token=abc123"],
        }
        entrada = ws.registrar_analisis(diag, "paquete")
        assert entrada is not None
        guardado = ws.REGISTRO_PATH.read_text(encoding="utf-8")
        assert "secreto123" not in guardado
        assert "clave456" not in guardado
        assert "abc123" not in guardado
        assert "[OCULTO]" in guardado
    finally:
        ws.REGISTRO_PATH = original


def test_api_registro_redacta_legado():
    import urllib.request
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_sanea_legado_"))
    original = ws.REGISTRO_PATH
    ws.REGISTRO_PATH = tmp / "registro_analisis.json"
    ws.REGISTRO_PATH.write_text(json.dumps([{
        "id": "20200101_000000_deadbeef",
        "fecha": "2020-01-01T00:00:00",
        "tipo": "paquete",
        "paquete": "wifi",
        "findings": [{"message": "Clave: secreto123"}],
    }]), encoding="utf-8")
    httpd, base = _abrir_servidor()
    try:
        req = urllib.request.Request(
            base + "/api/registro?id=20200101_000000_deadbeef",
            headers=_cookie())
        with urllib.request.urlopen(req, timeout=30) as r:
            texto = r.read().decode("utf-8")
        assert "secreto123" not in texto
        assert "[OCULTO]" in texto
    finally:
        httpd.shutdown()
        httpd.server_close()
        ws.REGISTRO_PATH = original


def test_api_borrar_datos_locales():
    import threading
    import socketserver
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    tmp = Path(tempfile.mkdtemp(prefix="diagusb_borrar_"))
    reports = tmp / "reports"
    reports.mkdir()
    old_reg = ws.REGISTRO_PATH
    old_base = ws.BASELINE_PATH
    ws.REGISTRO_PATH = tmp / "registro_analisis.json"
    ws.BASELINE_PATH = reports / "snapshot_antes.json"

    def peticion(confirmar, extra=None):
        cabeceras = {"Content-Type": "application/json"}
        cabeceras.update(extra or {})
        cuerpo = json.dumps({"confirmar": confirmar}).encode("utf-8")
        req = urllib.request.Request(base + "/api/datos", data=cuerpo,
                                     headers=cabeceras, method="DELETE")
        return urllib.request.urlopen(req, timeout=10)

    httpd = None
    try:
        ws.registrar_analisis(_diag_fake(1), "paquete")
        ws.registrar_analisis(_diag_fake(2), "paquete")
        ws.BASELINE_PATH.write_text("{}", encoding="utf-8")
        (reports / "snapshot_otro.json").write_text("{}", encoding="utf-8")
        for nombre in ("informe.pdf", "informe.doc", "informe.html"):
            (reports / nombre).write_text("x", encoding="utf-8")
        (reports / "nota.txt").write_text("conservar", encoding="utf-8")

        kb_antes = (kb.version(), len(kb.entradas()))
        httpd, base = _abrir_servidor()

        with urllib.request.urlopen(
                urllib.request.Request(base + "/", headers=_cookie()),
                timeout=10) as r:
            pagina = r.read().decode("utf-8")
        assert "Datos locales" in pagina
        assert "borrarDatosLocales()" in pagina
        assert 'id="datosRegistro"' in pagina

        try:
            peticion(True)
            raise AssertionError("sin cookie debio dar 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code

        try:
            peticion(True, {"Cookie": _cookie()["Cookie"],
                            "Host": "evil.example.com"})
            raise AssertionError("Host ajeno debio dar 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403, e.code

        try:
            peticion(True, {"Cookie": _cookie()["Cookie"],
                            "Content-Type": "text/plain"})
            raise AssertionError("Content-Type invalido debio dar 415")
        except urllib.error.HTTPError as e:
            assert e.code == 415, e.code

        try:
            peticion(False, _cookie())
            raise AssertionError("sin confirmacion debio dar 400")
        except urllib.error.HTTPError as e:
            assert e.code == 400, e.code
            conteos = json.loads(e.read().decode("utf-8"))["conteos"]
            assert conteos == {"registro": 2, "snapshots": 2, "informes": 3}

        with peticion(True, _cookie()) as r:
            assert r.status == 200
            eliminados = json.loads(r.read().decode("utf-8"))["eliminados"]
        assert eliminados == {"registro": 2, "snapshots": 2, "informes": 3}
        assert ws._cargar_registro() == []
        assert not ws.BASELINE_PATH.exists()
        assert not (reports / "snapshot_otro.json").exists()
        for nombre in ("informe.pdf", "informe.doc", "informe.html"):
            assert not (reports / nombre).exists()
        assert (reports / "nota.txt").exists()
        assert (kb.version(), len(kb.entradas())) == kb_antes
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()
        ws.REGISTRO_PATH = old_reg
        ws.BASELINE_PATH = old_base
        shutil.rmtree(tmp, ignore_errors=True)


def test_cabeceras_seguridad_en_respuestas():
    import http.client
    import urllib.request
    import urllib.error
    import diagusb.web_server as ws

    def comprobar(cabeceras):
        assert cabeceras.get("Content-Security-Policy") == ws.CSP
        assert cabeceras.get("X-Frame-Options") == "DENY"
        assert cabeceras.get("X-Content-Type-Options") == "nosniff"
        assert cabeceras.get("Cache-Control") == "no-store"
        assert cabeceras.get("Referrer-Policy") == "no-referrer"

    httpd, base = _abrir_servidor()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(base + "/", headers=_cookie()),
                timeout=10) as r:
            assert r.status == 200
            comprobar(r.headers)

        with urllib.request.urlopen(
                urllib.request.Request(base + "/api/registro",
                                       headers=_cookie()), timeout=10) as r:
            assert r.status == 200
            comprobar(r.headers)

        try:
            urllib.request.urlopen(base + "/api/registro", timeout=10)
            raise AssertionError("sin cookie debio dar 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401
            comprobar(e.headers)

        try:
            urllib.request.urlopen(
                urllib.request.Request(base + "/noexiste", headers=_cookie()),
                timeout=10)
            raise AssertionError("ruta inexistente debio dar 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
            comprobar(e.headers)

        host = httpd.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", host, timeout=10)
        conn.request("GET", "/?t=" + ws._token_sesion())
        respuesta = conn.getresponse()
        assert respuesta.status == 302
        comprobar(respuesta.headers)
        respuesta.read()
        conn.close()

        cuerpo = json.dumps({"diagnostico": _diag_minimo()}).encode("utf-8")
        cabeceras = dict(_cookie())
        cabeceras["Content-Type"] = "application/json"
        req = urllib.request.Request(base + "/api/report?format=pdf",
                                     data=cuerpo, headers=cabeceras)
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status == 200
            comprobar(r.headers)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_deteccion_virtual_por_fabricante_y_modelo():
    import subprocess

    raiz = Path(__file__).parent.parent
    common = raiz / "collectors" / "_common.ps1"
    contexto = (raiz / "src" / "diagusb" / "packages" / "contexto" /
                "collectors" / "get_system_context.ps1")
    texto = contexto.read_text(encoding="utf-8")
    assert "HypervisorPresent" not in texto
    assert "Test-DiagUsbVirtual" in texto

    casos = [
        ("Dell Inc.", "Precision 3620", False),
        ("LENOVO", "ThinkCentre M720", False),
        ("HP", "EliteDesk 800 G4", False),
        ("VMware, Inc.", "VMware Virtual Platform", True),
        ("innotek GmbH", "VirtualBox", True),
        ("QEMU", "Standard PC (Q35 + ICH9, 2009)", True),
        ("Red Hat", "KVM", True),
        ("Xen", "HVM domU", True),
        ("Parallels Software International Inc.", "Parallels Virtual Platform", True),
        ("Microsoft Corporation", "Virtual Machine", True),
    ]
    filas = ",\n".join(
        f"@('{m}','{model}',${str(esperado).lower()})"
        for m, model, esperado in casos
    )
    codigo = (
        "$ErrorActionPreference='Stop'; "
        f". '{common}'; "
        f"$casos=@({filas}); "
        "foreach ($c in $casos) { "
        "$r=Test-DiagUsbVirtual -Manufacturer $c[0] -Model $c[1]; "
        "if ($r -ne [bool]$c[2]) { "
        "Write-Output ('FALLA|' + $c[0] + '|' + $c[1]); exit 1 } }; "
        "Write-Output 'OK'"
    )
    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", codigo],
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert resultado.stdout.strip().endswith("OK"), resultado.stdout


def test_hardware_recolecta_inventario_detallado():
    """El colector de hardware expone firmware, chasis, ranuras y salud de disco."""
    raiz = Path(__file__).parent.parent
    texto = (raiz / "src" / "diagusb" / "packages" / "inventario_general"
             / "collectors" / "get_hardware.ps1").read_text(encoding="utf-8")
    for requerido in (
        "Win32_SystemEnclosure",
        "$env:firmware_type",
        "Confirm-SecureBootUEFI",
        "Get-PhysicalDisk",
        "smbios_version",
        "modo_arranque",
        "secure_boot",
        '"tpm" = $tpmEstado'.replace('"tpm"', 'tpm'),
        "chassis_descriptions",
        "device_locator",
        "bank_label",
        "health_status",
        "physical_media_type",
        "requiere_admin",
        "no_aplica",
    ):
        assert requerido in texto, requerido
    # TPM solo se consulta elevado; sin admin queda "requiere_admin"
    guardia = texto.index("if ($esAdmin)")
    consulta = texto.index("'root\\cimv2\\Security\\MicrosoftTpm'")
    assert guardia < consulta
    # Secure Boot solo en UEFI; en Legacy queda "no_aplica"
    guardia_uefi = texto.index("if ($firmwareType -ieq 'UEFI')")
    confirmacion = texto.index("Confirm-SecureBootUEFI")
    assert guardia_uefi < confirmacion


def test_bateria_colector_y_reporte_xml_simulado():
    """El colector de bateria usa powercfg, borra el XML y calcula el desgaste."""
    raiz = Path(__file__).parent.parent
    texto = (raiz / "src" / "diagusb" / "packages" / "bateria"
             / "collectors" / "get_battery.ps1").read_text(encoding="utf-8")
    for requerido in (
        "powercfg.exe /batteryreport /XML",
        "Get-DiagUsbBatteryReportInfo",
        "finally",
        "Remove-Item",
        "DIAGUSB_NOT_AVAILABLE",
        "desgaste_percent",
        "fuente_capacidad",
        "carga_percent",
    ):
        assert requerido in texto, requerido
    # el XML temporal se crea y se borra SIEMPRE (try/finally)
    creacion = texto.index("$reporte = Join-Path")
    borrado = texto.index("Remove-Item -LiteralPath $reporte")
    assert borrado > creacion
    assert "Remove-Item -LiteralPath $reporte -Force" in texto

    common = raiz / "collectors" / "_common.ps1"
    xml_simulado = (
        "<BatteryInformation>"
        "<Battery><Id>BAT-PRUEBA</Id><Manufacturer>FabPrueba</Manufacturer>"
        "<Chemistry>LION</Chemistry>"
        "<DesignCapacity>96000</DesignCapacity>"
        "<FullChargeCapacity>52800</FullChargeCapacity>"
        "<CycleCount>320</CycleCount></Battery>"
        "</BatteryInformation>")
    codigo = (
        "$ErrorActionPreference='Stop'; "
        f". '{common}'; "
        "$xml = Join-Path $env:TEMP ('diagusb_pruebas_xml_' + "
        "[Guid]::NewGuid().ToString('N') + '.xml'); "
        f"[IO.File]::WriteAllText($xml, '{xml_simulado}'); "
        "try { "
        "$info = Get-DiagUsbBatteryReportInfo -XmlPath $xml; "
        "$b = @($info)[0]; "
        "Write-Output ($b.id + '|' + $b.design_capacity_mwh + '|' + "
        "$b.full_charge_capacity_mwh + '|' + $b.ciclos + '|' + $b.fabricante) "
        "} finally { Remove-Item -LiteralPath $xml -Force "
        "-ErrorAction SilentlyContinue }"
    )
    import subprocess

    from diagusb.core.procesos import opciones_sin_ventana

    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", codigo],
        capture_output=True, text=True, timeout=40,
        **opciones_sin_ventana())
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    partes = resultado.stdout.strip().split("|")
    assert partes[0] == "BAT-PRUEBA", resultado.stdout
    assert partes[1] == "96000", resultado.stdout
    assert partes[2] == "52800", resultado.stdout
    assert partes[3] == "320", resultado.stdout
    assert partes[4] == "FabPrueba", resultado.stdout


def test_ip_configuration_entrega_dhcp_y_mac_gateway():
    """El colector de IP incluye servidor DHCP y MAC del gateway por ARP."""
    raiz = Path(__file__).parent.parent
    texto = (raiz / "src" / "diagusb" / "packages" / "conectividad"
             / "collectors" / "get_ip_configuration.ps1").read_text(
                 encoding="utf-8")
    for requerido in (
        "Win32_NetworkAdapterConfiguration",
        "dhcp_server",
        "gateway_mac",
        "Get-DiagUsbGatewayMac",
    ):
        assert requerido in texto, requerido
    comun = (raiz / "collectors" / "_common.ps1").read_text(encoding="utf-8")
    for requerido in ("Get-NetNeighbor", "LinkLayerAddress", "no_disponible"):
        assert requerido in comun, requerido


def test_gateway_mac_arp_simulado_devuelve_no_disponible():
    """Con la tabla ARP simulada, sin entrada del gateway devuelve no_disponible.

    Usa el rango de documentacion 192.0.2.x y una tabla ARP inyectada:
    no consulta la red real.
    """
    import subprocess

    from diagusb.core.procesos import opciones_sin_ventana

    if os.name != "nt":
        return
    common = Path(__file__).parent.parent / "collectors" / "_common.ps1"
    comando = (
        f". '{common}'; "
        "$v = @([pscustomobject]@{IPAddress='192.0.2.99';"
        "State='Stale';LinkLayerAddress='AA-BB-CC-DD-EE-FF'}); "
        "$con = Get-DiagUsbGatewayMac -GatewayIp '192.0.2.99' -Vecinos $v; "
        "$v2 = @([pscustomobject]@{IPAddress='192.0.2.99';"
        "State='Inarp';LinkLayerAddress='AA-BB-CC-DD-EE-FF'}); "
        "$inarp = Get-DiagUsbGatewayMac -GatewayIp '192.0.2.99' -Vecinos $v2; "
        "$sin = Get-DiagUsbGatewayMac -GatewayIp '192.0.2.99' -Vecinos @(); "
        "Write-Output $con; Write-Output $inarp; Write-Output $sin"
    )
    resultado = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-Command", comando],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, **opciones_sin_ventana(),
    )
    assert resultado.returncode == 0, resultado.stderr
    lineas = [l for l in resultado.stdout.strip().splitlines() if l]
    assert lineas[0] == "AA-BB-CC-DD-EE-FF", lineas
    assert lineas[1] == "no_disponible", lineas
    assert lineas[2] == "no_disponible", lineas


def run_tests():
    """Ejecuta todas las pruebas de esta suite."""
    tests = [
        ("test_saneamiento_redacta_estructuras", test_saneamiento_redacta_estructuras),
        ("test_wifi_colector_no_pide_clave", test_wifi_colector_no_pide_clave),
        ("test_api_snapshot_sanea_antes_de_guardar",
         test_api_snapshot_sanea_antes_de_guardar),
        ("test_registro_sanea_findings", test_registro_sanea_findings),
        ("test_api_registro_redacta_legado", test_api_registro_redacta_legado),
        ("test_api_borrar_datos_locales", test_api_borrar_datos_locales),
        ("test_cabeceras_seguridad_en_respuestas",
         test_cabeceras_seguridad_en_respuestas),
        ("test_deteccion_virtual_por_fabricante_y_modelo",
         test_deteccion_virtual_por_fabricante_y_modelo),
        ("test_hardware_recolecta_inventario_detallado",
         test_hardware_recolecta_inventario_detallado),
        ("test_bateria_colector_y_reporte_xml_simulado",
         test_bateria_colector_y_reporte_xml_simulado),
        ("test_ip_configuration_entrega_dhcp_y_mac_gateway",
         test_ip_configuration_entrega_dhcp_y_mac_gateway),
        ("test_saneo_enmascara_gateway_mac_y_dhcp_server",
         test_saneo_enmascara_gateway_mac_y_dhcp_server),
        ("test_gateway_mac_arp_simulado_devuelve_no_disponible",
         test_gateway_mac_arp_simulado_devuelve_no_disponible),
        ("test_agrupa_mismo_problema", test_agrupa_mismo_problema),
        ("test_agrupa_sin_repetidos_no_altera", test_agrupa_sin_repetidos_no_altera),
        ("test_diagnose_symptoms_agrupa", test_diagnose_symptoms_agrupa),
        ("test_updates_pendientes_con_criticas", test_updates_pendientes_con_criticas),
        ("test_updates_pendientes_sin_criticas", test_updates_pendientes_sin_criticas),
        ("test_updates_sin_pendientes", test_updates_sin_pendientes),
        ("test_wifi_senal_debil", test_wifi_senal_debil),
        ("test_wifi_senal_fuerte", test_wifi_senal_fuerte),
        ("test_bsod_reciente_error", test_bsod_reciente_error),
        ("test_bsod_viejo_warning", test_bsod_viejo_warning),
        ("test_informe_diferencias_y_grupo", test_informe_diferencias_y_grupo),
        ("test_informe_sin_diferencias", test_informe_sin_diferencias),
        ("test_resumen_datos_humano", test_resumen_datos_humano),
        ("test_fmt_fecha_informe", test_fmt_fecha_informe),
        ("test_informe_secciones_correlativas", test_informe_secciones_correlativas),
        ("test_doc_css_y_anexo_opcional", test_doc_css_y_anexo_opcional),
        ("test_pdf_fecha_y_secciones", test_pdf_fecha_y_secciones),
        ("test_informe_grafico_html_doc_pdf", test_informe_grafico_html_doc_pdf),
        ("test_informe_grafico_sin_metricas", test_informe_grafico_sin_metricas),
        ("test_pdf_panel_omite_graficos_vacios", test_pdf_panel_omite_graficos_vacios),
        ("test_api_report_incluye_grafico", test_api_report_incluye_grafico),
        ("test_api_report_metricas_recalculadas", test_api_report_metricas_recalculadas),
        ("test_informe_cifras_coherentes", test_informe_cifras_coherentes),
        ("test_informe_recomendaciones_coherentes", test_informe_recomendaciones_coherentes),
        ("test_kb_guardar_y_eliminar", test_kb_guardar_y_eliminar),
        ("test_kb_valida_campos", test_kb_valida_campos),
        ("test_kb_embebida_intacta", test_kb_embebida_intacta),
        ("test_run_diagnostic_contadores", test_run_diagnostic_contadores),
        ("test_progreso_diagnostico", test_progreso_diagnostico),
        ("test_procesos_sin_ventana", test_procesos_sin_ventana),
        ("test_elevation_comando_y_desactivacion", test_elevation_comando_y_desactivacion),
        ("test_elevation_rechazo_uac", test_elevation_rechazo_uac),
        ("test_elevation_hijo_terminado", test_elevation_hijo_terminado),
        ("test_elevation_hijo_sirve_puerto", test_elevation_hijo_sirve_puerto),
        ("test_outdated_drivers_advertencias_y_genericos", test_outdated_drivers_advertencias_y_genericos),
        ("test_outdated_drivers_sin_alertas", test_outdated_drivers_sin_alertas),
        ("test_registro_persistente_unitario", test_registro_persistente_unitario),
        ("test_registro_poda_y_full_scan", test_registro_poda_y_full_scan),
        ("test_api_registro_endpoints", test_api_registro_endpoints),
        ("test_sin_servidor_de_archivos", test_sin_servidor_de_archivos),
        ("test_bind_solo_loopback", test_bind_solo_loopback),
        ("test_sin_cabeceras_cors", test_sin_cabeceras_cors),
        ("test_validacion_host_y_origin", test_validacion_host_y_origin),
        ("test_post_exige_json", test_post_exige_json),
        ("test_token_sesion", test_token_sesion),
        ("test_limite_de_cuerpo", test_limite_de_cuerpo),
        ("test_nombre_informe_seguro", test_nombre_informe_seguro),
        ("test_id_registro_validado", test_id_registro_validado),
        ("test_escritura_atomica_normal", test_escritura_atomica_normal),
        ("test_escritura_atomica_fallo_preserva_original",
         test_escritura_atomica_fallo_preserva_original),
        ("test_registro_corrupto_preservado", test_registro_corrupto_preservado),
        ("test_kb_corrupta_preservada", test_kb_corrupta_preservada),
        ("test_identidad_coincide_unitario", test_identidad_coincide_unitario),
        ("test_identidad_equipo_comparacion", test_identidad_equipo_comparacion),
        ("test_integridad_colectores", test_integridad_colectores),
        ("test_run_diagnostic_integridad_fallida", test_run_diagnostic_integridad_fallida),
        ("test_generar_manifiesto", test_generar_manifiesto),
        ("test_web_server_rutas_base", test_web_server_rutas_base),
        ("test_rutas_portables", test_rutas_portables),
        ("test_rutas_modo_instalado", test_rutas_modo_instalado),
        ("test_entry_gui_puerto_elevado", test_entry_gui_puerto_elevado),
        ("test_codigo_verificacion_informe", test_codigo_verificacion_informe),
        ("test_obs_a_dict_conserva_contexto", test_obs_a_dict_conserva_contexto),
        ("test_banner_flush", test_banner_flush),
        ("test_pdf_valido_casos", test_pdf_valido_casos),
        ("test_pdf_validador_externo", test_pdf_validador_externo),
        ("test_arranque_sin_elevar", test_arranque_sin_elevar),
        ("test_api_elevar_token", test_api_elevar_token),
        ("test_api_apagar_token", test_api_apagar_token),
        ("test_api_latido_y_despedida", test_api_latido_y_despedida),
        ("test_watchdog_cierra_al_cerrar_pestana", test_watchdog_cierra_al_cerrar_pestana),
        ("test_reglas_colector_denied", test_reglas_colector_denied),
        ("test_linea_alcance_informes", test_linea_alcance_informes),
        ("test_datos_limitados_alcance", test_datos_limitados_alcance),
        ("test_physical_disks_usb_no_limita", test_physical_disks_usb_no_limita),
        ("test_colector_temperatura_cpu_lhm", test_colector_temperatura_cpu_lhm),
        ("test_manual_colector_temperatura_cpu_lhm",
         test_manual_colector_temperatura_cpu_lhm),
        ("test_pagina_desde_static", test_pagina_desde_static),
        ("test_atributos_cuerpo_escapados", test_atributos_cuerpo_escapados),
        ("test_pagina_inyectada_datos", test_pagina_inyectada_datos),
        ("test_modulos_y_fetch_sin_cambios", test_modulos_y_fetch_sin_cambios),
        ("test_run_powershell_timeout_termina_arbol",
         test_run_powershell_timeout_termina_arbol),
        ("test_graficos_png_valido", test_graficos_png_valido),
        ("test_doc_mhtml_con_imagenes", test_doc_mhtml_con_imagenes),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas de mejoras (agrupación, reglas, informe, KB)...")
    print("=" * 50)

    for name, test_func in tests:
        try:
            test_func()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FALLO] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            failed += 1

    print("=" * 50)
    print(f"Resultados: {passed} pasadas, {failed} fallidas")

    return failed == 0


def test_run_diagnostic_integridad_falla():
    """Un colector con hash falso se omite y se reporta; los demás corren."""
    import diagusb.web_server as ws
    from diagusb.core import integridad

    ejecutados = []

    def fake_powershell(script_path, timeout=30):
        ejecutados.append(Path(script_path).name)
        return {"collector_id": "x", "query": {"status": "ok"},
                "data": {}, "errors": []}

    def verificar_falso(ruta):
        if Path(ruta).name == "get_critical_services.ps1":
            return False, "hash no coincide"
        return True, ""

    original_powershell = ws.run_powershell
    original_verificar = integridad.verificar
    ws.run_powershell = fake_powershell
    integridad.verificar = verificar_falso
    try:
        diag = ws.run_diagnostic("servicios")
    finally:
        ws.run_powershell = original_powershell
        integridad.verificar = original_verificar

    assert not diag.get("error"), diag.get("error")
    assert diag.get("integridad_fallida") == ["get_critical_services"], \
        f"Se esperaba integridad_fallida con el manifiesto falso, obtuvimos: {diag.get('integridad_fallida')}"
    assert "get_critical_services.ps1" not in ejecutados
    assert ejecutados, "los demás colectores deberían haberse ejecutado"



if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
