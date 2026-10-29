# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas de la entrega opcional: correo SMTP y copia en carpeta.

Ninguna prueba abre una conexion real: el envio usa un servidor SMTP falso
inyectado. Todo se escribe en directorios temporales.
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core import entrega


class SMTPFalso:
    """Servidor SMTP en memoria que registra lo que recibe."""

    instancias: list["SMTPFalso"] = []

    def __init__(self, host, puerto, seguridad, **_kw):
        self.host = host
        self.puerto = puerto
        self.seguridad = seguridad
        self.ehlo_veces = 0
        self.starttls_llamado = False
        self.login_datos = None
        self.mensaje = None
        self.cerrado = False
        self.error_login = None
        SMTPFalso.instancias.append(self)

    def ehlo(self):
        self.ehlo_veces += 1

    def starttls(self, context=None):
        self.starttls_llamado = True

    def login(self, usuario, clave):
        if self.error_login:
            raise self.error_login
        self.login_datos = (usuario, clave)

    def send_message(self, mensaje):
        self.mensaje = mensaje

    def quit(self):
        self.cerrado = True


def factory_falso(host, puerto, seguridad):
    return SMTPFalso(host, puerto, seguridad)


@pytest.fixture(autouse=True)
def _limpiar_instancias():
    SMTPFalso.instancias = []
    yield
    SMTPFalso.instancias = []


def config_valida(**cambios):
    correo = {
        "habilitado": True,
        "servidor": "smtp.ejemplo.test",
        "puerto": 587,
        "seguridad": "starttls",
        "usuario": "tecnico@ejemplo.test",
        "remitente": "tecnico@ejemplo.test",
        "destinatarios": ["cliente@ejemplo.test", "jefe@ejemplo.test"],
        "asunto": "Informe de prueba",
    }
    correo.update(cambios)
    return {"correo": correo}


def adjuntos_demo() -> list[dict]:
    return [
        {"nombre": "informe.pdf", "tipo": "application/pdf", "datos": b"%PDF-1.4 demo"},
        {"nombre": "informe.html", "tipo": "text/html", "datos": b"<html>demo</html>"},
    ]


def diagnostico_demo() -> dict:
    return {
        "package": "disco",
        "package_label": "Disco",
        "symptom": "disco_lleno",
        "results": [],
        "findings": [],
        "collectors_count": 1,
        "ok_count": 1,
        "error_count": 0,
    }


def test_por_defecto_todo_deshabilitado(tmp_path):
    estado = entrega.estado(base_dir=tmp_path)
    assert estado["config"]["correo"]["habilitado"] is False
    assert estado["config"]["copia"]["habilitada"] is False
    assert estado["consentimiento_requerido"] is True
    assert estado["secreto_guardado"] is False
    assert estado["entregas"] == []


def test_config_invalida_se_rechaza(tmp_path):
    with pytest.raises(entrega.EntregaError):
        entrega.guardar_config({"correo": {"habilitado": True}},
                               base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError):
        entrega.guardar_config({"correo": {"puerto": 70000}}, base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError):
        entrega.guardar_config(
            {"correo": {"destinatarios": ["no-es-un-correo"]}},
            base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError):
        entrega.guardar_config({"correo": {"seguridad": "ninguna"}},
                               base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError):
        entrega.guardar_config({"correo": {"seguridad": "ninguna",
                                           "servidor": "10.0.0.5"}},
                               base_dir=tmp_path)


def test_config_nunca_guarda_contrasena(tmp_path):
    cfg = entrega.guardar_config(
        {"correo": dict(config_valida()["correo"], clave="super-secreta",
                        password="super-secreta", contrasena="super-secreta")},
        base_dir=tmp_path)
    texto = (tmp_path / "entrega.json").read_text(encoding="utf-8")
    assert "super-secreta" not in texto
    assert "clave" not in json.dumps(cfg["correo"])
    assert cfg["correo"]["habilitado"] is True


def test_envio_sin_consentimiento_no_hace_nada(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError, match="consentimiento"):
        entrega.enviar_correo(adjuntos_demo(), consentimiento=False,
                              clave="x", base_dir=tmp_path,
                              smtp_factory=factory_falso)
    assert SMTPFalso.instancias == []


def test_envio_deshabilitado_se_rechaza(tmp_path):
    with pytest.raises(entrega.EntregaError, match="deshabilitado"):
        entrega.enviar_correo(adjuntos_demo(), consentimiento=True,
                              clave="x", base_dir=tmp_path,
                              smtp_factory=factory_falso)


