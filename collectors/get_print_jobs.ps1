# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

$result = New-DiagUsbCollectorResult -CollectorId 'print_jobs' -ScriptBlock {
    Get-CimInstance -ClassName Win32_PrintJob | Sort-Object -Property Name | ForEach-Object {
        [ordered]@{
            name = $_.Name
            document = $_.Document
            driver_name = $_.DriverName
            host_print_queue = $_.HostPrintQueue
            job_id = $_.JobId
            owner = $_.Owner
            priority = $_.Priority
            size_bytes = $_.Size
            total_pages = $_.TotalPages
            pages_printed = $_.PagesPrinted
            elapsed_time_seconds = $_.ElapsedTime
            status_mask = $_.StatusMask
            time_submitted_utc = Convert-DiagUsbDateTime -Value $_.TimeSubmitted
        }
    }
}

Write-DiagUsbJson -InputObject $result