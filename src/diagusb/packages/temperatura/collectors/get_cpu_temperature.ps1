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
    try {
        $data = Get-DiagUsbLhmCpuTemperature -TimeoutSec 8
    }
    catch {
        throw "DIAGUSB_NOT_AVAILABLE: $($_.Exception.Message)"
    }
    if ($null -eq $data) {
        throw 'DIAGUSB_NOT_AVAILABLE: LibreHardwareMonitor no expone temperatura del CPU. Verifique PawnIO y ejecute LHM como administrador.'
    }

    return [ordered]@{
        source = 'librehardwaremonitor'
        url = $data.url
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
