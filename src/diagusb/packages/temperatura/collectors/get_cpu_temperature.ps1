# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

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

$result = New-DiagUsbCollectorResult -CollectorId 'cpu_temperature' -TimeoutSeconds 15 -ScriptBlock {
    $data = $null
    $motivoLib = $null
    try {
        $data = Get-DiagUsbLhmCpuTemperatureFromLib
    }
    catch {
        $motivoLib = $_.Exception.Message
    }

    # Respaldo: si ya hay un LibreHardwareMonitor con servidor web en 8085.
    if ($null -eq $data) {
        try {
            $data = Get-DiagUsbLhmCpuTemperature -TimeoutSec 3
        }
        catch {
            $motivoHttp = $_.Exception.Message
            throw "DIAGUSB_NOT_AVAILABLE: no se pudo leer la temperatura. DLL: $motivoLib | HTTP 8085: $motivoHttp"
        }
    }

    if ($null -eq $data) {
        throw 'DIAGUSB_NOT_AVAILABLE: LibreHardwareMonitor no expone temperatura del CPU. Ejecute DiagUSB como administrador y verifique PawnIO.'
    }

    return [ordered]@{
        source = 'librehardwaremonitor'
        via = $data.via
        available = $true
        sampled_at_utc = Get-DiagUsbTimestampUtc
        cpu_name = $data.cpu_name
        package_temp_c = $data.package_temp_c
        max_core_temp_c = $data.max_core_temp_c
        average_core_temp_c = $data.average_core_temp_c
        max_temp_c = $data.max_temp_c
        sensor_count = $data.sensor_count
        sensors = $data.sensors
    }
}

Write-DiagUsbJson -InputObject $result
