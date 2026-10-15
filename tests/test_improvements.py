# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de las mejoras: agrupacion, reglas nuevas, informe, KB editable y contadores."""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core import knowledge_base as kb
from diagusb.core.informe import (
    _resumen_datos,
    informe_a_html,
    informe_a_pdf,
    informe_desde_diagnostico,
)
from diagusb.core.models import CollectorResult, Finding
from diagusb.core.rules import RuleEngine, _agrupar_findings


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
        {"ssid": "Casa", "signal": 25},
        {"ssid": "Oficina", "signal": [80, 75]},
    ])
    findings = engine._check_wifi_signal([r])
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "Casa" in findings[0].message
    assert "Oficina" not in findings[0].message


def test_wifi_senal_fuerte():
    engine = RuleEngine()
    r = create_mock_result("wifi_networks", [{"ssid": "Casa", "signal": [90, 85]}])
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
    assert "Cambios detectados (antes vs después)" in html
    assert "Cómo debe estar (estado esperado)" in html
    assert "Espacio limitado en disco D: 9.0% libre" in html

    pdf = informe_a_pdf(inf)
    assert pdf.startswith(b"%PDF")
    texto = pdf.decode("latin-1", errors="replace")
    assert "antes vs despu" in texto
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


# ---------------------------------------------------------------------------
# Base de conocimiento editable (capa local en un archivo temporal)
# ---------------------------------------------------------------------------

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
    entrada = kb.buscar("wifi_debil")
    assert "40%" in entrada["estado_esperado"]


# ---------------------------------------------------------------------------
# Contadores del servidor web (ok / error / empty) con PowerShell simulado
# ---------------------------------------------------------------------------

def test_run_diagnostic_contadores():
    import diagusb.web_server as ws

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

    original = ws.run_powershell
    ws.run_powershell = fake_powershell
    try:
        diag = ws.run_diagnostic("servicios")
    finally:
        ws.run_powershell = original

    assert not diag.get("error"), diag.get("error")
    assert diag["collectors_count"] == n
    esperados_ok = sum(1 for i in range(n) if i % 3 == 0)
    esperados_empty = sum(1 for i in range(n) if i % 3 == 1)
    esperados_error = sum(1 for i in range(n) if i % 3 == 2)
    assert diag["ok_count"] == esperados_ok
    assert diag["empty_count"] == esperados_empty
    assert diag["error_count"] == esperados_error
    assert isinstance(diag.get("is_elevated"), (bool, type(None)))


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
    import http.client
    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(path, ctype=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = dict(_cookie())
        if ctype:
            headers["Content-Type"] = ctype
        conn.request("POST", path, body="{}", headers=headers)
        r = conn.getresponse()
        r.read()
        conn.close()
        return r.status

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
    assert not ws._identidad_coincide(a, {"computer_name": "PC-B", "hardware_id": "S1"})
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
        texto = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
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
    gen.DESTINO = tmp
    assert gen.main() == 0
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


def run_tests():
    """Ejecuta todas las pruebas de esta suite."""
    tests = [
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
        ("test_kb_guardar_y_eliminar", test_kb_guardar_y_eliminar),
        ("test_kb_valida_campos", test_kb_valida_campos),
        ("test_kb_embebida_intacta", test_kb_embebida_intacta),
        ("test_run_diagnostic_contadores", test_run_diagnostic_contadores),
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


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)
