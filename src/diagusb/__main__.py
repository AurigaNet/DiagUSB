# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Punto de entrada principal de DiagUSB."""

import sys

sys.dont_write_bytecode = True

import argparse
import os
import subprocess
from pathlib import Path
from datetime import datetime

from ._version import __version__
from .core.executor import CollectorExecutor
from .core.registry import build_package_menu, discover_packages
from .core.reporter import ConsoleReporter, HtmlReporter
from .core.rules import diagnose
from .core.models import CollectorResult, QueryInfo
from .core.logger import get_logger
from .core import rutas


BANNER = f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ██████╗  █████╗  ██████╗      ██████╗ ███████╗████████╗ ║
║   ██╔══██╗██╔══██╗██╔════╝     ██╔═══██╗██╔════╝╚══██╔══╝ ║
║   ██████╔╝███████║██║  ███╗    ██║   ██║█████╗     ██║    ║
║   ██╔══██╗██╔══██║██║   ██║    ██║   ██║██╔══╝     ██║    ║
║   ██║  ██║██║  ██║╚██████╔╝    ╚██████╔╝██║        ██║    ║
║   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝      ╚═════╝ ╚═╝        ╚═╝    ║
║                                                           ║
║   Herramienta de Diagnostico USB                          ║
║   Version {__version__}                                          ║
║                                                           ║
║   Copyright (C) 2026 Daniel Ricardo Novoa     ║
║   Licencia: GPL-3.0-or-later                              ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""


def show_banner():
    """Muestra el banner de DiagUSB."""
    print(BANNER, flush=True)


def open_in_browser(file_path: Path) -> bool:
    """
    Abre un archivo en el navegador o programa por defecto.
    Funciona en Windows, Linux y Mac.
    
    Returns:
        True si se pudo abrir, False si no.
    """
    path_str = str(file_path.resolve())
    
    try:
        if sys.platform == "win32":
            os.startfile(path_str)
        elif sys.platform == "darwin":
            subprocess.run(["open", path_str], check=True)
        else:
            # Linux - intentar diferentes comandos
            for cmd in ["xdg-open", "gio open", "firefox", "chromium-browser"]:
                result = subprocess.run([cmd, path_str], capture_output=True)
                if result.returncode == 0:
                    break
            else:
                return False
        return True
    except Exception:
        return False


def show_progress(current: int, total: int, prefix: str = "Progreso"):
    """Muestra una barra de progreso ASCII."""
    if total == 0:
        return
    percentage = int((current / total) * 100)
    filled = int(percentage / 5)
    bar = "=" * filled + " " * (20 - filled)
    print(f"\r{prefix}: [{bar}] {percentage}% ({current}/{total})", end="", flush=True)
    if current == total:
        print()


def interactive_menu(yes_flag: bool = False, open_browser: bool = False, logger=None):
    """Muestra el menu interactivo y maneja la seleccion del usuario."""
    packages = build_package_menu()

    if not packages:
        print("No se encontraron paquetes de diagnostico.")
        print("Asegurese de que los paquetes esten instalados en el directorio 'packages'.")
        return

    while True:
        print("\n" + "=" * 60)
        print("MENU PRINCIPAL")
        print("=" * 60)
        print("\nPaquetes disponibles:\n")

        for i, pkg in enumerate(packages, 1):
            symptoms_str = f" [{len(pkg['symptoms'])} sintomas]" if pkg["has_symptoms"] else ""
            print(f"  {i}. {pkg['label']}{symptoms_str}")
            if pkg["description"]:
                print(f"     {pkg['description']}")
            if pkg["has_symptoms"]:
                print(f"     Sintomas: {', '.join(pkg['symptoms'])}")
            print()

        print("  0. Salir")
        print()

        try:
            if yes_flag:
                idx = 0
                print(f"Seleccion automatica: {packages[0]['label']}")
            else:
                choice = input("Seleccione una opcion: ").strip()
                if choice == "0":
                    print("Saliendo...")
                    break

                idx = int(choice) - 1
                if idx < 0 or idx >= len(packages):
                    print("Opcion invalida.")
                    continue

            selected_pkg = packages[idx]
            run_package_diagnosis(selected_pkg, open_browser=open_browser, yes_flag=yes_flag, logger=logger)

        except ValueError:
            print("Por favor ingrese un numero valido.")
        except KeyboardInterrupt:
            print("\nSaliendo...")
            break


