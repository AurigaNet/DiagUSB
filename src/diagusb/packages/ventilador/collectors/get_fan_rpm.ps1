# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
# Colector real: RPM de ventiladores leidos directamente de
# LibreHardwareMonitorLib.dll. No lee fixtures ni inventa valores.
# Si no hay permisos o driver, informa DIAGUSB_NOT_AVAILABLE con el motivo.

[CmdletBinding()]
param()

$__diagusb_dir = $PSScriptRoot
$__diagusb_common = $null
while ($__diagusb_dir) {
    $__diagusb_candidate = Join-Path $__diagusb_dir 'collectors\_common.ps1'
    if (Test-Path -LiteralPath $__diagusb_candidate) { $__diagusb_common = $__diagusb_candidate; break }
    $__diagusb_parent = Split-Path -Path $__diagusb_dir -Parent
    if ($__diagusb_parent -eq $__diagusb_dir) { break }
    $__diagusb_dir = $__diagusb_parent
}
if (-not $__diagusb_common) {
    Write-Error 'DiagUSB: no se encontro collectors\_common.ps1'
    exit 1
}
. $__diagusb_common

$result = New-DiagUsbCollectorResult -CollectorId 'fan_speeds' -TimeoutSeconds 15 -ScriptBlock {
    try {
        $data = Get-DiagUsbLhmFanSpeedsFromLib
    }
    catch {
        throw "DIAGUSB_NOT_AVAILABLE: $($_.Exception.Message)"
    }

    if ($null -eq $data -or [int]$data.sensor_count -eq 0) {
        throw 'DIAGUSB_NOT_AVAILABLE: LibreHardwareMonitor no expone sensores de ventilador en este equipo. Ejecute DiagUSB como administrador y verifique PawnIO.'
    }

    return [ordered]@{
        source = 'librehardwaremonitor'
        via = $data.via
        available = $true
        sampled_at_utc = Get-DiagUsbTimestampUtc
        fan_rpms = $data.fan_rpms
        max_fan_rpm = $data.max_fan_rpm
        sensor_count = $data.sensor_count
        sensors = $data.sensors
    }
}

Write-DiagUsbJson -InputObject $result
