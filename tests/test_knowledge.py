# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas unitarias para la base de conocimiento local de DiagUSB."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core import knowledge_base as kb
from diagusb.core.models import Finding
from diagusb.core.rules import RuleEngine


class TestKnowledgeBase:
    """Pruebas para la base de conocimiento."""

    def test_kb_cargada(self):
        """La base carga con al menos una entrada y version valida."""
        entradas = kb.entradas()
        assert len(entradas) >= 10, f"solo {len(entradas)} entradas"
        assert kb.version() >= 1

    def test_estructura_entradas(self):
        """Cada entrada tiene los campos minimos: estado esperado y soluciones."""
        for e in kb.entradas():
            assert e.get("id"), "entrada sin id"
            assert e.get("titulo"), f"{e['id']}: sin titulo"
            assert e.get("estado_esperado"), f"{e['id']}: sin estado_esperado"
            assert e.get("soluciones"), f"{e['id']}: sin soluciones"
            assert e.get("verificacion"), f"{e['id']}: sin verificacion"
            assert isinstance(e.get("colectores"), list)

    def test_ids_unicos(self):
        ids = [e["id"] for e in kb.entradas()]
        assert len(ids) == len(set(ids)), "ids duplicados en la base"

    def test_cobertura_de_reglas(self):
        """Todo colector usado por el motor de reglas tiene entrada en la KB."""
        fuente = __import__("inspect").getsource(RuleEngine)
        colectores = set(re.findall(r'_find_collector\(observations, "([^"]+)"', fuente))
        assert colectores, "no se encontraron colectores en rules.py"
        sin_cobertura = [c for c in sorted(colectores) if not kb.por_colector(c)]
        assert not sin_cobertura, f"colectores sin entrada en KB: {sin_cobertura}"

    def test_buscar_y_consultas(self):
        assert kb.buscar("no_existe_este_id") is None
        assert kb.buscar("") is None
        assert kb.por_colector("colector_inexistente") == []
        assert kb.por_sintoma("sintoma_inexistente") == []
        e = kb.buscar("servicio_automatico_detenido")
        assert e is not None
        assert e["estado_esperado"]
        assert "critical_services" in e["colectores"]

    def test_para_finding_por_colector(self):
        f = Finding(severity="error", collector_id="logical_disks",
                    message="Disco casi lleno")
        e = kb.para_finding(f)
        assert e is not None
        assert e["id"] == "disco_sin_espacio"
        assert kb.knowledge_json(f)["estado_esperado"] == e["estado_esperado"]
        assert kb.soluciones_de(f) == e["soluciones"]

    def test_para_finding_por_id_explicito(self):
        f = Finding(severity="error", collector_id="cualquiera",
                    message="x", knowledge_id="firewall_desactivado")
        e = kb.para_finding(f)
        assert e is not None
        assert e["id"] == "firewall_desactivado"

    def test_para_finding_sin_relacion(self):
        f = Finding(severity="warning", collector_id="colector_raro", message="x")
        assert kb.para_finding(f) is None
        assert kb.knowledge_json(f) is None
        assert kb.soluciones_de(f) == []

    def test_attach_knowledge(self):
        f1 = Finding(severity="error", collector_id="antivirus_status", message="x")
        f2 = Finding(severity="error", collector_id="dns_servers",
                     message="y", knowledge_id="dns_invalido")
        kb.attach_knowledge([f1, f2])
        assert f1.knowledge_id == "antivirus_desactivado"
        assert f2.knowledge_id == "dns_invalido", "no debe pisar el id explicito"


def run_tests():
    """Ejecuta todas las pruebas."""
    inst = TestKnowledgeBase()

    tests = [
        ("test_kb_cargada", inst.test_kb_cargada),
        ("test_estructura_entradas", inst.test_estructura_entradas),
        ("test_ids_unicos", inst.test_ids_unicos),
        ("test_cobertura_de_reglas", inst.test_cobertura_de_reglas),
        ("test_buscar_y_consultas", inst.test_buscar_y_consultas),
        ("test_para_finding_por_colector", inst.test_para_finding_por_colector),
        ("test_para_finding_por_id_explicito", inst.test_para_finding_por_id_explicito),
        ("test_para_finding_sin_relacion", inst.test_para_finding_sin_relacion),
        ("test_attach_knowledge", inst.test_attach_knowledge),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas de base de conocimiento...")
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
    success = run_tests()
    sys.exit(0 if success else 1)
