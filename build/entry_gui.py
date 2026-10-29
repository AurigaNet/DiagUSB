# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Punto de entrada sin consola para la aplicacion instalada y portable."""

from __future__ import annotations

import os
import sys
import traceback

sys.dont_write_bytecode = True


def _abrir_registro():
    try:
        from diagusb.core import rutas

        base = rutas.dir_base()
        base.mkdir(parents=True, exist_ok=True)
        return open(base / "diagusb.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        return open(os.devnull, "w", encoding="utf-8")


def _preparar_salida():
    if sys.stdout is not None and sys.stderr is not None:
        return None
    registro = _abrir_registro()
    if sys.stdout is None:
        sys.stdout = registro
    if sys.stderr is None:
        sys.stderr = registro
    return registro


def _mostrar_error(mensaje: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, mensaje, "DiagUSB", 0x10)
    except Exception:
        pass


def _puerto_solicitado(argv: list[str]) -> int:
    if "web" not in argv:
        return 8080
    resto = argv[argv.index("web") + 1:]
    for i, arg in enumerate(resto):
        if arg == "--port" and i + 1 < len(resto):
            try:
                return int(resto[i + 1])
            except ValueError:
                break
        if arg.startswith("--port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                break
    return 8080


def main() -> int:
    registro = _preparar_salida()
    try:
        from diagusb.web_server import run_server

        run_server(_puerto_solicitado(sys.argv[1:]))
        return 0
    except SystemExit as exc:
        codigo = exc.code if isinstance(exc.code, int) else 1
        if codigo:
            _mostrar_error(
                "DiagUSB no pudo iniciarse.\n\n"
                "Puede haber otra instancia abierta usando el puerto 8080. "
                "Cerrá la instancia anterior e intentá de nuevo.\n\n"
                f"Detalle: {exc}"
            )
        return codigo
    except Exception as exc:
        traceback.print_exc()
        _mostrar_error(
            "DiagUSB no pudo iniciarse.\n\n"
            f"Detalle: {exc}\n\n"
            "El registro de la aplicación está en la carpeta de datos."
        )
        return 1
    finally:
        if registro is not None:
            try:
                registro.flush()
                registro.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