def run_package_diagnosis(pkg: dict, open_browser: bool = False, yes_flag: bool = False, logger=None):
    """Ejecuta el diagnostico para un paquete seleccionado."""
    print(f"\nIniciando diagnostico para: {pkg['label']}")

    if not pkg["has_symptoms"]:
        print("Este paquete no tiene sintomas configurados.")
        return

    print("\nSintomas disponibles:")
    for i, symptom in enumerate(pkg["symptoms"], 1):
        print(f"  {i}. {symptom}")

    try:
        if yes_flag:
            symptom = pkg["symptoms"][0]
            print(f"\nSintoma seleccionado: {symptom}")
        else:
            choice = input("\nSeleccione un sintoma (o Enter para todos): ").strip()
            symptom = pkg["symptoms"][int(choice) - 1] if choice else pkg["symptoms"][0]
    except (ValueError, IndexError):
        print("Sintoma invalido, se ejecutaran todos.")
        symptom = pkg["symptoms"][0]

    # Ejecutar diagnostico
    observations = run_collectors(pkg["id"], logger=logger)

    # Generar diagnostico
    if logger:
        logger.info(f"Generando diagnostico para sintoma: {symptom}")
    
    diagnostic = diagnose(symptom, observations)

    # Generar reportes
    reports_dir = rutas.dir_reports()
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Reporte consola
    console = ConsoleReporter()
    print("\n" + console.render(diagnostic))

    # Reporte HTML
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_reporter = HtmlReporter()
    html_path = reports_dir / f"diagnostico_{pkg['id']}_{timestamp}.html"
    html_reporter.render(diagnostic, html_path)

    print(f"\nReporte HTML guardado en: {html_path}")

    # Abrir en navegador si se pidio
    if open_browser:
        print("Abriendo reporte en el navegador...")
        if open_in_browser(html_path):
            print("Reporte abierto exitosamente.")
        else:
            print("No se pudo abrir automaticamente. Puede abrirlo manualmente.")


def run_collectors(package_id: str, logger=None) -> list[CollectorResult]:
    """Ejecuta los colectores de un paquete."""
    executor = CollectorExecutor()
    packages = discover_packages()
    package = next((p for p in packages if p.name == package_id), None)

    if not package:
        if logger:
            logger.error(f"Paquete no encontrado: {package_id}")
        return []

    observations = []
    collectors = list(package.collectors)
    total = len(collectors)

    print(f"\nEjecutando {total} colector(es)...\n")

    for i, collector in enumerate(collectors, 1):
        show_progress(i - 1, total, f"Colectores ({i-1}/{total})")
        
        if logger:
            logger.info(f"Ejecutando colector: {collector.id}")

        print(f"  Ejecutando: {collector.label}...", end=" ", flush=True)

        try:
            result = executor.run_package_collector(package_id, collector.script)

            if isinstance(result, dict) and "error" in result and "collector_id" not in result:
                print(f"[ERROR] {result['error']}")
                if logger:
                    logger.error(f"Error en colector {collector.id}: {result['error']}")
                continue

            query_data = result.get("query", {}) if isinstance(result, dict) else {}
            observations.append(CollectorResult(
                collector_id=result.get("collector_id", collector.id) if isinstance(result, dict) else collector.id,
                data=result.get("data", {}) if isinstance(result, dict) else {},
                query=QueryInfo(
                    status=query_data.get("status", "unknown"),
                    duration_ms=query_data.get("duration_ms", 0),
                    timeout_seconds=query_data.get("timeout_seconds", 15),
                ),
            ))
            print(f"[OK]")
        except Exception as e:
            print(f"[ERROR] {e}")
            if logger:
                logger.error(f"Error en colector {collector.id}: {e}")

    show_progress(total, total, f"Colectores ({total}/{total})")
    print()
    
    return observations


