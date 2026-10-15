# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]$')]
    [string]$Unidad,
    [switch]$Ejecutar
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$driveLetter = $Unidad.ToUpperInvariant()
$targetRoot = '{0}:\' -f $driveLetter
$systemDrive = $env:SystemDrive.TrimEnd('\').TrimEnd(':').ToUpperInvariant()

Write-Host ('armar_pendrive: modo {0}' -f $(if ($Ejecutar) { 'EJECUCIÓN REAL' } else { 'SIMULACIÓN' }))
Write-Host ("Unidad solicitada: {0}" -f $targetRoot)

if ($driveLetter -eq $systemDrive) {
    throw ("La unidad {0}: es la del sistema. Operación cancelada." -f $driveLetter)
}

if (-not $Ejecutar) {
    Write-Host 'SIMULAR: no se formatea, no se particiona y no se borra ningún dispositivo.'
    Write-Host 'SIMULAR: se validaría que la unidad exista y sea extraíble antes de copiar archivos.'
    Write-Host 'SIMULAR: se copiarían únicamente archivos preparados por el técnico.'
    exit 0
}

if (-not (Test-Path -LiteralPath $targetRoot)) {
    throw ("La unidad {0} no existe o no está accesible." -f $targetRoot)
}

$confirmation = Read-Host ("Escriba la letra de unidad {0} para confirmar la copia" -f $driveLetter)
if ($confirmation.ToUpperInvariant() -ne $driveLetter) {
    throw 'Confirmación inválida. Operación cancelada.'
}

Write-Host 'Copia real todavía no implementada en F0.'
Write-Host 'No se realizó ninguna modificación.'