def test_envio_real_contra_smtp_falso(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)
    resultado = entrega.enviar_correo(
        adjuntos_demo(), consentimiento=True, clave="clave-smtp",
        cliente="Taller", base_dir=tmp_path, smtp_factory=factory_falso)

    assert resultado["ok"] is True
    assert resultado["destinatarios"] == ["cliente@ejemplo.test",
                                          "jefe@ejemplo.test"]
    assert resultado["bytes"] == sum(len(a["datos"]) for a in adjuntos_demo())

    servidor = SMTPFalso.instancias[0]
    assert servidor.host == "smtp.ejemplo.test"
    assert servidor.puerto == 587
    assert servidor.starttls_llamado is True
    assert servidor.ehlo_veces == 2
    assert servidor.login_datos == ("tecnico@ejemplo.test", "clave-smtp")
    assert servidor.mensaje is not None
    assert "cliente@ejemplo.test" in servidor.mensaje["To"]
    assert servidor.mensaje["Subject"] == "Informe de prueba"
    adjuntos = list(servidor.mensaje.iter_attachments())
    assert [a.get_filename() for a in adjuntos] == ["informe.pdf", "informe.html"]
    assert servidor.cerrado is True

    entregas = entrega.ultimas_entregas(base_dir=tmp_path)
    assert entregas[0]["tipo"] == "correo"
    assert entregas[0]["ok"] is True
    assert "clave-smtp" not in json.dumps(entregas)


def test_error_de_conexion_se_informa_y_se_registra(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)

    def factory_rota(host, puerto, seguridad):
        raise OSError("host inalcanzable")

    with pytest.raises(entrega.EntregaError, match="No se pudo enviar"):
        entrega.enviar_correo(adjuntos_demo(), consentimiento=True,
                              clave="x", base_dir=tmp_path,
                              smtp_factory=factory_rota)
    entregas = entrega.ultimas_entregas(base_dir=tmp_path)
    assert entregas[0]["ok"] is False
    assert "host inalcanzable" in entregas[0]["detalle"]


def test_falta_contrasena_si_hay_usuario(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError, match="contrasena"):
        entrega.enviar_correo(adjuntos_demo(), consentimiento=True,
                              base_dir=tmp_path, smtp_factory=factory_falso)


def test_probar_conexion_no_envia_mensaje(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)
    resultado = entrega.probar_conexion(clave="clave-smtp", base_dir=tmp_path,
                                        smtp_factory=factory_falso)
    assert resultado["ok"] is True
    assert resultado["autenticado"] is True
    servidor = SMTPFalso.instancias[0]
    assert servidor.mensaje is None
    assert servidor.cerrado is True


def test_adjuntos_demasiado_grandes_se_rechazan():
    grande = [{"nombre": "informe.pdf", "tipo": "application/pdf",
               "datos": b"x" * (entrega.LIMITE_ADJUNTOS_BYTES + 1)}]
    with pytest.raises(entrega.EntregaError, match="limite"):
        entrega._validar_adjuntos(grande)


def test_adjunto_con_tipo_invalido_se_rechaza():
    with pytest.raises(entrega.EntregaError, match="Tipo"):
        entrega._validar_adjuntos([
            {"nombre": "informe.pdf", "tipo": "pdf", "datos": b"x"}])


def test_generar_adjuntos_del_informe(tmp_path):
    adjuntos = entrega.generar_adjuntos(diagnostico_demo(),
                                        tecnico="Tecnico", cliente="Taller")
    nombres = [a["nombre"] for a in adjuntos]
    assert nombres[0].startswith("informe_disco_")
    extensiones = {Path(n).suffix for n in nombres}
    assert extensiones == {".pdf", ".html", ".json"}

    pdf = next(a for a in adjuntos if a["nombre"].endswith(".pdf"))
    assert pdf["datos"].startswith(b"%PDF")
    datos_json = json.loads(next(a for a in adjuntos
                                 if a["nombre"].endswith(".json"))["datos"])
    assert datos_json["tipo"]
    assert "problemas" in datos_json
    assert datos_json["tecnico"] == "Tecnico"


