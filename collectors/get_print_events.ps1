# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

[CmdletBinding()]
param(
    [ValidateRange(1, 200)]
    [int]$MaxEvents = 20
)

. (Join-Path $PSScriptRoot '_common.ps1')

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