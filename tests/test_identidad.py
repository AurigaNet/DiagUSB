# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Tests de core.identidad: normalización, fingerprint, calidad y comparación."""

import json

from diagusb.core import identidad


def componentes(uuid="", bios="", baseboard="", guid=""):
    out = {}
    if uuid:
        out["smbios_uuid"] = uuid
    if bios:
        out["bios_serial"] = bios
    if baseboard:
        out["baseboard_serial"] = baseboard
    if guid:
        out["machine_guid"] = guid
    return out


BASURA = (
    "",
    "   ",
    "To Be Filled By O.E.M.",
    "Default string",
    "System Serial Number",
    "Serial Number",
    "None",
    "N/A",
    "Not Specified",
    "Unknown",
    "O.E.M.",
    "0",
    "123456789",
    "00000000-0000-0000-0000-000000000000",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "aaaaaaaa",
    "x",
)


def test_basura_no_sirve_como_identificador():
    for valor in BASURA:
        assert not identidad.es_valido(valor), valor


def test_frases_de_relleno_en_cualquier_posicion():
    for valor in ("To Be Filled By O.E.M", "No Asset Tag",
                  "Base Board Serial Number", "Chassis Serial Number",
                  "Default String", "ASSET INFORMATION-99",
                  "Serial No es esto: Not Available",
                  "Chassis: Not Specified"):
        assert not identidad.es_valido(valor), valor
    # un serial real con letras y numeros sigue siendo valido
    assert identidad.es_valido("ABC123XYZ9")
    # 'tbd' solo invalida el valor completo; como subcadena no
    assert not identidad.es_valido("TBD")
    assert not identidad.es_valido("tbd")
    assert identidad.es_valido("XTBD4Y7K")


def test_calidad_cuenta_valores_distintos():
    # el mismo serial repetido en tres campos es UN solo dato: baja
    comp_repetido = {
        "bios_serial": "SER-IGUALES",
        "system_serial": "ser-iguales",
        "chassis_serial": " SER-IGUALES ",
    }
    assert identidad.calidad(comp_repetido) == "baja"
    # uuid + el serial repetido en tres campos: dos datos distintos = alta
    comp_uuid_y_repetido = dict(comp_repetido, smbios_uuid="UUID-REAL-01")
    assert identidad.calidad(comp_uuid_y_repetido) == "alta"
    # sin fuertes validos: nula
    assert identidad.calidad({"bios_serial": "To Be Filled By O.E.M"}) == "nula"


def test_basura_descarta_componentes():
    comp = componentes(uuid="To Be Filled By O.E.M.",
                       bios="System Serial Number",
                       baseboard="00000000-0000-0000-0000-000000000000",
                       guid="ffffffff-ffff-ffff-ffff-ffffffffffff")
    assert identidad.fingerprint(comp) == ""
    ident = identidad.de_results([])  # sin datos no explota
    assert ident["machine_id"] == ""


def test_determinismo_independiente_del_orden():
    dav = identidad.fingerprint(componentes(
        uuid="UUID-UNO", bios="BIO-1", baseboard="PLA-1"))
    dict_otro = {"baseboard_serial": "PLA-1", "bios_serial": "BIO-1",
                 "smbios_uuid": "UUID-UNO"}
    igual = identidad.fingerprint(dict_otro)
    assert igual == dav
    assert igual.startswith("dgu-")
    assert len(igual) == len("dgu-" + "0" * 16)
    # Cambiar un componente cambia el id
    assert identidad.fingerprint(componentes(
        uuid="UUID-UNO", bios="BIO-2", baseboard="PLA-1")) != dav


def test_fingerprint_ignora_fuertes_invalidos():
    dias = identidad.fingerprint(componentes(
        uuid="Default string", bios="BIO-REAL", baseboard="0"))
    assert dias == identidad.fingerprint(componentes(bios="BIO-REAL"))


def test_caso_clonado_es_distinto():
    maestro = {"computer_name": "ORIGEN",
               "componentes": componentes(
                   uuid="UUID-MAESTRO", bios="BS-1",
                   baseboard="BB-1", guid="GUID-CLONADO")}
    clon = {"computer_name": "CLON",
            "componentes": componentes(
                uuid="UUID-CLON", bios="BS-9",
                baseboard="BB-9", guid="GUID-CLONADO")}
    assert identidad.comparar(maestro, clon) == "distinto"


def test_renombre_de_pc_sigue_siendo_igual():
    antes = {"computer_name": "PC-VIEJA",
             "componentes": componentes(
                 uuid="UUID-X", bios="BIO-X", baseboard="BB-X")}
    despues = {"computer_name": "PC-NUEVA",
               "componentes": componentes(
                   uuid="UUID-X", bios="BIO-X", baseboard="BB-X")}
    assert identidad.comparar(antes, despues) == "igual"


