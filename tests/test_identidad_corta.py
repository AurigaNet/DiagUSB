# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""ID corto legible, ID debil por respaldos e identificar() (core.identidad).

Todos los valores son inventados: ningun serial ni UUID real va al repo.
"""
from diagusb.core import identidad as ident

DOS = {"smbios_uuid": "UUID-PRUEBA-A1", "bios_serial": "BIO-PRUEBA-77"}
UNO = {"smbios_uuid": "UUID-PRUEBA-A1"}
DISCO = "DISCO-PRUEBA-55"
MAC1 = "aa:bb:cc:dd:ee:01"
MAC2 = "aa:bb:cc:dd:ee:02"
MAC3 = "aa:bb:cc:dd:ee:03"


def test_id_corto_agrupa_en_cuatro_y_cuatro():
    assert ident.id_corto("dgu-b3004fb73e084c42") == "DGU-B300-4FB7"


def test_id_corto_debil():
    assert ident.id_corto("dgw-0123456789abcdef") == "DGW-0123-4567"


def test_id_corto_rechaza_basura():
    for malo in ("", None, "basura", "dgu-", "dgu-123", "xyz-0123456789ab",
                 "dgu-zzzzzzzzzzzz"):
        assert ident.id_corto(malo) == "", malo


def test_id_debil_estable_y_con_prefijo_dgw():
    r = {"disco_arranque": DISCO}
    a = ident.id_debil(r)
    assert a.startswith("dgw-") and len(a) == len("dgw-") + 16
    assert a == ident.id_debil(r)


def test_id_debil_no_depende_del_orden_de_macs():
    a = {"macs_fisicas": [MAC1, MAC2]}
    b = {"macs_fisicas": [MAC2, MAC1]}
    c = {"macs_fisicas": [MAC1, MAC3]}
    assert ident.id_debil(a) == ident.id_debil(b) != ""
    assert ident.id_debil(a) != ident.id_debil(c)


def test_id_debil_sin_respaldos_es_vacio():
    assert ident.id_debil(None) == ""
    assert ident.id_debil({}) == ""
    assert ident.id_debil({"disco_arranque": "To Be Filled By O.E.M."}) == ""


def test_identificar_fuerte_alta():
    r = ident.identificar(DOS)
    assert r["nivel"] == "fuerte" and r["calidad"] == "alta"
    assert r["aviso"] == ""
    assert r["id"].startswith("dgu-")
    assert r["id_corto"].startswith("DGU-") and len(r["id_corto"]) == 13


def test_identificar_fuerte_baja_avisa():
    r = ident.identificar(UNO)
    assert r["nivel"] == "fuerte" and r["calidad"] == "baja"
    assert "un solo dato" in r["aviso"]


def test_identificar_debil_por_respaldos():
    r = ident.identificar({}, {"disco_arranque": DISCO})
    assert r["nivel"] == "debil"
    assert r["id"].startswith("dgw-") and r["id_corto"].startswith("DGW-")
    assert "d\u00e9bil" in r["aviso"]


def test_identificar_ninguno():
    r = ident.identificar({}, None)
    assert r["nivel"] == "ninguno" and r["id"] == "" and r["id_corto"] == ""
    assert r["aviso"] != ""


def test_machine_guid_solo_no_identifica():
    r = ident.identificar({"machine_guid": "GUID-PRUEBA-XYZ"}, {})
    assert r["nivel"] == "ninguno" and r["id"] == ""


def test_identificar_compatible_con_fingerprint():
    assert ident.identificar(DOS)["id"] == ident.fingerprint(DOS)
    assert ident.identificar(UNO)["id"] == ident.fingerprint(UNO)