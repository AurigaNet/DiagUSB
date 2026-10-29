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

$result = New-DiagUsbCollectorResult -CollectorId 'top_processes' -ScriptBlock {
    # Porcentaje de CPU real por proceso (WMI, nombres de contador neutros al idioma).
    $nucleos = [int]$env:NUMBER_OF_PROCESSORS
    if ($nucleos -lt 1) { $nucleos = 1 }
    $porPid = @{}
    $porNombre = @{}
    try {
        foreach ($p in (Get-CimInstance -ClassName Win32_PerfFormattedData_PerfProc_Process -ErrorAction Stop)) {
            $pidProceso = [int]$p.IDProcess
            $nombre = [string]$p.Name
            $valor = [double]$p.PercentProcessorTime
            if ($pidProceso -gt 0) { $porPid[$pidProceso] = $valor }
            if ($nombre) { $porNombre[$nombre] = $valor }
        }
    }
    catch {
        $porPid = @{}
        $porNombre = @{}
    }

    Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 10 | ForEach-Object {
        $bruto = $null
        if ($porPid.ContainsKey([int]$_.Id)) {
            $bruto = [double]$porPid[[int]$_.Id]
        }
        elseif ($porNombre.ContainsKey([string]$_.ProcessName)) {
            $bruto = [double]$porNombre[[string]$_.ProcessName]
        }
        $cpuNormalizado = if ($null -ne $bruto) { [math]::Round($bruto / $nucleos, 2) } else { $null }
        [ordered]@{
            name = $_.ProcessName
            pid = $_.Id
            memory_mb = [math]::Round($_.WorkingSet64 / 1MB, 2)
            cpu_percent = $cpuNormalizado
            cpu_percent_total = if ($null -ne $bruto) { [math]::Round($bruto, 2) } else { $null }
            cpu_seconds = if ($_.CPU) { [math]::Round([double]$_.CPU, 2) } else { 0 }
            threads = $_.Threads.Count
            handles = $_.HandleCount
            start_time = if ($_.StartTime) { $_.StartTime.ToString('o') } else { $null }
        }
    }
}

Write-DiagUsbJson -InputObject $result