def _obs_a_dict(o: CollectorResult) -> dict:
    """Serializa una observacion CollectorResult a dict para el informe."""
    return {
        "collector_id": o.collector_id,
        "query": {
            "status": o.query.status,
            "duration_ms": o.query.duration_ms,
            "timeout_seconds": o.query.timeout_seconds,
        },
        "data": o.data,
        "errors": o.errors,
    }


def cmd_diagnose(args):
    """Comando diagnose: Ejecuta un diagnostico directo."""
    symptom = args.symptom
    package_id = args.package or "impresion"
    output_dir = Path(args.output_dir) if args.output_dir else rutas.dir_reports()
    open_browser = args.open

    output_dir.mkdir(parents=True, exist_ok=True)

    # Configurar logging si se pidio
    logger = None
    if args.log:
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = get_logger(log_file=log_path)
        logger.info(f"Iniciando diagnostico: {symptom}")
        logger.info(f"Paquete: {package_id}")

    print(f"Ejecutando diagnostico: {symptom}")
    print(f"Paquete: {package_id}")

    # Ejecutar colectores
    observations = run_collectors(package_id, logger=logger)

    # Generar diagnostico
    diagnostic = diagnose(symptom, observations)

    # Reporte consola
    console = ConsoleReporter()
    print("\n" + console.render(diagnostic))

    # Reporte HTML
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_reporter = HtmlReporter()
    html_path = output_dir / f"diagnostico_{symptom}_{timestamp}.html"
    html_reporter.render(diagnostic, html_path)

    print(f"\nReporte HTML guardado en: {html_path}")

    # Informes Word y PDF
    from .core.informe import informe_a_doc, informe_a_pdf, informe_desde_diagnostico

    pkg = next((p for p in discover_packages() if p.name == package_id), None)
    from .core import knowledge_base as kb_mod

    findings_json = []
    for f in diagnostic.findings:
        k = kb_mod.knowledge_json(f)
        findings_json.append({
            "severity": f.severity,
            "collector_id": f.collector_id,
            "message": f.message,
            "details": f.details,
            "knowledge_id": f.knowledge_id,
            "knowledge": k,
            "solutions": (k or {}).get("soluciones") or None,
        })
    diag_dict = {
        "package": package_id,
        "package_label": pkg.label if pkg else package_id,
        "symptom": symptom,
        "results": [_obs_a_dict(o) for o in observations],
        "findings": findings_json,
        "recommendations": diagnostic.recommendations,
        "collectors_count": len(observations),
        "ok_count": sum(1 for o in observations if o.query.status == "ok"),
        "error_count": sum(1 for o in observations if o.query.status != "ok"),
        "timestamp": datetime.now().isoformat(),
    }
    informe = informe_desde_diagnostico(diag_dict)
    doc_path = output_dir / f"diagnostico_{symptom}_{timestamp}.doc"
    pdf_path = output_dir / f"diagnostico_{symptom}_{timestamp}.pdf"
    doc_path.write_bytes(informe_a_doc(informe, resultados_completos=diag_dict["results"]))
    pdf_path.write_bytes(informe_a_pdf(informe))
    print(f"Informe Word guardado en: {doc_path}")
    print(f"Informe PDF guardado en: {pdf_path}")

    # Abrir en navegador si se pidio
    if open_browser or args.yes:
        print("Abriendo reporte en el navegador...")
        if open_in_browser(html_path):
            print("Reporte abierto exitosamente.")
        else:
            print("No se pudo abrir automaticamente.")

    if logger:
        logger.info(f"Diagnostico completado. Reporte: {html_path}")


