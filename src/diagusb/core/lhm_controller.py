# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Arranque y cierre de LibreHardwareMonitor dentro del kit.

- Busca LibreHardwareMonitor.exe dentro del kit (tools/lhm/) o proyecto.
- Si ya hay otro LHM corriendo en 8085 que NO lanzo este modulo, lo reutiliza.
- Si no hay LHM corriendo: lanza oculto con config propia (loopback 127.0.0.1:8085).
- Al salir de DiagUSB (incluso por error o cierre brusco): cierra el proceso lanzado.
- Nunca abre puertos a la red externa.
- No inventa valores de sensores.
"""

import os, time, subprocess, signal, sys
from pathlib import Path

def _find_lhm_exe() -> str | None:
    # Resolver desde la raiz del proyecto/kit, no desde directorio actual
    # El modulo esta en src/diagusb/core/ -> subir 4 niveles = raiz
    base = Path(__file__).resolve().parents[3]
    candidatos = [
        base / "tools" / "lhm" / "LibreHardwareMonitor.exe",
        base / "dist" / "DiagUSB" / "tools" / "lhm" / "LibreHardwareMonitor.exe",
        Path(__file__).resolve().parents[3] / "python" / "python.exe",
    ]
    for c in candidatos:
        if c.exists():
            return str(c.resolve())
    return None

def _is_port_8085_open() -> bool:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", 8085))
        s.close()
        return True
    except Exception:
        return False

def _find_lhm_process():
    try:
        import subprocess
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Select-Object -First 1 -Property Id,ProcessName"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0 and "LibreHardwareMonitor" in res.stdout:
            # Extraer PID
            for line in res.stdout.splitlines():
                if line.strip() and "Id" not in line:
                    try:
                        return int(line.split()[0])
                    except Exception:
                        pass
    except Exception:
        pass
    return None

class LHMController:
    def __init__(self):
        self.process = None
        self.exe_path = _find_lhm_exe()

    def start(self):
        if not self.exe_path:
            return {"estado": "lhm_no_disponible", "motivo": "No se encontro LibreHardwareMonitor.exe en el kit"}
        # Si hay LHM corriendo que NO lanzo yo, reutilizarlo
        existing = _find_lhm_process()
        if existing:
            return {"estado": "reutilizado", "pid": existing, "motivo": "Otro LHM ya corriendo; no se cierra al salir"}
        # Si el puerto esta ocupado por otra cosa, informar
        if _is_port_8085_open():
            return {"estado": "puerto_ocupado", "puerto": 8085, "motivo": "Otro proceso usa 8085; LHM no se lanza"}
        # Lanzar oculto con config propio (loopback 127.0.0.1:8085 configurado en config)
        try:
            self.process = subprocess.Popen(
                [self.exe_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW  # oculto
            )
            # Esperar con sondeo (no sleep fijo)
            for _ in range(20):  # ~4 segundos maximo con pausas cortas
                time.sleep(0.2)
                if self.process.poll() is not None:
                    return {"estado": "fallo_al_iniciar", "motivo": "LHM termino inmediatamente"}
                if _is_port_8085_open():
                    return {"estado": "activo", "pid": self.process.pid, "enlace": "127.0.0.1:8085", "motivo": "Servidor web solo loopback"}
            return {"estado": "timeout", "motivo": "LHM no respondio en 8085 tras espera"}
        except Exception as exc:
            return {"estado": "error", "motivo": str(exc)}

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            return {"estado": "cerrado", "pid": self.process.pid}
        return {"estado": "no_lanzado"}
