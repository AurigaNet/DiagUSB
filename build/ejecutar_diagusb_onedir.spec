# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Especificacion PyInstaller de DiagUSB en modo carpeta (onedir).

El instalador de Inno Setup empaqueta esta carpeta. A diferencia del onefile,
el ejecutable que ve el usuario no es un archivo comprimido con todo adentro:
es un lanzador normal junto a una carpeta ``_internal`` con los datos. Esa
estructura es la que usan las aplicaciones de escritorio y la que no dispara
las heuristicas que si marcan el onefile de PyInstaller.

Se excluyen del paquete los archivos de LibreHardwareMonitor que DiagUSB no
usa (la interfaz grafica, su configuracion, los simbolos .pdb y la
documentacion XML). Solo se necesita LibreHardwareMonitorLib.dll y sus
dependencias.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))


def R(rel):
    return os.path.join(ROOT, rel)


# Archivos de LibreHardwareMonitor que no se usan en tiempo de ejecucion.
_LHM_EXCLUIDOS = {
    'LibreHardwareMonitor.exe',
    'LibreHardwareMonitor.exe.config',
    'LibreHardwareMonitorLib.pdb',
    'LibreHardwareMonitorLib.xml',
    'Aga.Controls.pdb',
}


def _datas_lhm():
    """Datas de tools/lhm sin la interfaz grafica ni los simbolos.

    PyInstaller interpreta el segundo elemento como carpeta destino y agrega
    el nombre del archivo: se pasa la carpeta, no la ruta completa.
    """
    base = R('tools/lhm')
    salida = []
    for raiz, _dirs, archivos in os.walk(base):
        relativo = os.path.relpath(raiz, base).replace('\\', '/')
        destino = 'tools/lhm' if relativo == '.' else 'tools/lhm/' + relativo
        for nombre in archivos:
            if nombre in _LHM_EXCLUIDOS or nombre.lower().endswith('.pdb'):
                continue
            salida.append((os.path.join(raiz, nombre), destino))
    return salida


datas = [
    (R('src/diagusb/packages'), 'diagusb/packages'),
    (R('src/diagusb/static'), 'diagusb/static'),
    (R('src/diagusb/core/base_conocimiento.json'), 'diagusb/core'),
    (R('collectors'), 'collectors'),
] + _datas_lhm()
_manifiesto = R('manifiesto_hashes.json')
if os.path.isfile(_manifiesto):
    datas.append((_manifiesto, '.'))

a = Analysis(
    [R('launcher_exe.py')],
    pathex=[R('src')],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ejecutar DiagUSB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=R('assets/branding/diagusb.ico'),
    version=R('build/version_info.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='DiagUSB',
)
