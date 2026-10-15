#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Script de ejecucion de pruebas para DiagUSB."""

import sys
from pathlib import Path

# Agregar src y tests al path
tests_dir = Path(__file__).parent
src_path = tests_dir.parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(tests_dir))

from test_models import run_tests as run_models
from test_rules import run_tests as run_rules
from test_registry import run_tests as run_registry
from test_knowledge import run_tests as run_knowledge
from test_improvements import run_tests as run_improvements


def main():
    """Ejecuta todas las suites de pruebas."""
    print("\n" + "=" * 60)
    print("SUITE DE PRUEBAS - DiagUSB")
    print("=" * 60 + "\n")

    results = []

    print("\n" + "-" * 40)
    print("MODULOS")
    print("-" * 40 + "\n")

    try:
        result1 = run_models()
        results.append(("Modelos", result1))
    except Exception as e:
        print(f"  [ERROR] Fallo en suite de modelos: {e}")
        results.append(("Modelos", False))

    try:
        result2 = run_rules()
        results.append(("Reglas", result2))
    except Exception as e:
        print(f"  [ERROR] Fallo en suite de reglas: {e}")
        results.append(("Reglas", False))

    try:
        result3 = run_registry()
        results.append(("Registro", result3))
    except Exception as e:
        print(f"  [ERROR] Fallo en suite de registro: {e}")
        results.append(("Registro", False))

    try:
        result4 = run_knowledge()
        results.append(("Base de conocimiento", result4))
    except Exception as e:
        print(f"  [ERROR] Fallo en suite de base de conocimiento: {e}")
        results.append(("Base de conocimiento", False))

    try:
        result5 = run_improvements()
        results.append(("Mejoras", result5))
    except Exception as e:
        print(f"  [ERROR] Fallo en suite de mejoras: {e}")
        results.append(("Mejoras", False))

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASO" if passed else "FALLO"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\nTodas las pruebas fueron exitosas.")
        return 0
    else:
        print("\nAlgunas pruebas fallaron. Revise los detalles arriba.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
