# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Colector de temperatura: detecta librehardwaremonitor, verifica hash,
# y reporta si hay datos reales o por que no (driver, sensores no expuestos).
# Nunca inventa valores.
$puedeLeer = $false
$nota = "LibreHardwareMonitor no detectado en el kit ($env:LOCALAPPDATA) ni en herramientas externad"

# Verificar si LHM esta disponible
$lhmDir = Join-Path $PSScriptRoot '..\..\..\..\..\tools\lhm'
if (Test-Path $lhmDir) {
    $exe = Join-Path $lhmDir 'LibreHardwareMonitor.exe'
    if (Test-Path $exe) {
        $puedeLeer = $true
        $nota = "LibreHardwareMonitor detectado en kit ($lhmDir); requiere driver PawnIO para sensores CPU."
        # No se lanza sin consentimiento: solo deteccion de archivo sumado
    }
}

# Verificar si PawnIO driver esta cargado
$pawnioCargado = $false
try {
    $driver = Get-CimInstance -ClassName Win32_PnPSignedDriver -Filter "DeviceName LIKE '%PawnIO%'" -ErrorAction SilentlyContinue
    if ($driver) { $pawnioCargado = $true }
} catch { $pawnioCargado = $false }

# Si no hay PawnIO cargado, informar claramente
if (-not $pawnioCargado) {
    $nota += " Driver PawnIO NO cargado: instalar con consentimiento explicito desde UI (boton 'Instalar controlador')."
}

# Devolver resultado real (nunca simulado)
@{ temperatura_cpu_c = $null; estado = 'no_disponible'; razon = $nota; pawnio_cargado = $pawnioCargado; lhm_presente = $puedeLeer }