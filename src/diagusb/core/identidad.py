# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Identidad estable del equipo para DiagUSB.

Componentes fuertes: ``smbios_uuid``, ``bios_serial``, ``baseboard_serial``,
``system_serial``, ``chassis_serial`` y ``chassis_asset_tag``; componente
débil: ``machine_guid`` (se duplica en imágenes clonadas, así que nunca decide
por sí solo). El ``machine_id`` es un SHA-256 corto sobre los componentes
fuertes válidos, en un orden fijo (nombre:valor), de modo que el mismo
conjunto de valores produce siempre el mismo identificador sin importar el
orden en que lleguen los datos.

Es la única fuente de verdad para comparar equipos entre instantáneas
(comparator.py) y baselines guardadas (web_server.py). Los baselines viejos
con ``{"computer_name", "hardware_id"}`` siguen comparándose con la lógica
anterior por medio del componente ``legacy``.

Los respaldos (MACs de adaptadores físicos y serial del disco de arranque)
jamás producen "distinto": solo pueden subir un "indeterminado" a
"probable".
"""

from __future__ import annotations

import hashlib

FUERTES = ("smbios_uuid", "bios_serial", "baseboard_serial",
           "system_serial", "chassis_serial", "chassis_asset_tag")
DEBILES = ("machine_guid",)
LEGACY = "legacy"

_VALORES_INVALIDOS = frozenset((
    "",
    "to be filled by o.e.m.",
    "default string",
    "system serial number",
    "serial number",
    "none",
    "n/a",
    "not specified",
    "unknown",
    "o.e.m.",
    "0",
    "123456789",
))

# UUIDs de relleno propios de algunas placas OEM (sin guiones para comparar).
_UUID_RELLENO_HEXA = frozenset((
    "03000200030004000005000600070008",
    "00020003000400050006000700080009",
))

# Rutas exactas dentro de los ``data`` de los recolectores. No se recorre
# el árbol buscando claves genéricas: cada componente se lee de su lugar.
_RUTAS = {
    "smbios_uuid": ("identidad", "smbios_uuid"),
    "machine_guid": ("identidad", "machine_guid"),
    "bios_serial": ("bios", 0, "serial_number"),
    "baseboard_serial": ("baseboards", 0, "serial_number"),
    "system_serial": ("identidad", "system_serial"),
    "chassis_serial": ("identidad", "chassis_serial"),
    "chassis_asset_tag": ("identidad", "chassis_asset_tag"),
}
# Respaldo también por rutas exactas.
_RESPALDOS_MACS = ("identidad", "macs_fisicas")
_RESPALDOS_DISCO = ("identidad", "disco_arranque")


def normalizar(valor) -> str:
    """Valor listo para comparar: strip + minúsculas."""
    return str(valor if valor is not None else "").strip().lower()


def _hexa_consecutiva(texto) -> bool:
    """True si el texto tiene una racha de 8 o más dígitos hex consecutivos
    ascendentes o descendentes.

    Los guiones y los dos puntos se quitan antes; cualquier otro carácter
    que NO sea hexadecimal corta la racha (no se ignoran letras no hex).
    Ejemplos: '12345678' y 'fedcba98' se descartan; 'a1b2c3d4e5f6' no.
    """
    limpio = normalizar(texto).replace("-", "").replace(":", "")
    previo = None
    racha = 0
    for caracter in limpio:
        if caracter not in "0123456789abcdef":
            previo = None
            racha = 0
            continue
        valor = int(caracter, 16)
        if previo is not None and abs(valor - previo) == 1:
            racha += 1
        else:
            racha = 1
        previo = valor
        if racha >= 8:
            return True
    return False


# Fichas de relleno se buscan en TODO el valor (sin distinciones):
# sirven tanto para UUIDs ("To be filled by O.E.M.") como para etiquetas.
_FRASES_RELLENO = (
    "to be filled",
    "o.e.m",
    "default string",
    "serial number",
    "asset tag",
    "asset information",
    "not applicable",
    "not available",
    "not specified",
)
# "tbd" SOLO invalida cuando el valor normalizado es exactamente ese:
# como subcadena descartaria seriales reales (ej. 'XTBD4Y7K').
_VALORES_INVALIDOS = frozenset(_VALORES_INVALIDOS | {"tbd"})


def es_valido(valor) -> bool:
    """True si el valor en bruto sirve como identificador de hardware."""
    n = normalizar(valor)
    if not n:
        return False
    if n in _VALORES_INVALIDOS:
        return False
    if any(frase in n for frase in _FRASES_RELLENO):
        return False
    hexa = n.replace("-", "")
    if hexa in _UUID_RELLENO_HEXA:
        return False
    if len(hexa) == 32 and set(hexa) <= set("0123456789abcdef"):
        if set(hexa) == {"0"} or set(hexa) == {"f"}:
            return False
    if _hexa_consecutiva(n):
        return False
    if len(set(n)) == 1:
        return False
    return True


def _mac_valida(valor) -> bool:
    """MAC utilizable como respaldo: 12 hex, no relleno."""
    n = normalizar(valor).replace("-", "").replace(":", "")
    if len(n) != 12 or any(c not in "0123456789abcdef" for c in n):
        return False
    if len(set(n)) == 1:
        return False
    return True


def _leer_ruta(data, ruta):
    """Baja por una ruta fija de claves/índices y devuelve lo que encuentre."""
    nodo: object = data
    for paso in ruta:
        try:
            if isinstance(nodo, dict):
                nodo = nodo.get(paso)
            else:
                nodo = nodo[paso]
        except (KeyError, IndexError, TypeError):
            return ""
    return nodo


def extraer_componentes(data) -> dict:
    """Lee cada componente de su ruta exacta dentro de un ``data`` de
    recolector. Devuelve {nombre_componente: valor_en_bruto_solo_si_hay}."""
    salida = {}
    if not isinstance(data, dict):
        return salida
    for nombre, ruta in _RUTAS.items():
        nodo = _leer_ruta(data, ruta)
        if isinstance(nodo, str) and nodo.strip():
            salida[nombre] = nodo.strip()
    return salida


def componentes_de_results(results) -> dict:
    """Reúne los componentes de identidad del primer ``data`` con hardware."""
    for resultado in results or []:
        if not isinstance(resultado, dict):
            continue
        data = resultado.get("data")
        if not isinstance(data, dict):
            continue
        if ("identidad" not in data and "bios" not in data
                and "baseboards" not in data):
            continue
        comp = extraer_componentes(data)
        if comp:
            return comp
    return {}


def nombre_equipo(results) -> str:
    """Nombre visible (computer_name) del primer resultado con contexto."""
    for resultado in results or []:
        if not isinstance(resultado, dict):
            continue
        ctx = resultado.get("context")
        if isinstance(ctx, dict):
            texto = str(ctx.get("computer_name") or "").strip()
            if texto:
                return texto
    return ""


def nombre_distinto(base, actual) -> bool:
    """True si ambos lados tienen nombre y los nombres difieren (aviso)."""
    nb = str((base or {}).get("computer_name") or "").strip().lower()
    na = str((actual or {}).get("computer_name") or "").strip().lower()
    return bool(nb and na and nb != na)


def fingerprint(componentes) -> str:
    """``dgu-`` + 16 hex de SHA-256 sobre los fuertes válidos, en orden fijo.

    El material se arma con una línea ``nombre:valor`` por componente, en el
    orden canónico de ``FUERTES``. Si no hay ningún fuerte válido, el
    identificador es ``""`` (identidad débil).
    """
    lineas = []
    for nombre in FUERTES:
        valor = normalizar((componentes or {}).get(nombre))
        if es_valido(valor):
            lineas.append(f"{nombre}:{valor}")
    if not lineas:
        return ""
    return "dgu-" + hashlib.sha256("\n".join(lineas).encode("utf-8")).hexdigest()[:16]


def extraer_respaldos(data) -> dict:
    """Lee los respaldos de un ``data`` de recolector (solo lectura).

    Rutas exactas: ``identidad.macs_fisicas`` (lista) y
    ``identidad.disco_arranque`` (serial del disco que contiene la unidad de
    sistema). Se descartan MAC/serial inválidos; nunca deciden solos (ver
    ``comparar``).
    """
    salida = {}
    if not isinstance(data, dict):
        return salida
    macs = _leer_ruta(data, _RESPALDOS_MACS)
    if isinstance(macs, list):
        utiles = [normalizar(m) for m in macs
                  if isinstance(m, str) and _mac_valida(m)]
        if utiles:
            salida["macs_fisicas"] = utiles
    serial = _leer_ruta(data, _RESPALDOS_DISCO)
    if isinstance(serial, str) and serial.strip() and es_valido(serial):
        salida["disco_arranque"] = serial.strip()
    return salida


def respaldos_de_results(results) -> dict:
    """Une los respaldos del primer ``data`` con hardware."""
    for resultado in results or []:
        if not isinstance(resultado, dict):
            continue
        data = resultado.get("data")
        if not isinstance(data, dict):
            continue
        resp = extraer_respaldos(data)
        if resp:
            return resp
    return {}


def calidad(componentes) -> str:
    """\"alta\" con 2+ fuertes validos de valor DISTINTO, \"baja\" con 1, \"nula\" con 0.

    Los campos que comparten el mismo valor cuentan una sola vez: el mismo
    serial repetido en ``bios_serial``, ``system_serial`` y ``chassis_serial``
    es UN dato, no tres.
    """
    valores = {normalizar((componentes or {}).get(nombre))
               for nombre in FUERTES
               if es_valido((componentes or {}).get(nombre))}
    if len(valores) >= 2:
        return "alta"
    if len(valores) == 1:
        return "baja"
    return "nula"


def calidad_de_base(base) -> str:
    """Calidad de un lado a comparar.

    Si hay ``componentes`` se recalcula desde ellos (el valor guardado se
    usa solo cuando no hay componentes). Con formato legacy
    (``hardware_id`` único, sin componentes) la calidad es "baja".
    """
    if isinstance(base, dict):
        comp = base.get("componentes")
        if isinstance(comp, dict):
            return calidad(comp)
        guardada = str(base.get("calidad") or "").strip().lower()
        if guardada in ("alta", "baja", "nula"):
            return guardada
        heredado = str(base.get("hardware_id") or "").strip()
        if heredado:
            return "baja"
        return "nula"
    return "nula"


def advertencia_calidad(cal_base: str, cal_actual: str) -> str:
    """Aviso cuando algún lado se reconoce por un solo dato de hardware."""
    if cal_base == "baja" or cal_actual == "baja":
        return "Este equipo se reconoce por un solo dato de hardware"
    return ""


def de_results(results) -> dict:
    """Resumen de identidad a partir de los ``results`` de un diagnóstico."""
    comp = componentes_de_results(results)
    fuertes_validos = [k for k in FUERTES if es_valido(comp.get(k))]
    fuertes_invalidos = [k for k in FUERTES
                         if str(comp.get(k) or "").strip()
                         and not es_valido(comp.get(k))]
    return {
        "computer_name": nombre_equipo(results),
        "componentes": comp,
        "machine_id": fingerprint(comp),
        "calidad": calidad(comp),
        "fuertes_validos": fuertes_validos,
        "fuertes_invalidos": fuertes_invalidos,
        "debiles": [k for k in DEBILES if str(comp.get(k) or "").strip()],
        "respaldos": respaldos_de_results(results),
    }


def _para_comparar(datos) -> dict:
    """Componentes normalizados listos para comparar.

    Formato viejo (baseline ``{"computer_name", "hardware_id"}``): se cae al
    componente único ``legacy`` para que la comparación siga funcionando.
    """
    if isinstance(datos, dict):
        comp = datos.get("componentes")
        if isinstance(comp, dict) and comp:
            return {k: normalizar(v) for k, v in comp.items()
                    if isinstance(v, str) and v.strip()}
        heredado = str(datos.get("hardware_id") or "").strip()
        if heredado:
            return {LEGACY: normalizar(heredado)}
    return {}


def comparar(base, actual) -> str:
    """Veredicto entre dos lados: igual | probable | distinto | indeterminado.

    - igual: cada fuerte válido compartido coincide (hay al menos uno).
    - probable: un fuerte coincide y otro difiere (ej.: cambio de placa).
    - distinto: hay fuertes válidos en ambos y ninguno coincide.
    - indeterminado: no hay fuertes válidos en común.

    Fallback con legacy (baseline vieja frente a datos nuevos, o
    viceversa): si el valor heredado coincide con un fuerte actual es
    "igual"; si coincide solo con ``machine_guid`` es "probable"; si no
    coincide con nada es "indeterminado" (nunca "distinto"). Dos lados
    legacy entre sí conservan la lógica previa: distinto si difieren.
    Componentes fuertes sin ninguno en común: "indeterminado" (el cruce de
    valores de componentes distintos ya no produce veredicto).

    ``machine_guid`` nunca decide (se clona) y ``computer_name`` solo añade
    contexto vía ``nombre_distinto``: renombrar la PC no invalida nada.

    Los respaldos (MACs, disco de arranque) se leen de
    ``datos["respaldos"]`` y jamás producen "distinto": solo suben un
    "indeterminado" a "probable".
    """
    b = {k: v for k, v in _para_comparar(base).items()
         if k in FUERTES or k in DEBILES or k == LEGACY}
    b = {k: v for k, v in b.items() if es_valido(v)}
    a = {k: v for k, v in _para_comparar(actual).items()
         if k in FUERTES or k in DEBILES or k == LEGACY}
    a = {k: v for k, v in a.items() if es_valido(v)}

    comunes = [k for k in FUERTES if k in b and k in a]
    if not comunes:
        b_hereda = LEGACY in b
        a_hereda = LEGACY in a
        if b_hereda and a_hereda:
            return "igual" if b[LEGACY] == a[LEGACY] else "distinto"
        if b_hereda or a_hereda:
            heredado = b[LEGACY] if b_hereda else a[LEGACY]
            nuevo = a if b_hereda else b
            if heredado in [v for k, v in nuevo.items() if k in FUERTES]:
                return "igual"
            if heredado in [v for k, v in nuevo.items() if k in DEBILES]:
                return "probable"
            return "indeterminado"
        if _respaldos_coinciden(_respaldos_de(base), _respaldos_de(actual)) is True:
            return "probable"
        return "indeterminado"

    iguales = [k for k in comunes if b[k] == a[k]]
    if not iguales:
        return "distinto"
    return "igual" if len(iguales) == len(comunes) else "probable"


def _respaldos_de(datos) -> dict:
    """Extrae ``datos["respaldos"]`` si es dict; si no, vacío."""
    if isinstance(datos, dict) and isinstance(datos.get("respaldos"), dict):
        return datos["respaldos"]
    return {}


def _aplano_respaldos(resp) -> dict:
    """Respaldos a pares planos (nombre, valor). Cada MAC es una clave."""
    plano = {}
    if not isinstance(resp, dict):
        return plano
    disco = resp.get("disco_arranque")
    if isinstance(disco, str) and disco.strip() and es_valido(disco):
        plano["disco_arranque"] = normalizar(disco)
    macs = resp.get("macs_fisicas")
    if isinstance(macs, list):
        for mac in macs:
            if isinstance(mac, str) and _mac_valida(mac):
                canon = normalizar(mac).replace("-", "").replace(":", "")
                plano["mac:" + canon] = canon
    return plano


def _respaldos_coinciden(resp_base, resp_actual):
    """True si los respaldos compartidos coinciden TODOS.

    Devuelve None cuando no alcanza para afirmar nada (sin datos útiles de
    un lado, sin respaldos en común, o cuando algún respaldo compartido
    difiere): en ese caso la comparación no sube a "probable" por
    respaldos. Nunca devuelve False: los respaldos jamás producen
    "distinto".
    """
    b = _aplano_respaldos(resp_base)
    a = _aplano_respaldos(resp_actual)
    if not b or not a:
        return None
    claves = set(b) & set(a)
    if not claves:
        return None
    if any(b[k] != a[k] for k in claves):
        return None
    return True


def id_corto(machine_id) -> str:
    """Forma corta para decir en voz alta: dgu-b3004fb7... -> DGU-B300-4FB7.

    Solo acepta ids con prefijo dgu o dgw y 8 o mas digitos hex; si no, "".
    """
    texto = normalizar(machine_id)
    prefijo, _, resto = texto.partition("-")
    if prefijo not in ("dgu", "dgw") or len(resto) < 8:
        return ""
    if any(c not in "0123456789abcdef" for c in resto):
        return ""
    return (prefijo + "-" + resto[:4] + "-" + resto[4:8]).upper()


def id_debil(respaldos) -> str:
    """ID debil (dgw-) a partir de los respaldos validos (disco y MACs).

    Es independiente del orden de las MAC. Nunca debe mostrarse como fuerte.
    """
    plano = _aplano_respaldos(respaldos)
    if not plano:
        return ""
    material = "\n".join("%s:%s" % (k, plano[k]) for k in sorted(plano))
    return "dgw-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def identificar(componentes, respaldos=None) -> dict:
    """Identidad del equipo con su nivel: fuerte, debil o ninguno.

    El id fuerte es el mismo fingerprint de siempre (compatible con los
    snapshots guardados). machine_guid solo nunca produce un id.
    """
    fuerte = fingerprint(componentes)
    cal = calidad(componentes)
    if fuerte:
        aviso = ""
        if cal == "baja":
            aviso = advertencia_calidad("baja", "baja")
        return {"id": fuerte, "id_corto": id_corto(fuerte), "nivel": "fuerte",
                "calidad": cal, "aviso": aviso}
    debil = id_debil(respaldos)
    if debil:
        return {"id": debil, "id_corto": id_corto(debil), "nivel": "debil",
                "calidad": "nula",
                "aviso": ("Identificaci\u00f3n d\u00e9bil: se reconoce solo por el "
                          "disco de arranque o las MAC; puede cambiar si se "
                          "reemplazan.")}
    return {"id": "", "id_corto": "", "nivel": "ninguno", "calidad": "nula",
            "aviso": ("No se pudo identificar este equipo: el hardware no "
                      "aporta datos \u00fanicos v\u00e1lidos.")}
