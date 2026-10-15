# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas unitarias para el motor de reglas de DiagUSB."""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.models import CollectorResult, DiagnosticResult, Finding
from diagusb.core.rules import diagnose, RuleEngine


def create_mock_result(collector_id: str, data: list | dict, status: str = "ok") -> CollectorResult:
    """Crea un resultado de colector mock para pruebas."""
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


class TestRuleEngine:
    """Pruebas para RuleEngine."""

    def test_rule_engine_creation(self):
        """Verifica que el motor de reglas se inicialice correctamente."""
        engine = RuleEngine()
        assert "la_impresora_no_imprime" in engine._rules
        assert len(engine._rules["la_impresora_no_imprime"]) >= 5

    def test_check_spooler_running_ok(self):
        """Verifica que no se reporten errores cuando el spooler esta corriendo."""
        engine = RuleEngine()

        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Running", "display_name": "Print Spooler"},
            "required_services": [],
            "dependent_services": []
        })

        findings = engine._check_spooler_running([spooler_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0

    def test_check_spooler_stopped(self):
        """Verifica que se detecte cuando el spooler esta detenido."""
        engine = RuleEngine()

        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Stopped", "display_name": "Print Spooler"},
            "required_services": [],
            "dependent_services": []
        })

        findings = engine._check_spooler_running([spooler_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) > 0
        assert "Spooler" in critical_findings[0].message

    def test_check_offline_printer(self):
        """Verifica que se detecten impresoras offline."""
        engine = RuleEngine()

        printer_result = create_mock_result("printers", [
            {
                "device_id": "HP-LaserJet",
                "name": "HP LaserJet Pro",
                "work_offline": True,
                "default": True,
            }
        ])

        findings = engine._check_offline_printers([printer_result])
        error_findings = [f for f in findings if f.severity == "error"]
        assert len(error_findings) > 0

    def test_check_printer_error_state(self):
        """Verifica que se detecten impresoras con estado de error."""
        engine = RuleEngine()

        printer_result = create_mock_result("printers", [
            {
                "device_id": "Canon-G3",
                "name": "Canon imageCLASS",
                "detected_error_state": 1,
                "work_offline": False,
                "default": False,
            }
        ])

        findings = engine._check_printer_error_state([printer_result])
        assert len(findings) > 0

    def test_stuck_jobs_detection(self):
        """Verifica la deteccion de trabajos atascados."""
        engine = RuleEngine()

        # Crear un trabajo antiguo (mas de 5 minutos)
        old_time = datetime.utcnow() - timedelta(hours=1)

        jobs_result = create_mock_result("print_jobs", [
            {
                "name": "Trabajo1",
                "document": "documento.pdf",
                "job_id": 1,
                "status_mask": 0,
                "time_submitted_utc": old_time.isoformat(),
            }
        ])

        findings = engine._check_stuck_jobs([jobs_result])
        warning_findings = [f for f in findings if f.severity == "warning"]
        assert len(warning_findings) > 0

    def test_diagnose_function(self):
        """Verifica la funcion principal diagnose()."""
        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Running"}
        })
        printer_result = create_mock_result("printers", [
            {"device_id": "Test", "name": "Test Printer", "detected_error_state": 0, "work_offline": False, "default": True}
        ])

        result = diagnose("la_impresora_no_imprime", [spooler_result, printer_result])

        assert isinstance(result, DiagnosticResult)
        assert result.symptom == "la_impresora_no_imprime"
        assert isinstance(result.findings, list)
        assert isinstance(result.recommendations, list)

    def test_driver_mismatch(self):
        """Verifica deteccion de drivers faltantes."""
        engine = RuleEngine()

        printers_result = create_mock_result("printers", [
            {"name": "Test Printer", "driver_name": "HP LaserJet 1010"}
        ])
        drivers_result = create_mock_result("printer_drivers", [
            {"name": "Canon Generic Driver"}
        ])

        findings = engine._check_driver_mismatch([printers_result, drivers_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) > 0


def run_tests():
    """Ejecuta todas las pruebas."""
    test_instance = TestRuleEngine()

    tests = [
        ("test_rule_engine_creation", test_instance.test_rule_engine_creation),
        ("test_check_spooler_running_ok", test_instance.test_check_spooler_running_ok),
        ("test_check_spooler_stopped", test_instance.test_check_spooler_stopped),
        ("test_check_offline_printer", test_instance.test_check_offline_printer),
        ("test_check_printer_error_state", test_instance.test_check_printer_error_state),
        ("test_stuck_jobs_detection", test_instance.test_stuck_jobs_detection),
        ("test_diagnose_function", test_instance.test_diagnose_function),
        ("test_driver_mismatch", test_instance.test_driver_mismatch),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas del motor de reglas...")
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
