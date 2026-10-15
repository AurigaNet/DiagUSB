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