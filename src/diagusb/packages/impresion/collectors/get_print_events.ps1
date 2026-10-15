# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

[CmdletBinding()]
param(
    [ValidateRange(1, 200)]
    [int]$MaxEvents = 20
)

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

$result = New-DiagUsbCollectorResult -CollectorId 'print_service_events' -ScriptBlock {
    $logs = @(
        'Microsoft-Windows-PrintService/Admin',
        'Microsoft-Windows-PrintService/Operational'
    )

    $output = @()
    foreach ($logName in $logs) {
        $logInfo = Get-WinEvent -ListLog $logName -ErrorAction SilentlyContinue
        $eventsForLog = @()

        if ($logInfo -and $logInfo.IsEnabled) {
            try {
                $eventsForLog = @(Get-WinEvent -LogName $logName -MaxEvents $MaxEvents -ErrorAction SilentlyContinue | ForEach-Object {
                    Get-DiagUsbEventRecord -Event $_
                })
            }
            catch {
                $eventsForLog = @()
            }
        }

        $output += [ordered]@{
            log_name = $logName
            record_count = $(if ($logInfo) { $logInfo.RecordCount } else { $null })
            oldest_record_number = $(if ($logInfo) { $logInfo.OldestRecordNumber } else { $null })
            is_enabled = [bool]$(if ($logInfo) { $logInfo.IsEnabled } else { $false })
            log_mode = $(if ($logInfo) { $logInfo.LogMode.ToString() } else { $null })
            maximum_size_bytes = $(if ($logInfo) { $logInfo.MaximumSizeInBytes } else { $null })
            events = $eventsForLog
        }
    }

    return $output
}

Write-DiagUsbJson -InputObject $result -Depth 10