def cmd_snapshot(args):
    """Comando snapshot: Ejecuta los colectores y guarda una instantanea real."""
    from concurrent.futures import ThreadPoolExecutor
    from .core.comparator import save_snapshot
    from .core.registry import discover_packages
    from .web_server import run_diagnostic, _snapshot_from_results

    output_path = Path(args.output) if args.output else None

    packages = discover_packages()
    if args.package:
        packages = [p for p in packages if p.name == args.package]
        if not packages:
            print(f"Error: paquete '{args.package}' no encontrado.")
            print("Use list-packages para ver los disponibles.")
            sys.exit(1)

    print(f"Ejecutando colectores de {len(packages)} paquete(s)...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        diagnostics = list(pool.map(lambda p: run_diagnostic(p.name), packages))

    results = []
    for diag in diagnostics:
        if diag.get("error"):
            print(f"  Aviso: {diag['error']}")
            continue
        results.extend(diag.get("results") or [])

    if not results:
        print("Error: no se obtuvieron resultados de los colectores.")
        sys.exit(1)

    ok = sum(1 for r in results
             if (r.get("query") or {}).get("status") == "ok")
    print(f"  Colectores ejecutados: {len(results)} (ok: {ok})")

    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"snapshot_{timestamp}.json")

    snapshot = _snapshot_from_results(results)
    save_snapshot(snapshot, output_path)
    print(f" Instantanea guardada en: {output_path}")
    if args.description:
        print(f" Descripcion: {args.description}")


def cmd_compare(args):
    """Comando compare: Compara dos instantaneas."""
    from .core.comparator import load_snapshot, compare_snapshots

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)
    output_path = Path(args.output) if args.output else None

    print(f"Comparando instantaneas...")
    print(f"  Baseline: {baseline_path}")
    print(f"  Actual: {current_path}")

    baseline = load_snapshot(baseline_path)
    current = load_snapshot(current_path)

    differences = compare_snapshots(baseline, current)

    if not differences:
        print("\nNo se encontraron diferencias entre las instantaneas.")
        return

    print(f"\nSe encontraron {len(differences)} diferencia(s):\n")
    for diff in differences:
        print(f"  [{diff.severity.upper()}] {diff.collector_id}")
        print(f"    Campo: {diff.field_path}")
        print(f"    Antes: {diff.baseline_value}")
        print(f"    Ahora: {diff.current_value}")
        print()

    if output_path:
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([d.__dict__ for d in differences], f, indent=2, ensure_ascii=False)
        print(f"Diferencias guardadas en: {output_path}")


def cmd_list_packages(args):
    """Comando list-packages: Lista los paquetes disponibles."""
    packages = discover_packages()

    if not packages:
        print("No se encontraron paquetes.")
        return

    print(f"Se encontraron {len(packages)} paquete(s):\n")

    for pkg in packages:
        print(f"  {pkg.label} ({pkg.name})")
        print(f"    Version: {pkg.version}")
        print(f"    Descripcion: {pkg.description}")
        print(f"    Sintomas: {', '.join(pkg.symptoms) if pkg.symptoms else 'Ninguno'}")
        print(f"    Colectores: {len(pkg.collectors)}")
        for col in pkg.collectors:
            print(f"      - {col.label} ({col.id})")
        print()


