# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas unitarias para el registro de paquetes de DiagUSB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.registry import discover_packages, build_package_menu


class TestRegistry:
    """Pruebas para el registro de paquetes."""

    def test_discover_packages(self):
        """Verifica que se descubran los paquetes instalados."""
        packages = discover_packages()
        assert isinstance(packages, list)

        # Debe encontrar al menos el paquete de impresion
        package_names = [pkg.name for pkg in packages]
        print(f"Paquetes encontrados: {package_names}")

    def test_discover_impresion_package(self):
        """Verifica que se descubra el paquete de impresion."""
        packages = discover_packages()
        impresion_pkg = next((p for p in packages if p.name == "impresion"), None)

        assert impresion_pkg is not None, "No se encontro el paquete 'impresion'"
        assert impresion_pkg.version == "1.0.0"
        assert "la_impresora_no_imprime" in impresion_pkg.symptoms

    def test_build_package_menu(self):
        """Verifica la construccion del menu de paquetes."""
        menu = build_package_menu()
        assert isinstance(menu, list)

        if len(menu) > 0:
            first_item = menu[0]
            assert "id" in first_item
            assert "label" in first_item
            assert "description" in first_item
            assert "symptoms" in first_item
            assert "has_symptoms" in first_item

    def test_menu_shows_symptoms(self):
        """Verifica que el menu muestre sintomas."""
        menu = build_package_menu()
        impresion_item = next((m for m in menu if m["id"] == "impresion"), None)

        if impresion_item:
            assert impresion_item["has_symptoms"] is True
            assert len(impresion_item["symptoms"]) > 0


def run_tests():
    """Ejecuta todas las pruebas."""
    test_instance = TestRegistry()

    tests = [
        ("test_discover_packages", test_instance.test_discover_packages),
        ("test_discover_impresion_package", test_instance.test_discover_impresion_package),
        ("test_build_package_menu", test_instance.test_build_package_menu),
        ("test_menu_shows_symptoms", test_instance.test_menu_shows_symptoms),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas del registro de paquetes...")
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
