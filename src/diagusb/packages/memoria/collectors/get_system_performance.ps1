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

$result = New-DiagUsbCollectorResult -CollectorId 'system_performance' -ScriptBlock {
    $perfOS = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_System -ErrorAction SilentlyContinue
    $processor = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue)

    $upTimeSeconds = $null
    $queueLength = $null
    $threads = $null
    $objects = $null
    if ($null -ne $perfOS) {
        $upTimeSeconds = Get-DiagUsbPropertyValue -InputObject $perfOS -PropertyName 'SystemUpTime'
        $queueLength = Get-DiagUsbPropertyValue -InputObject $perfOS -PropertyName 'ProcessorQueueLength'
        $threads = Get-DiagUsbPropertyValue -InputObject $perfOS -PropertyName 'Threads'
        $objects = Get-DiagUsbPropertyValue -InputObject $perfOS -PropertyName 'Objects'
    }

    $systemUptime = if ($null -ne $upTimeSeconds) {
        [TimeSpan]::FromSeconds([double]$upTimeSeconds).ToString()
    } else { $null }

    $cpuLoad = if ($processor.Count -gt 0) {
        [math]::Round(($processor | Measure-Object -Property LoadPercentage -Average).Average, 1)
    } else { $null }

    return [ordered]@{
        processor_queue_length = $queueLength
        system_uptime = $systemUptime
        system_uptime_seconds = $upTimeSeconds
        threads = $threads
        objects = $objects
        cpu_load_percent = $cpuLoad
    }
}

Write-DiagUsbJson -InputObject $result