def test_cambio_de_placa_es_probable():
    antes = {"componentes": componentes(
        uuid="UUID-Q", bios="BIO-Q", baseboard="BB-VIEJA",
        guid="GUID-Z")}
    despues = {"componentes": componentes(
        uuid="UUID-Q", bios="BIO-Q", baseboard="BB-NUEVA",
        guid="GUID-Z")}
    assert identidad.comparar(antes, despues) == "probable"


def test_sin_datos_es_indeterminado():
    assert identidad.comparar({}, {}) == "indeterminado"
    assert identidad.comparar({"computer_name": "A"}, {"computer_name": "B"}) \
        == "indeterminado"
    assert identidad.nombre_distinto({"computer_name": "A"},
                                     {"computer_name": "B"}) is True


def test_machine_guid_nunca_decide_solo():
    solo_guid_base = {"componentes": {"machine_guid": "GUID-UNO"}}
    solo_guid_act = {"componentes": {"machine_guid": "GUID-UNO"}}
    # Hay un componente comun "debil": sin fuertes validos no puede decidir
    assert identidad.comparar(solo_guid_base, solo_guid_act) == "indeterminado"
    distintos = {"componentes": {"machine_guid": "G1", "smbios_uuid": "U1"}}, \
               {"componentes": {"machine_guid": "G1", "smbios_uuid": "U2"}}
    assert identidad.comparar(*distintos) == "distinto"


def test_baseline_viejo_hereda_comparacion():
    viejo = {"computer_name": "PC-LEGA", "hardware_id": "SER-ABC"}
    igual_mayus_minus = identidad.comparar(
        viejo, {"computer_name": "PC-LEGA", "hardware_id": "ser-abc"})
    distinto = identidad.comparar(
        viejo, {"computer_name": "PC-OTRA", "hardware_id": "SER-XYZ"})
    assert igual_mayus_minus == "igual"
    assert distinto == "distinto"
    # Sin hardware_id en el baseline viejo: indeterminado
    vacio = identidad.comparar(
        {"computer_name": "PC-LEGA"}, {"computer_name": "PC-NUEVA",
                                       "hardware_id": "SER-7"})
    assert vacio == "indeterminado"


def test_de_results_lee_rutas_exactas():
    results = [
        {"collector_id": "hardware",
         "data": {
             "identidad": {"smbios_uuid": " UUID-COMPI ",
                           "machine_guid": "GUID-COMPI"},
             "computer_system": [{"manufacturer": "X"}],
             "bios": [{"serial_number": "BIO-COMPI"}],
             "baseboards": [{"serial_number": "BB-COMPI"}],
         }},
    ]
    comp = identidad.componentes_de_results(results)
    assert comp == {"smbios_uuid": "UUID-COMPI", "machine_guid": "GUID-COMPI",
                    "bios_serial": "BIO-COMPI",
                    "baseboard_serial": "BB-COMPI"}
    resumen = identidad.de_results(results)
    assert resumen["computer_name"] == ""
    assert resumen["machine_id"].startswith("dgu-")
    assert resumen["calidad"] == "alta"
    assert resumen["fuertes_validos"] == ["smbios_uuid", "bios_serial",
                                          "baseboard_serial"]
    assert resumen["debiles"] == ["machine_guid"]


# ---------- refuerzo: rellenos, calidad, respaldos ----------

RELLENOS_NUEVOS = (
    "03000200-0300-0400-0005-000600070008",
    "03000200-0300-0400-0005-000600070008".upper(),
    "00020003-0004-0005-0006-000700080009",
    "12345678",
    "87654321",
    "fedcba98",
    "0123456789abcdef",
)


def test_rellenos_uuid_y_secuencias_consecutivas():
    for valor in RELLENOS_NUEVOS:
        assert not identidad.es_valido(valor), valor
    # tandas cortas (<8) o no consecutivas siguen siendo validas
    assert identidad.es_valido("01020304")
    assert identidad.es_valido("BIO-7ABC9D")


def test_secuencia_no_aplica_a_texto_no_hex():
    # "ABC123" tiene hex dispersos pero sin racha de 8: valido
    assert identidad.es_valido("SN-1A2B3C4D")