def construir_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de la linea de comandos."""
    parser = argparse.ArgumentParser(
        description="DiagUSB - Herramienta de Diagnostico USB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m diagusb                           # Menu interactivo
  python -m diagusb diagnose                  # Diagnostico interactivo
  python -m diagusb diagnose --package impresion --symptom la_impresora_no_imprime --open
  python -m diagusb snapshot                 # Crear instantanea
  python -m diagusb list-packages             # Ver paquetes disponibles
  python -m diagusb web                       # Interfaz web en http://localhost:8080
        """
    )

    parser.add_argument("--version", action="version", version=f"DiagUSB {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Modo verbose (debug)")
    parser.add_argument("--yes", "-y", action="store_true", help="Responder si a todas las preguntas")
    parser.add_argument("--open", action="store_true", help="Abrir reporte HTML en el navegador")
    parser.add_argument("--log", metavar="ARCHIVO", help="Guardar log en archivo")
    parser.add_argument("--elevar", action="store_true",
                        help="Solicitar permisos de Administrador (UAC) al arrancar")
    parser.add_argument("--no-elevate", action="store_true",
                        help="Sin efecto (compatibilidad): la elevacion ya no es automatica")

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # Comando diagnose
    diagnose_parser = subparsers.add_parser("diagnose", help="Ejecutar diagnostico")
    diagnose_parser.add_argument("--package", "-p", help="Nombre del paquete")
    diagnose_parser.add_argument("--symptom", "-s", help="Sintoma a diagnosticar")
    diagnose_parser.add_argument("--output-dir", "-o", help="Directorio de salida para reportes")

    # Comando snapshot
    snapshot_parser = subparsers.add_parser("snapshot", help="Crear instantanea del sistema")
    snapshot_parser.add_argument("--output", "-o", help="Archivo de salida")
    snapshot_parser.add_argument("--description", "-d", help="Descripcion de la instantanea")
    snapshot_parser.add_argument("--package", "-p", help="Solo los colectores de un paquete")

    # Comando compare
    compare_parser = subparsers.add_parser("compare", help="Comparar instantaneas")
    compare_parser.add_argument("baseline", help="Instantanea base (antes)")
    compare_parser.add_argument("current", help="Instantanea actual (despues)")
    compare_parser.add_argument("--output", "-o", help="Archivo de salida para diferencias")

    # Comando list-packages
    subparsers.add_parser("list-packages", help="Listar paquetes disponibles")

    # Comando web
    web_parser = subparsers.add_parser("web", help="Abrir la interfaz web interactiva")
    web_parser.add_argument("--port", type=int, default=8080, help="Puerto del servidor (8080)")

    return parser


def main():
    """Punto de entrada principal."""
    parser = construir_parser()
    args = parser.parse_args()

    # Consolas Windows (cp1252) no pueden imprimir el banner Unicode
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
    except (AttributeError, ValueError):
        pass

    show_banner()

    # Elevar a Administrador solo si se pidio explicitamente con --elevar
    if args.elevar and args.command in (None, "diagnose", "snapshot"):
        from .core.elevation import (comando_relanzable, desactivada,
                                     elevar_cli, is_elevado)
        if not desactivada() and not is_elevado():
            print("Solicitando permisos de Administrador (acepte el dialogo de Windows)...")
            codigo = elevar_cli(comando_relanzable("diagusb"))
            if codigo is not None:
                sys.exit(codigo)
            print("Aviso: permisos de Administrador no otorgados; diagnostico con "
                  "permisos limitados (algunos datos pueden faltar).\n")

    # Si no hay subcomando, mostrar menu interactivo
    if not args.command:
        interactive_menu(yes_flag=args.yes, open_browser=args.open)
        return

    # Ejecutar subcomando
    if args.command == "diagnose":
        if not args.symptom:
            print("Error: --symptom es requerido para diagnose")
            print("Use: python -m diagusb diagnose --symptom la_impresora_no_imprime")
            sys.exit(1)
        cmd_diagnose(args)
    elif args.command == "snapshot":
        cmd_snapshot(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "list-packages":
        cmd_list_packages(args)
    elif args.command == "web":
        from .web_server import run_server
        from .core.elevation import comando_relanzable
        run_server(args.port, elevar=args.elevar,
                   comando=comando_relanzable("diagusb"))


if __name__ == "__main__":
    main()
