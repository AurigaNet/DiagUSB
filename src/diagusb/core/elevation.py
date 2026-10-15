# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Elevacion automatica a Administrador (dialogo UAC de Windows)."""

import os
import socket
import subprocess
import sys
import time

ES_WINDOWS = sys.platform == "win32"
DESACTIVADA_ENV = "DIAGUSB_NO_ELEVATE"

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_SHOWNORMAL = 1
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102


def desactivada() -> bool:
    """True si la auto-elevacion esta desactivada (variable de entorno)."""
    return DESACTIVADA_ENV in os.environ


def is_elevado() -> bool:
    """True si el proceso actual corre como Administrador."""
    if not ES_WINDOWS:
        try:
            return os.geteuid() == 0
        except AttributeError:
            return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def comando_relanzable(modulo: str = "diagusb") -> list[str]:
    """Linea de comandos que relanza el proceso actual (ejecutable o python -m)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, "-m", modulo, *sys.argv[1:]]


def _lanzar_elevado(comando: list[str]):
    """Lanza el comando pidiendo elevacion UAC.

    Devuelve el handle del proceso hijo, o None si el usuario rechazo
    el dialogo (o el lanzamiento fallo).
    """
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hKeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = comando[0]
    info.lpParameters = subprocess.list2cmdline(list(comando[1:]))
    info.nShow = _SW_SHOWNORMAL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return None
    return info.hProcess


def _esperar_codigo(handle) -> int | None:
    """Espera a que el hijo termine y devuelve su codigo de salida."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                             ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
    codigo = wintypes.DWORD(0)
    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo)):
        return None
    return int(codigo.value)


def _proceso_vivo(handle, esperar_ms: int) -> bool:
    """True si el proceso sigue vivo tras esperar_ms."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    return kernel32.WaitForSingleObject(handle, esperar_ms) == _WAIT_TIMEOUT


def puerto_en_uso(puerto: int) -> bool:
    """True si algo ya esta escuchando en el puerto local."""
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.5):
            return True
    except OSError:
        return False


def elevar_cli(comando: list[str]) -> int | None:
    """Relanza el comando elevado y espera a que termine.

    Devuelve el codigo de salida del proceso elevado, o None si el
    usuario rechazo el dialogo UAC o el lanzamiento fallo.
    """
    handle = _lanzar_elevado(comando)
    if handle is None:
        return None
    return _esperar_codigo(handle)


def elevar_servidor(comando: list[str], puerto: int, timeout: float = 20.0) -> bool:
    """Relanza el comando elevado y espera a que el hijo levante el puerto.

    True -> el proceso elevado ya esta sirviendo (este debe salir).
    False -> no se elevo; este proceso debe continuar (permisos limitados).
    """
    handle = _lanzar_elevado(comando)
    if handle is None:
        return False
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if puerto_en_uso(puerto):
            return True
        if not _proceso_vivo(handle, 400):
            return False
    return False
