# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas unitarias para los modelos de datos de DiagUSB."""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.models import (
    CollectorResult,
    ComputerId,
    Snapshot,
    Finding,
    DiagnosticResult,
    CollectorManifest,
    PackageManifest,
)


class TestCollectorResult:
    """Pruebas para CollectorResult."""

    def test_collector_result_creation(self):
        """Verifica que se pueda crear un CollectorResult."""
        result = CollectorResult(
            schema_version=1,
            collector_id="test_collector",
            captured_at_utc=datetime.utcnow().isoformat(),
            query={"status": "ok", "duration_ms": 100, "timeout_seconds": 15},
            context={
                "computer_name": "TEST-PC",
                "user": "test\\user",
                "is_elevated": True,
                "windows": {},
                "regional_settings": {},
                "powershell": {},
            },
            metadata={},
            data=[{"id": 1, "name": "test"}],
            errors=[],
            notes=[],
        )

        assert result.schema_version == 1
        assert result.collector_id == "test_collector"
        assert result.query["status"] == "ok"
        assert len(result.data) == 1

    def test_finding_creation(self):
        """Verifica que se pueda crear un Finding."""
        finding = Finding(
            severity="error",
            collector_id="printers",
            message="La impresora esta offline",
            details={"device_id": "HP-LaserJet"},
        )

        assert finding.severity == "error"
        assert "offline" in finding.message

    def test_computer_id_creation(self):
        """Verifica la creacion de ComputerId."""
        computer_id = ComputerId(
            smbios_uuid="12345678-1234-1234-1234-123456789012",
            bios_serial="SN123456",
            machine_guid="{abcdef00-1234-5678-abcd-ef0123456789}",
            mac_addresses=["00:11:22:33:44:55"],
            weak_candidate="TEST-PC",
        )

        assert computer_id.smbios_uuid == "12345678-1234-1234-1234-123456789012"
        assert "00:11:22:33:44:55" in computer_id.mac_addresses

    def test_snapshot_creation(self):
        """Verifica la creacion de un Snapshot."""
        computer_id = ComputerId(
            smbios_uuid="test-uuid",
            bios_serial=None,
            machine_guid=None,
            mac_addresses=[],
            weak_candidate="TEST-PC",
        )

        observation = CollectorResult(
            schema_version=1,
            collector_id="test",
            captured_at_utc=datetime.utcnow().isoformat(),
            query={"status": "ok", "duration_ms": 50, "timeout_seconds": 15},
            context={},
            metadata={},
            data=[],
            errors=[],
            notes=[],
        )

        snapshot = Snapshot(
            computer_id=computer_id,
            captured_at_utc=datetime.utcnow().isoformat(),
            observations=[observation],
        )

        assert snapshot.computer_id.weak_candidate == "TEST-PC"
        assert len(snapshot.observations) == 1

    def test_package_manifest(self):
        """Verifica la estructura de PackageManifest."""
        manifest = PackageManifest(
            name="impresion",
            version="1.0.0",
            label="Impresion",
            description="Diagnostico de impresion",
            symptoms=["la_impresora_no_imprime"],
            collectors=[
                CollectorManifest(
                    id="printers",
                    label="Impresoras",
                    script="get_printers.ps1",
                )
            ],
        )

        assert manifest.name == "impresion"
        assert "la_impresora_no_imprime" in manifest.symptoms
        assert len(manifest.collectors) == 1


def run_tests():
    """Ejecuta todas las pruebas."""
    test_instance = TestCollectorResult()

    tests = [
        ("test_collector_result_creation", test_instance.test_collector_result_creation),
        ("test_finding_creation", test_instance.test_finding_creation),
        ("test_computer_id_creation", test_instance.test_computer_id_creation),
        ("test_snapshot_creation", test_instance.test_snapshot_creation),
        ("test_package_manifest", test_instance.test_package_manifest),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas de modelos...")
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
