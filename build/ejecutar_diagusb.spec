# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Especificacion PyInstaller de "Ejecutar DiagUSB.exe" (un solo archivo).

Incluye TODO lo que el programa lee en tiempo de ejecucion: paquetes con sus
manifiestos y colectores .ps1, static (HTML/CSS/JS), base de conocimiento,
colectores compartidos y manifiesto de integridad. Sin estos datos el analisis
arranca con "Paquetes analizados: 0" porque discover_packages() no encuentra
nada dentro del bundle.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))


def R(rel: str) -> str:
    return os.path.join(ROOT, rel)


datas = [
    (R('src/diagusb/packages'), 'diagusb/packages'),
    (R('src/diagusb/static'), 'diagusb/static'),
    (R('src/diagusb/core/base_conocimiento.json'), 'diagusb/core'),
    (R('collectors'), 'collectors'),
    (R('tools/lhm'), 'tools/lhm'),
]
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
    a.binaries,
    a.datas,
    [],
    name='Ejecutar DiagUSB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=R('assets/branding/diagusb.ico'),
    version=R('build/version_info.txt'),
)