def test_calidad_alta_baja_nula():
    dos = componentes(uuid="U-UNO", bios="BIO-UNO")
    assert identidad.calidad(dos) == "alta"
    uno = componentes(bios="BIO-UNO")
    assert identidad.calidad(uno) == "baja"
    assert identidad.calidad({}) == "nula"
    # basura no cuenta
    assert identidad.calidad(componentes(
        uuid="To Be Filled By O.E.M.", bios="System Serial Number")) == "nula"


def test_calidad_unica_fuerte_valido():
    res = identidad.de_results([
        {"data": {"bios": [{"serial_number": "BIO-UNICO"}]}}])
    assert res["calidad"] == "baja"
    assert res["fuertes_validos"] == ["bios_serial"]
    # baseline viejo con ese mismo serial: igual (cruz legacy/fuerte)
    assert identidad.comparar({"hardware_id": "BIO-UNICO"},
                              {"componentes": res["componentes"]}) == "igual"


def test_calidad_de_base_legacy_es_baja():
    assert identidad.calidad_de_base(
        {"computer_name": "PC", "hardware_id": "S1"}) == "baja"
    assert identidad.calidad_de_base({"calidad": "alta"}) == "alta"
    assert identidad.calidad_de_base({}) == "nula"


def test_advertencia_calidad_baja():
    assert (identidad.advertencia_calidad("baja", "alta")
            == "Este equipo se reconoce por un solo dato de hardware")
    assert identidad.advertencia_calidad("alta", "baja") != ""
    assert identidad.advertencia_calidad("alta", "alta") == ""
    assert identidad.advertencia_calidad("", "") == ""


def test_extraer_respaldos_rutas_exactas():
    data = {
        "identidad": {
            "macs_fisicas": ["AA-BB-CC-DD-EE-F1", "00-00-00-00-00-00",
                             "ZZZZ", "AA:BB:CC:DD:EE:F2"],
            "disco_arranque": " DISCO-SERIAL-1 ",
        },
    }
    resp = identidad.extraer_respaldos(data)
    # la MAC invalida (todo ceros) se descarta
    assert resp["macs_fisicas"] == ["aa-bb-cc-dd-ee-f1", "aa:bb:cc:dd:ee:f2"]
    assert resp["disco_arranque"] == "DISCO-SERIAL-1"
    assert identidad.extraer_respaldos({}) == {}


def test_respaldos_suben_indeterminado_a_probable():
    base = {"respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    act = {"respaldos": {"macs_fisicas": ["aa:bb:cc:dd:ee:f1"]}}
    sin_resp = identidad.comparar({"hardware_id": ""}, {"hardware_id": ""})
    assert sin_resp == "indeterminado"
    assert identidad.comparar(base, act) == "probable"
    # por serial de disco de arranque tambien
    base_d = {"respaldos": {"disco_arranque": "DISK-1"}}
    act_d = {"respaldos": {"disco_arranque": "disk-1"}}
    assert identidad.comparar(base_d, act_d) == "probable"


def test_respaldos_nunca_producen_distinto():
    base = {"respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    act = {"respaldos": {"macs_fisicas": ["11:22:33:44:55:66"]}}
    assert identidad.comparar(base, act) == "indeterminado"
    # contradiccion parcial: hay comun que difiere y otro que iguala ->
    # NO falso distinto: solo los que coinciden sustentan probable
    base_m = {"respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    act_m = {"respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1",
                                            "11:22:33:44:55:66"]}}
    assert identidad.comparar(base_m, act_m) == "probable"