def test_copia_en_carpeta_con_consentimiento(tmp_path):
    destino = tmp_path / "nube"
    destino.mkdir()
    resultado = entrega.guardar_copia(adjuntos_demo(), consentimiento=True,
                                      destino=str(destino), base_dir=tmp_path)
    ruta = Path(resultado["archivo"])
    assert ruta.exists()
    assert ruta.parent == destino
    with zipfile.ZipFile(ruta) as archivo:
        assert sorted(archivo.namelist()) == ["informe.html", "informe.pdf"]
    assert entrega.ultimas_entregas(base_dir=tmp_path)[0]["tipo"] == "copia"


def test_copia_sin_consentimiento_o_carpeta_no_existe(tmp_path):
    destino = tmp_path / "nube"
    destino.mkdir()
    with pytest.raises(entrega.EntregaError, match="consentimiento"):
        entrega.guardar_copia(adjuntos_demo(), consentimiento=False,
                              destino=str(destino), base_dir=tmp_path)
    with pytest.raises(entrega.EntregaError, match="no existe"):
        entrega.guardar_copia(adjuntos_demo(), consentimiento=True,
                              destino=str(tmp_path / "fantasma"),
                              base_dir=tmp_path)
    assert list(destino.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="DPAPI solo existe en Windows")
def test_secreto_cifrado_con_dpapi(tmp_path):
    clave = "contrasena-de-prueba-123"
    entrega.guardar_secreto(clave, base_dir=tmp_path)
    archivo = tmp_path / "correo_secreto.bin"
    assert archivo.exists()
    assert clave.encode("utf-8") not in archivo.read_bytes()
    assert entrega.hay_secreto(base_dir=tmp_path) is True
    assert entrega.leer_secreto(base_dir=tmp_path) == clave

    entrega.olvidar_secreto(base_dir=tmp_path)
    assert entrega.hay_secreto(base_dir=tmp_path) is False
    assert entrega.leer_secreto(base_dir=tmp_path) == ""


@pytest.mark.skipif(os.name != "nt", reason="DPAPI solo existe en Windows")
def test_envio_usa_el_secreto_guardado(tmp_path):
    entrega.guardar_config(config_valida(), base_dir=tmp_path)
    entrega.guardar_secreto("clave-guardada", base_dir=tmp_path)
    entrega.enviar_correo(adjuntos_demo(), consentimiento=True,
                          base_dir=tmp_path, smtp_factory=factory_falso)
    assert SMTPFalso.instancias[0].login_datos[1] == "clave-guardada"


# ---------------------------------------------------------------------------
# API HTTP
# ---------------------------------------------------------------------------

def _abrir_servidor():
    import socketserver
    import threading

    import diagusb.web_server as ws

    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = ThreadedTCPServer((ws.BIND_HOST, 0), ws.DiagUSBHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _peticion(base: str, ruta: str, cuerpo: dict | None = None):
    import urllib.error
    import urllib.request

    import diagusb.web_server as ws

    datos = None
    cabeceras = {"Cookie": f"diagusb_token={ws._token_sesion()}"}
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    req = urllib.request.Request(base + ruta, data=datos, headers=cabeceras)
    try:
        with urllib.request.urlopen(req, timeout=20) as respuesta:
            return respuesta.status, json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def test_api_estado_y_validaciones(tmp_path, monkeypatch):
    monkeypatch.setattr(entrega, "_ruta_config",
                        lambda base_dir=None: tmp_path / "entrega.json")
    monkeypatch.setattr(entrega, "_ruta_secreto",
                        lambda base_dir=None: tmp_path / "correo_secreto.bin")
    monkeypatch.setattr(entrega, "_ruta_bitacora",
                        lambda base_dir=None: tmp_path / "entregas.json")

    httpd, base = _abrir_servidor()
    try:
        estado_http, estado = _peticion(base, "/api/entrega")
        assert estado_http == 200
        assert estado["config"]["correo"]["habilitado"] is False

        codigo, cuerpo = _peticion(base, "/api/entrega/config",
                                   {"correo": {"puerto": 99999}})
        assert codigo == 400
        assert "puerto" in cuerpo["error"].lower()

        codigo, cuerpo = _peticion(base, "/api/entrega/enviar", {
            "diagnostico": diagnostico_demo(),
            "consentimiento": False,
        })
        assert codigo == 400
        assert "consentimiento" in cuerpo["error"].lower()

        codigo, cuerpo = _peticion(base, "/api/entrega/copia", {
            "diagnostico": diagnostico_demo(),
            "consentimiento": False,
        })
        assert codigo == 400
        assert "consentimiento" in cuerpo["error"].lower()
    finally:
        httpd.shutdown()
        httpd.server_close()
