# SPDX-License-Identifier: GPL-3.0-or-later
"""Regla ventilador_0_rpm_con_cpu_caliente con datos simulados (tabla de verdad)."""
import pytest

from diagusb.core.models import CollectorResult, QueryInfo
from diagusb.core.rules import diagnose_symptoms

SINTOMA = "ventilador_0_rpm_con_cpu_caliente"
FRASE = "puede ser un ventilador detenido o un sensor sin conectar"


def _resultado(collector_id, datos):
    return CollectorResult(
        collector_id=collector_id,
        query=QueryInfo(status="ok", duration_ms=5, timeout_seconds=15),
        data=[datos],
    )


def _cpu(temp=85.0, **extra):
    datos = {"available": True, "cpu_name": "CPU simulada", "max_temp_c": temp,
             "package_temp_c": temp, "max_core_temp_c": temp}
    datos.update(extra)
    return _resultado("cpu_temperature", datos)


def _fan(sensores=(), **extra):
    lista = [{"name": n, "rpm": r} for n, r in sensores]
    datos = {"available": True, "source": "simulado", "fan_rpms": [s["rpm"] for s in lista],
             "max_fan_rpm": 0, "sensor_count": len(lista), "sensors": lista}
    datos.update(extra)
    return _resultado("fan_speeds", datos)


def _hallazgos(cpu, fan):
    observaciones = [o for o in (cpu, fan) if o is not None]
    hallazgos, _ = diagnose_symptoms([SINTOMA], observaciones)
    return [f for f in hallazgos if f.knowledge_id == SINTOMA]


def _un_aviso(hallazgos):
    assert len(hallazgos) == 1, hallazgos
    f = hallazgos[0]
    assert f.severity == "warning"
    assert f.severity not in ("error", "critical")
    assert FRASE in f.message
    return f


CASOS_AVISO = [
    ("lista_vacia", []),
    ("todos_en_cero", [("Fan #1", 0), ("Fan #2", 0)]),
    ("cabeceras_vacias_en_cero", [("CPU Fan", 0), ("Chassis Fan #1", 0), ("Chassis Fan #2", 0)]),
    ("sensor_cpu_en_cero_otro_gira", [("CPU Fan", 0), ("Chassis Fan", 1200)]),
    ("sensor_processor_en_cero_otro_gira", [("Processor Fan", 0), ("Fan #2", 900)]),
    ("sensor_cpu_minusculas_en_cero", [("cpu fan", 0), ("Fan #2", 900)]),
    ("rpm_vacio", [("Fan #1", "")]),
    ("rpm_none", [("Fan #1", None)]),
    ("rpm_ilegible", [("Fan #1", "n/d")]),
    ("ilegible_y_cero", [("Fan #1", "n/d"), ("Fan #2", 0)]),
]

CASOS_NADA = [
    ("uno_gira", [("Fan #1", 900)]),
    ("cpu_gira_otro_en_cero", [("CPU Fan", 1500), ("Chassis Fan", 0)]),
    ("todos_giran", [("CPU Fan", 1500), ("Chassis Fan", 800)]),
]


@pytest.mark.parametrize("nombre,sensores", CASOS_AVISO, ids=[c[0] for c in CASOS_AVISO])
def test_cpu_caliente_y_ventilador_detenido_avisa(nombre, sensores):
    f = _un_aviso(_hallazgos(_cpu(85.0), _fan(sensores)))
    assert f.details["temperature_c"] == 85.0


@pytest.mark.parametrize("nombre,sensores", CASOS_NADA, ids=[c[0] for c in CASOS_NADA])
def test_cpu_caliente_con_ventilador_sano_no_avisa(nombre, sensores):
    assert _hallazgos(_cpu(85.0), _fan(sensores)) == []


def test_cpu_ausente_no_genera_nada():
    assert _hallazgos(None, _fan([])) == []


def test_cpu_sin_lectura_no_genera_nada():
    assert _hallazgos(_cpu(None), _fan([])) == []


def test_cpu_no_disponible_no_genera_nada():
    assert _hallazgos(_cpu(85.0, available=False), _fan([])) == []


def test_ventiladores_ausentes_no_genera_nada():
    assert _hallazgos(_cpu(85.0), None) == []


def test_ventiladores_no_disponibles_no_genera_nada():
    assert _hallazgos(_cpu(85.0), _fan([], available=False)) == []


@pytest.mark.parametrize("temp", [69.9, 40.0])
@pytest.mark.parametrize("sensores", [[], [("Fan #1", 0)], [("CPU Fan", 0)]])
def test_cpu_fria_no_genera_nada(temp, sensores):
    assert _hallazgos(_cpu(temp), _fan(sensores)) == []


def test_umbral_es_inclusivo_en_70():
    _un_aviso(_hallazgos(_cpu(70.0), _fan([])))
    assert _hallazgos(_cpu(69.9), _fan([])) == []


def test_sin_sensores_usa_fan_rpms():
    _un_aviso(_hallazgos(_cpu(85.0), _fan([], fan_rpms=[0])))
    assert _hallazgos(_cpu(85.0), _fan([], fan_rpms=[1500])) == []