def test_respaldos_no_cambian_veredictos_firmes():
    fuerte = componentes(uuid="U-Z", bios="BIO-Z")
    base = {"componentes": fuerte, "respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    act = {"componentes": fuerte, "respaldos": {}}
    assert identidad.comparar(base, act) == "igual"
    dist_base = {"componentes": componentes(uuid="U-A", bios="BIO-A"),
                 "respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    dist_act = {"componentes": componentes(uuid="U-B", bios="BIO-B"),
                "respaldos": {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    assert identidad.comparar(dist_base, dist_act) == "distinto"


def test_respaldos_con_disco_distinto_y_mac_igual_es_indeterminado():
    # Un respaldo compartido que difiere bloquea el ascenso a "probable".
    base = {"respaldos": {"disco_arranque": "DISK-VIEJO",
                          "macs_fisicas": ["AA-BB-CC-DD-EE-F1"]}}
    act = {"respaldos": {"disco_arranque": "DISK-NUEVO",
                         "macs_fisicas": ["aa:bb:cc:dd:ee:f1"]}}
    assert identidad.comparar(base, act) == "indeterminado"


def test_calidad_de_base_recalcula_si_hay_componentes():
    # El valor guardado se ignora cuando hay componentes disponibles.
    guardado = {"calidad": "alta",
                "componentes": {"bios_serial": "BIO-UNICO"}}
    assert identidad.calidad_de_base(guardado) == "baja"
    guardado_coherente = {"calidad": "baja",
                          "componentes": {"bios_serial": "BIO-UNICO"}}
    assert identidad.calidad_de_base(guardado_coherente) == "baja"
    # Sin componentes: se usa el guardado
    assert identidad.calidad_de_base({"calidad": "alta"}) == "alta"
    assert identidad.calidad_de_base({"calidad": "nula"}) == "nula"


def test_secuencia_corta_antes_de_caracteres_no_hex():
    letras_intercaladas = "a1b2c3d4e5f6"
    assert identidad.es_valido(letras_intercaladas)
    # letras NO hex al principio no salvan una racha de 8 más adelante
    assert not identidad.es_valido("xx12345678")
    # las rachas ya existentes siguen descartándose
    assert not identidad.es_valido("12345678")
    assert not identidad.es_valido("fedcba98")
    # espacios y otros símbolos también cortan la racha
    assert identidad.es_valido("1234 5678")


def test_snapshots_guardan_calidad_y_respaldos():
    """
    El formato nuevo agrega los campos calidad/respaldos y los snapshots
    viejos no los tienen: deben poder cargarse sin error.
    """
    from diagusb.core.models import ComputerId, CollectorResult, Snapshot
    from diagusb.core.comparator import load_snapshot, save_snapshot
    import tempfile
    from pathlib import Path

    cliente = Path(tempfile.mkdtemp(prefix="diagusb_ident_"))
    archivo = cliente / "snap.json"

    snapshot = Snapshot(
        computer_id=ComputerId(
            smbios_uuid="U-Q", bios_serial="BIO-Q",
            machine_id="dgu-0000000000000000", calidad="baja",
            respaldos={"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]},
            componentes={"smbios_uuid": "U-Q", "bios_serial": "BIO-Q"}),
        captured_at_utc="2026-01-01T00:00:00",
        observations=[CollectorResult(collector_id="x")],
    )
    save_snapshot(snapshot, archivo)
    document = json.loads(archivo.read_text(encoding="utf-8"))
    assert document["computer_id"]["calidad"] == "baja"
    assert (document["computer_id"]["respaldos"]
            == {"macs_fisicas": ["AA-BB-CC-DD-EE-F1"]})
    # formato viejo (sin calidad ni respaldos)
    doc_viejo = {"computer_id": {"smbios_uuid": "U-V", "bios_serial": "BIO-V"},
                 "captured_at_utc": "2020-01-01T00:00:00", "observations": []}
    archivo_viejo = cliente / "viejo.json"
    archivo_viejo.write_text(json.dumps(doc_viejo), encoding="utf-8")
    cargado = load_snapshot(archivo_viejo).computer_id
    assert cargado.smbios_uuid == "U-V" and cargado.componentes
    assert cargado.calidad == "alta"
    # Snapshot nuevo también carga
    cargado_nuevo = load_snapshot(archivo).computer_id
    assert cargado_nuevo.calidad == "baja"
    assert cargado_nuevo.respaldos["macs_fisicas"]


# ---------- bench: fallback legacy, disyunción y adaptadores USB ----------

def test_fuertes_disjuntos_es_indeterminado():
    # Ningún componente fuerte en común: el cruce de valores distintos
    # de componentes INICIALES ya no produce veredicto.
    lado_a = {"componentes": {"smbios_uuid": "UUID-AAA"}}
    lado_b = {"componentes": {"bios_serial": "BIO-BBB",
                              "baseboard_serial": "PLA-BBB"}}
    assert identidad.comparar(lado_a, lado_b) == "indeterminado"


def test_legacy_que_no_coincide_con_nada_es_indeterminado():
    baseline = {"computer_name": "PC-LEGA", "hardware_id": "SER-VIEJO"}
    nuevos = {"componentes": {"smbios_uuid": "UUID-NUEVO",
                              "machine_guid": "GUID-NUEVO"}}
    # aunque el lado nuevo tiene fuertes distintos: nunca "distinto"
    assert identidad.comparar(baseline, nuevos) == "indeterminado"


def test_legacy_coincide_con_fuerte_es_igual():
    baseline = {"computer_name": "PC-LEGA", "hardware_id": "BIO-7K"}
    nuevos = {"componentes": {"bios_serial": "BIO-7K",
                              "machine_guid": "GUID-OTRO"}}
    assert identidad.comparar(baseline, nuevos) == "igual"


def test_legacy_coincide_solo_machine_guid_es_probable():
    baseline = {"computer_name": "PC-LEGA", "hardware_id": "GUID-IMG"}
    nuevos = {"componentes": {"smbios_uuid": "UUID-NUEVO",
                              "machine_guid": "GUID-IMG"}}
    assert identidad.comparar(baseline, nuevos) == "probable"


def test_legacy_vs_legacy_mantiene_distinto():
    base = {"computer_name": "PC-A", "hardware_id": "S1"}
    otro = {"computer_name": "PC-B", "hardware_id": "S2"}
    assert identidad.comparar(base, otro) == "distinto"


def test_el_recolector_excluye_adaptadores_usb():
    """El filtro de MACs del colector descarta los adaptadores USB."""
    from pathlib import Path
    ruta = (Path(identidad.__file__).resolve().parents[1]
            / "packages" / "inventario_general" / "collectors"
            / "get_hardware.ps1")
    texto = ruta.read_text(encoding="utf-8")
    assert "-like 'usb\\*'" in texto
    # la exclusión debe aplicarse antes de leer la MAC
    rechazo = texto.index("$n.PNPDeviceID -like 'usb\\*'")
    asignacion = texto.index("$mac = [string]$n.MACAddress")
    assert rechazo < asignacion


# ---------- componentes fuertes de chasis y system ----------

def test_componentes_de_chasis_se_extraen():
    data = {
        "identidad": {
            "smbios_uuid": "UUID-CH",
            "system_serial": "SYS-001",
            "chassis_serial": "CHA-001",
            "chassis_asset_tag": "ETIQUETA-1",
            "machine_guid": "GUID-CH",
        },
        "bios": [{"serial_number": "BIO-CH"}],
        "baseboards": [{"serial_number": "PLA-CH"}],
    }
    comp = identidad.extraer_componentes(data)
    assert comp["system_serial"] == "SYS-001"
    assert comp["chassis_serial"] == "CHA-001"
    assert comp["chassis_asset_tag"] == "ETIQUETA-1"


def test_chasis_valido_sub_calidad_y_compara():
    # dos fuertes nuevos validos: calidad alta
    comp = {"system_serial": "SYS-ALTA", "chassis_serial": "CHA-ALTA"}
    assert identidad.calidad(comp) == "alta"
    assert identidad.fingerprint(comp).startswith("dgu-")

    # cambio de chasis con el uuid igual: probable
    antes = {"componentes": {"smbios_uuid": "UUID-CC", "chassis_serial": "CHA-1"}}
    despues = {"componentes": {"smbios_uuid": "UUID-CC", "chassis_serial": "CHA-2"}}
    assert identidad.comparar(antes, despues) == "probable"

    # solo un fuerte compartido del chasis y distinto: distinto
    base = {"componentes": {"chassis_asset_tag": "ETQ-1"}}
    actual = {"componentes": {"chassis_asset_tag": "ETQ-2"}}
    assert identidad.comparar(base, actual) == "distinto"


def test_relleno_de_fabrica_en_chasis_no_sub_calidad():
    # los rellenos OEM no cuentan como fuertes validos
    comp = {
        "smbios_uuid": "UUID-RELL",
        "system_serial": "To Be Filled By O.E.M.",
        "chassis_serial": "System Serial Number",
        "chassis_asset_tag": "None",
    }
    assert identidad.calidad(comp) == "baja"
    assert identidad.fingerprint(comp) == identidad.fingerprint(
        {"smbios_uuid": "UUID-RELL"})


def test_baseline_vieja_carga_con_componentes_nuevos():
    """Una baseline del formato previo (sin los fuertes nuevos) compara igual."""
    from diagusb.core.comparator import load_snapshot
    from diagusb.core.models import ComputerId, CollectorResult, Snapshot
    import tempfile
    from pathlib import Path

    cliente = Path(tempfile.mkdtemp(prefix="diagusb_id_ch_"))
    viejo = cliente / "viejo.json"
    viejo.write_text(json.dumps({
        "computer_id": {"smbios_uuid": "U-V", "bios_serial": "BIO-V"},
        "captured_at_utc": "2021-01-01T00:00:00",
        "observations": [],
    }), encoding="utf-8")
    base = load_snapshot(viejo).computer_id
    assert base.componentes == {"smbios_uuid": "U-V", "bios_serial": "BIO-V"}

    actual = {
        "componentes": {
            "smbios_uuid": "U-V", "bios_serial": "BIO-V",
            "system_serial": "SYS-NUEVO", "chassis_serial": "CHA-NUEVO",
            "chassis_asset_tag": "ETQ-NUEVO",
        },
    }
    assert identidad.comparar(base.__dict__, actual) == "igual"
