# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

import os

block_cipher = None

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))


def R(rel: str) -> str:
    return os.path.join(ROOT, rel)


a = Analysis(
    [R('build/entry_gui.py')],
    pathex=[R('src')],
    binaries=[],
    datas=[
        (R('src/diagusb/packages'), 'diagusb/packages'),
        (R('src/diagusb/static'), 'diagusb/static'),
        (R('src/diagusb/core/base_conocimiento.json'), 'diagusb/core'),
        (R('collectors'), 'collectors'),
        (R('manifiesto_hashes.json'), '.'),
    ],
    hiddenimports=['diagusb.web_server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DiagUSB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=R('assets/branding/diagusb.ico'),
    version=R('build/version_info_gui.txt'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DiagUSB',
)
