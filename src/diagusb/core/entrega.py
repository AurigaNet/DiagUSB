# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Entrega opcional del informe: correo SMTP y copia en carpeta.

Nada sale del equipo sin una accion explicita del tecnico: el envio por correo
y la copia requieren ``consentimiento=True`` y una configuracion habilitada a
mano. La contrasena del correo nunca se guarda en texto plano: se usa solo en
memoria o se cifra con DPAPI de Windows en ``config/correo_secreto.bin``
(ambito del usuario actual, no se puede descifrar en otro equipo).
"""

from __future__ import annotations

import ctypes
import os
import re
import smtplib
import ssl
import zipfile
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any, Callable, Iterable

from . import almacen, rutas

LIMITE_ADJUNTOS_BYTES = 25 * 1024 * 1024
MAX_DESTINATARIOS = 10
SEGURIDADES = ("starttls", "ssl", "ninguna")
_CRYPTPROTECT_UI_FORBIDDEN = 0x01

_RE_HOST = re.compile(r"^[A-Za-z0-9._-]{1,253}$")
_RE_CORREO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
_RE_TIPO_MIME = re.compile(r"^[a-z]+/[a-z0-9.+-]+$")


class EntregaError(Exception):
    """Error de configuracion o de envio que se muestra tal cual al tecnico."""


def _ruta_config(base_dir: Path | None = None) -> Path:
    return (Path(base_dir) if base_dir else rutas.dir_config()) / "entrega.json"


def _ruta_secreto(base_dir: Path | None = None) -> Path:
    return (Path(base_dir) if base_dir else rutas.dir_config()) / "correo_secreto.bin"


def _ruta_bitacora(base_dir: Path | None = None) -> Path:
    return (Path(base_dir) if base_dir else rutas.dir_config()) / "entregas.json"


def config_por_defecto() -> dict:
    """Configuracion inicial: todo apagado y sin datos del equipo."""
    return {
        "version": 1,
        "correo": {
            "habilitado": False,
            "servidor": "",
            "puerto": 587,
            "seguridad": "starttls",
            "usuario": "",
            "remitente": "",
            "destinatarios": [],
            "asunto": "Informe DiagUSB",
        },
        "copia": {
            "habilitada": False,
            "destino": "",
        },
        "actualizado_en": "",
    }


def _texto(valor: Any, limite: int = 200) -> str:
    return str("" if valor is None else valor).strip()[:limite]


def _lista_destinatarios(valor: Any) -> list[str]:
    if isinstance(valor, str):
        crudos = re.split(r"[,;\n]", valor)
    elif isinstance(valor, (list, tuple)):
        crudos = []
        for item in valor:
            crudos.extend(re.split(r"[,;\n]", str(item)))
    else:
        crudos = []
    salida: list[str] = []
    for crudo in crudos:
        correo = crudo.strip()
        if not correo:
            continue
        if not _RE_CORREO.match(correo):
            raise EntregaError(f"Direccion de correo invalida: {correo[:80]}")
        if correo.casefold() not in [c.casefold() for c in salida]:
            salida.append(correo)
    if len(salida) > MAX_DESTINATARIOS:
        raise EntregaError(f"Maximo {MAX_DESTINATARIOS} destinatarios por envio.")
    return salida


def normalizar_config(datos: dict, base: dict | None = None) -> dict:
    """Valida y normaliza una configuracion parcial sobre ``base``.

    Se descartan a proposito las claves de contrasena: la unica via para
    guardarla es ``guardar_secreto`` (cifrada con DPAPI).
    """
    actual = json_copia(base if isinstance(base, dict) else config_por_defecto())
    if not isinstance(datos, dict):
        raise EntregaError("La configuracion debe ser un objeto JSON.")

    correo_datos = datos.get("correo")
    if isinstance(correo_datos, dict):
        correo = actual["correo"]
        if "habilitado" in correo_datos:
            correo["habilitado"] = bool(correo_datos.get("habilitado"))
        if "servidor" in correo_datos:
            servidor = _texto(correo_datos.get("servidor"))
            if servidor and not _RE_HOST.match(servidor):
                raise EntregaError("El servidor SMTP solo admite un nombre de host o una IP.")
            correo["servidor"] = servidor
        if "puerto" in correo_datos:
            try:
                puerto = int(correo_datos.get("puerto"))
            except (TypeError, ValueError):
                raise EntregaError("El puerto SMTP debe ser un numero.") from None
            if not 1 <= puerto <= 65535:
                raise EntregaError("El puerto SMTP debe estar entre 1 y 65535.")
            correo["puerto"] = puerto
        if "seguridad" in correo_datos:
            seguridad = _texto(correo_datos.get("seguridad"), 20).lower()
            if seguridad not in SEGURIDADES:
                raise EntregaError("La seguridad debe ser starttls, ssl o ninguna.")
            correo["seguridad"] = seguridad
        if "usuario" in correo_datos:
            correo["usuario"] = _texto(correo_datos.get("usuario"))
        if "remitente" in correo_datos:
            remitente = _texto(correo_datos.get("remitente"))
            if remitente and not _RE_CORREO.match(remitente):
                raise EntregaError("La direccion del remitente no es valida.")
            correo["remitente"] = remitente
        if "destinatarios" in correo_datos:
            correo["destinatarios"] = _lista_destinatarios(correo_datos.get("destinatarios"))
        if "asunto" in correo_datos:
            correo["asunto"] = _texto(correo_datos.get("asunto"), 120) or "Informe DiagUSB"

    copia_datos = datos.get("copia")
    if isinstance(copia_datos, dict):
        copia = actual["copia"]
        if "habilitada" in copia_datos:
            copia["habilitada"] = bool(copia_datos.get("habilitada"))
        if "destino" in copia_datos:
            copia["destino"] = _texto(copia_datos.get("destino"), 400)

    _validar_config(actual)
    return actual


def json_copia(datos: dict) -> dict:
    """Copia profunda sencilla de un dict JSON."""
    if not isinstance(datos, dict):
        return {}
    return {clave: (json_copia(valor) if isinstance(valor, dict)
                    else [json_copia(v) if isinstance(v, dict) else v for v in valor]
                    if isinstance(valor, list) else valor)
            for clave, valor in datos.items()}


def _validar_config(cfg: dict) -> None:
    correo = cfg.get("correo") or {}
    if correo.get("habilitado"):
        if not correo.get("servidor"):
            raise EntregaError("Para habilitar el correo indique el servidor SMTP.")
        if not correo.get("destinatarios"):
            raise EntregaError("Para habilitar el correo indique al menos un destinatario.")
        if not (correo.get("remitente") or correo.get("usuario")):
            raise EntregaError("Indique el remitente o el usuario SMTP.")
    if correo.get("seguridad") == "ninguna" and not _es_loopback(correo.get("servidor")):
        raise EntregaError(
            "Sin cifrado solo se permite un servidor SMTP en este equipo "
            "(127.0.0.1 o localhost).")
    copia = cfg.get("copia") or {}
    if copia.get("habilitada") and not copia.get("destino"):
        raise EntregaError("Para habilitar la copia indique una carpeta de destino.")


def _es_loopback(host: Any) -> bool:
    texto = _texto(host, 80).lower().strip("[]")
    return texto in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def cargar_config(base_dir: Path | None = None) -> dict:
    """Lee la configuracion; si falta o esta rota devuelve la de fabrica."""
    datos = almacen.leer_json(_ruta_config(base_dir))
    base = config_por_defecto()
    if isinstance(datos, dict):
        try:
            base = normalizar_config(datos, base)
        except EntregaError:
            base = config_por_defecto()
    return base


def guardar_config(datos: dict, base_dir: Path | None = None) -> dict:
    """Valida y guarda la configuracion (sin contrasenas)."""
    actual = cargar_config(base_dir)
    nueva = normalizar_config(datos, actual)
    nueva["actualizado_en"] = datetime.now().isoformat(timespec="seconds")
    almacen.escribir_json_atomico(_ruta_config(base_dir), nueva)
    return nueva


# ---------------------------------------------------------------------------
# Secreto del correo: DPAPI (solo Windows) o memoria
# ---------------------------------------------------------------------------

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_entrada(datos: bytes) -> tuple[_BLOB, Any]:
    if not datos:
        raise EntregaError("El secreto esta vacio.")
    buffer = ctypes.create_string_buffer(datos, len(datos))
    return (_BLOB(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))),
            buffer)


def dpapi_disponible() -> bool:
    return os.name == "nt"


def _dpapi_proteger(datos: bytes) -> bytes:
    if not dpapi_disponible():
        raise EntregaError("El cifrado de la contrasena requiere Windows (DPAPI).")
    entrada, _buffer = _blob_entrada(datos)
    salida = _BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(entrada), "DiagUSB correo", None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida))
    if not ok:
        raise EntregaError(
            f"Windows no pudo cifrar la contrasena (error {ctypes.get_last_error()}).")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _dpapi_descifrar(datos: bytes) -> bytes:
    if not dpapi_disponible():
        raise EntregaError("El cifrado de la contrasena requiere Windows (DPAPI).")
    entrada, _buffer = _blob_entrada(datos)
    salida = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(entrada), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida))
    if not ok:
        raise EntregaError("Windows no pudo descifrar la contrasena guardada. "
                           "Vuelva a escribirla y guardarla.")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def hay_secreto(base_dir: Path | None = None) -> bool:
    try:
        return _ruta_secreto(base_dir).stat().st_size > 0
    except OSError:
        return False


def guardar_secreto(clave: str, base_dir: Path | None = None) -> dict:
    """Cifra y guarda la contrasena con DPAPI (nunca en texto plano)."""
    texto = str(clave or "")
    if not texto:
        raise EntregaError("La contrasena esta vacia.")
    blob = _dpapi_proteger(texto.encode("utf-8"))
    ruta = _ruta_secreto(base_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)
    return {"ok": True, "cifrado": "dpapi", "bytes": len(blob)}


def olvidar_secreto(base_dir: Path | None = None) -> dict:
    ruta = _ruta_secreto(base_dir)
    try:
        ruta.unlink()
    except FileNotFoundError:
        return {"ok": True, "borrado": False}
    return {"ok": True, "borrado": True}


def leer_secreto(base_dir: Path | None = None) -> str:
    ruta = _ruta_secreto(base_dir)
    try:
        blob = ruta.read_bytes()
    except FileNotFoundError:
        return ""
    if not blob:
        return ""
    return _dpapi_descifrar(blob).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Adjuntos e informe
# ---------------------------------------------------------------------------

def _nombre_seguro(texto: Any, defecto: str = "informe") -> str:
    limpio = "".join(c for c in str("" if texto is None else texto)
                     if c.isascii() and (c.isalnum() or c in "._-"))
    return limpio.strip("._-") or defecto


def generar_adjuntos(diag: dict, acciones: list | None = None,
                     mejoras: list | None = None, tecnico: str = "",
                     cliente: str = "", observaciones: str = "",
                     diferencias: list | None = None,
                     formatos: Iterable[str] = ("pdf", "html", "json"),
                     con_anexo: bool = False) -> list[dict]:
    """Construye los adjuntos del informe a partir del diagnostico."""
    from . import informe as modulo_informe

    if not isinstance(diag, dict) or not diag.get("package"):
        raise EntregaError("Falta el diagnostico para generar el informe.")

    informe = modulo_informe.informe_desde_diagnostico(
        diag,
        acciones=acciones,
        mejoras_acciones=mejoras,
        tecnico=tecnico,
        cliente=cliente,
        observaciones=observaciones,
        diferencias=diferencias,
    )
    paquete = _nombre_seguro(diag.get("package"))
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"informe_{paquete}_{marca}"
    adjuntos: list[dict] = []

    for formato in formatos:
        nombre_formato = str(formato).lower()
        if nombre_formato == "pdf":
            adjuntos.append({"nombre": f"{base}.pdf",
                             "tipo": "application/pdf",
                             "datos": modulo_informe.informe_a_pdf(informe)})
        elif nombre_formato == "html":
            adjuntos.append({"nombre": f"{base}.html",
                             "tipo": "text/html",
                             "datos": modulo_informe.informe_a_html(
                                 informe, con_anexo=con_anexo).encode("utf-8")})
        elif nombre_formato == "json":
            adjuntos.append({"nombre": f"{base}.json",
                             "tipo": "application/json",
                             "datos": (modulo_informe.informe_a_json(informe)
                                       .encode("utf-8"))})
        elif nombre_formato == "doc":
            adjuntos.append({"nombre": f"{base}.doc",
                             "tipo": "application/msword",
                             "datos": modulo_informe.informe_a_doc(
                                 informe, resultados_completos=diag.get("results"))})
        else:
            raise EntregaError(f"Formato de adjunto desconocido: {nombre_formato}")

    _validar_adjuntos(adjuntos)
    return adjuntos


def _validar_adjuntos(adjuntos: list[dict]) -> None:
    if not adjuntos:
        raise EntregaError("No hay ningun adjunto para entregar.")
    total = 0
    for adjunto in adjuntos:
        if not isinstance(adjunto, dict):
            raise EntregaError("Adjunto invalido.")
        nombre = adjunto.get("nombre")
        datos = adjunto.get("datos")
        tipo = adjunto.get("tipo")
        if not nombre or not isinstance(datos, (bytes, bytearray)):
            raise EntregaError("Adjunto sin nombre o sin contenido.")
        if not _RE_TIPO_MIME.match(str(tipo or "")):
            raise EntregaError(f"Tipo de adjunto invalido: {tipo}")
        total += len(datos)
    if total > LIMITE_ADJUNTOS_BYTES:
        raise EntregaError(
            f"Los adjuntos superan el limite de {LIMITE_ADJUNTOS_BYTES // (1024 * 1024)} MB.")


# ---------------------------------------------------------------------------
# Envio por correo
# ---------------------------------------------------------------------------

def _conectar(correo: dict, timeout: int = 25,
              smtp_factory: Callable | None = None):
    host = correo.get("servidor") or ""
    puerto = int(correo.get("puerto") or 0)
    seguridad = correo.get("seguridad") or "starttls"
    if smtp_factory is not None:
        conexion = smtp_factory(host, puerto, seguridad)
        if seguridad == "starttls":
            conexion.ehlo()
            conexion.starttls(context=ssl.create_default_context())
            conexion.ehlo()
        return conexion
    if seguridad == "ssl":
        return smtplib.SMTP_SSL(host, puerto, timeout=timeout,
                                context=ssl.create_default_context())
    conexion = smtplib.SMTP(host, puerto, timeout=timeout)
    if seguridad == "starttls":
        conexion.ehlo()
        conexion.starttls(context=ssl.create_default_context())
        conexion.ehlo()
    return conexion


def _cuerpo_correo(correo: dict, adjuntos: list[dict], cliente: str) -> str:
    lineas = [
        "Informe de diagnostico generado con DiagUSB.",
        "",
        "Este mensaje se envio desde el equipo diagnosticado porque el tecnico",
        "lo autorizo de forma explicita en la interfaz.",
        "",
    ]
    if cliente:
        lineas.append(f"Cliente o sector: {cliente}")
    lineas.append("Adjuntos:")
    for adjunto in adjuntos:
        lineas.append(f"  - {adjunto['nombre']} ({len(adjunto['datos'])} bytes)")
    lineas += [
        "",
        "DiagUSB no envia datos a ningun servidor propio ni guarda copias en la",
        "nube: el correo sale por el servidor SMTP configurado en este equipo.",
        "",
        "Copyright (C) 2026 Daniel Ricardo Novoa - GPL-3.0-or-later",
    ]
    return "\n".join(lineas)


def enviar_correo(adjuntos: list[dict], consentimiento: bool,
                  clave: str | None = None, cliente: str = "",
                  base_dir: Path | None = None,
                  smtp_factory: Callable | None = None) -> dict:
    """Envia los adjuntos por SMTP. Sin ``consentimiento=True`` no hace nada."""
    if consentimiento is not True:
        raise EntregaError("Se requiere consentimiento explicito para enviar el informe.")
    _validar_adjuntos(adjuntos)
    cfg = cargar_config(base_dir)
    correo = cfg.get("correo") or {}
    if not correo.get("habilitado"):
        raise EntregaError("El envio por correo esta deshabilitado en la configuracion.")
    _validar_config(cfg)

    clave_uso = str(clave or "")
    if not clave_uso:
        clave_uso = leer_secreto(base_dir)
    if correo.get("usuario") and not clave_uso:
        raise EntregaError("Falta la contrasena del correo. Escribala o guardela "
                           "cifrada con Windows.")

    remitente = correo.get("remitente") or correo.get("usuario")
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = ", ".join(correo["destinatarios"])
    mensaje["Subject"] = correo.get("asunto") or "Informe DiagUSB"
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(domain="diagusb.local")
    mensaje.set_content(_cuerpo_correo(correo, adjuntos, cliente))
    for adjunto in adjuntos:
        principal, _, secundario = adjunto["tipo"].partition("/")
        mensaje.add_attachment(adjunto["datos"], maintype=principal,
                               subtype=secundario, filename=adjunto["nombre"])

    conexion = None
    try:
        conexion = _conectar(correo, smtp_factory=smtp_factory)
        if correo.get("usuario"):
            conexion.login(correo["usuario"], clave_uso)
        conexion.send_message(mensaje)
    except EntregaError:
        raise
    except Exception as e:
        _registrar_entrega("correo", False, str(e), base_dir,
                           destinatarios=correo.get("destinatarios") or [])
        raise EntregaError(f"No se pudo enviar el correo: {e}") from None
    finally:
        if conexion is not None:
            try:
                conexion.quit()
            except Exception:
                pass

    resumen = {
        "ok": True,
        "tipo": "correo",
        "servidor": correo.get("servidor"),
        "puerto": correo.get("puerto"),
        "seguridad": correo.get("seguridad"),
        "destinatarios": list(correo.get("destinatarios") or []),
        "adjuntos": [adjunto["nombre"] for adjunto in adjuntos],
        "bytes": sum(len(adjunto["datos"]) for adjunto in adjuntos),
        "enviado_en": datetime.now().isoformat(timespec="seconds"),
    }
    _registrar_entrega("correo", True, "", base_dir,
                       destinatarios=resumen["destinatarios"],
                       adjuntos=resumen["adjuntos"])
    return resumen


def probar_conexion(clave: str | None = None, base_dir: Path | None = None,
                    smtp_factory: Callable | None = None) -> dict:
    """Comprueba el servidor SMTP y el inicio de sesion sin enviar nada."""
    cfg = cargar_config(base_dir)
    correo = cfg.get("correo") or {}
    if not correo.get("servidor"):
        raise EntregaError("Configure primero el servidor SMTP.")
    _validar_config(cfg)
    clave_uso = str(clave or "") or leer_secreto(base_dir)
    conexion = None
    try:
        conexion = _conectar(correo, smtp_factory=smtp_factory)
        if correo.get("usuario"):
            if not clave_uso:
                raise EntregaError("Falta la contrasena del correo para probar el acceso.")
            conexion.login(correo["usuario"], clave_uso)
    except EntregaError:
        raise
    except Exception as e:
        raise EntregaError(f"No se pudo conectar con el servidor SMTP: {e}") from None
    finally:
        if conexion is not None:
            try:
                conexion.quit()
            except Exception:
                pass
    return {"ok": True, "servidor": correo.get("servidor"),
            "puerto": correo.get("puerto"),
            "seguridad": correo.get("seguridad"),
            "autenticado": bool(correo.get("usuario"))}


# ---------------------------------------------------------------------------
# Copia en carpeta (por ejemplo, una carpeta sincronizada por el usuario)
# ---------------------------------------------------------------------------

def guardar_copia(adjuntos: list[dict], consentimiento: bool,
                  destino: str | None = None, base_dir: Path | None = None) -> dict:
    """Escribe un ZIP con los adjuntos en la carpeta indicada.

    No sube nada a internet: deja el archivo en una carpeta local que el
    tecnico elige (puede ser una carpeta sincronizada con su propia nube).
    """
    if consentimiento is not True:
        raise EntregaError("Se requiere consentimiento explicito para guardar la copia.")
    _validar_adjuntos(adjuntos)
    cfg = cargar_config(base_dir)
    copia = cfg.get("copia") or {}
    elegido = _texto(destino or copia.get("destino"), 400)
    if not elegido:
        raise EntregaError("Indique una carpeta de destino para la copia.")
    carpeta = Path(elegido)
    if not carpeta.exists() or not carpeta.is_dir():
        raise EntregaError("La carpeta de destino no existe o no es una carpeta.")
    if not os.access(carpeta, os.W_OK):
        raise EntregaError("No hay permisos de escritura en la carpeta de destino.")

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_zip = f"DiagUSB_copia_{marca}.zip"
    ruta = carpeta / nombre_zip
    try:
        with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as archivo:
            for adjunto in adjuntos:
                archivo.writestr(adjunto["nombre"], bytes(adjunto["datos"]))
    except OSError as e:
        _registrar_entrega("copia", False, str(e), base_dir, destino=str(carpeta))
        raise EntregaError(f"No se pudo escribir la copia: {e}") from None

    resumen = {
        "ok": True,
        "tipo": "copia",
        "archivo": str(ruta),
        "nombre": nombre_zip,
        "carpeta": str(carpeta),
        "bytes": ruta.stat().st_size,
        "archivos": [adjunto["nombre"] for adjunto in adjuntos],
        "guardado_en": datetime.now().isoformat(timespec="seconds"),
    }
    _registrar_entrega("copia", True, "", base_dir, destino=str(carpeta),
                       adjuntos=resumen["archivos"])
    return resumen


# ---------------------------------------------------------------------------
# Bitacora local (sin contrasenas ni contenido de los informes)
# ---------------------------------------------------------------------------

def _registrar_entrega(tipo: str, ok: bool, detalle: str,
                       base_dir: Path | None = None,
                       destinatarios: list | None = None,
                       destino: str = "", adjuntos: list | None = None) -> None:
    ruta = _ruta_bitacora(base_dir)
    entradas = almacen.leer_json(ruta)
    if not isinstance(entradas, list):
        entradas = []
    entradas.insert(0, {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "tipo": tipo,
        "ok": bool(ok),
        "detalle": _texto(detalle, 300),
        "destinatarios": [_texto(c, 120) for c in (destinatarios or [])],
        "destino": _texto(destino, 400),
        "adjuntos": [_texto(a, 120) for a in (adjuntos or [])],
    })
    del entradas[50:]
    try:
        almacen.escribir_json_atomico(ruta, entradas)
    except OSError:
        pass


def ultimas_entregas(limite: int = 10, base_dir: Path | None = None) -> list[dict]:
    entradas = almacen.leer_json(_ruta_bitacora(base_dir))
    if not isinstance(entradas, list):
        return []
    return [e for e in entradas if isinstance(e, dict)][:max(0, int(limite))]


def estado(base_dir: Path | None = None) -> dict:
    """Estado para la interfaz: configuracion, secreto y ultimas entregas."""
    return {
        "config": cargar_config(base_dir),
        "secreto_guardado": hay_secreto(base_dir),
        "dpapi_disponible": dpapi_disponible(),
        "consentimiento_requerido": True,
        "limite_adjuntos_bytes": LIMITE_ADJUNTOS_BYTES,
        "entregas": ultimas_entregas(10, base_dir),
    }
