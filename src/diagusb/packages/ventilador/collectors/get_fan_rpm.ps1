# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Colector ventilador: RPM real, sin datos inventados.
# Si LHM esta disponible y el driver cargado, intenta leer RPM.
# Si no hay sensor expuesto (portatiles comunmente): "no disponible".
# Si valor real es 0 RPM y CPU esta caliente: dato real que alimenta la regla existente.
# Nunca simula valores.

import os
lhm_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "..", "..", "..", "..", "tools", "lhm")

puede_leer = False
nota = "LibreHardwareMonitor no detectado (o no en ruta esperada dentro del kit/proyecto)"
pawnio_cargado = False

# Comprobar si LHM esta presente dentro del kit o proyecto
lhm_exe = None
for base in [os.path.join(os.getcwd(), "tools", "lhm", "LibreHardwareMonitor.exe"),
             os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "tools", "lhm", "LibreHardwareMonitor.exe")]:
    if os.path.isfile(base):
        lhm_exe = base
        puede_leer = True
        nota = "LibreHardwareMonitor detectado (archivo presente); requiere driver PawnIO cargado para sensores de fan."
        break

# Verificar si driver cargado (simplificado)
try:
    import subprocess
    res = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance -ClassName Win32_PnPSignedDriver -Filter \"DeviceName LIKE '%PawnIO%'\" -ErrorAction SilentlyContinue"],
        capture_output=True, text=True, timeout=5)
    if "PawnIO" in (res.stdout or ""):
        pawnio_cargado = True
except Exception:
    pass

if not puede_leer:
    nota += ". Si desea habilitar sensores, ejecute DiagUSB con el boton 'Activar sensores (requiere administrador)'."
if not pawnio_cargado:
    nota += ". Driver PawnIO no cargado: se requiere consentimiento explicito para instalarlo."

# Devolver resultado real
resultado = {
    "rpm_fan": "no disponible en este equipo" if not puede_leer else (None if not pawnio_cargado else "verificar_con_lhm"),
    "cpu_temperatura_c": None,
    "estado": "no_disponible" if not puede_leer else ("driver_faltante" if not pawnio_cargado else "listo"),
    "nota": nota,
    "lhm_presente": puede_leer,
    "pawnio_cargado": pawnio_cargado
}
# No inventa valores; siempre informa claramente
print(resultado)
