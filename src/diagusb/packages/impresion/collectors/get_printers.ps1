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

$result = New-DiagUsbCollectorResult -CollectorId 'printers' -ScriptBlock {
    Get-CimInstance -ClassName Win32_Printer | Sort-Object -Property Name | ForEach-Object {
        [ordered]@{
            device_id = $_.DeviceID
            name = $_.Name
            system_name = $_.SystemName
            driver_name = $_.DriverName
            port_name = $_.PortName
            default = [bool]$_.Default
            network = [bool]$_.Network
            local = [bool]$_.Local
            shared = [bool]$_.Shared
            share_name = $_.ShareName
            hidden = [bool]$_.Hidden
            direct = [bool]$_.Direct
            do_complete_first = [bool]$_.DoCompleteFirst
            enable_bidi = [bool]$_.EnableBIDI
            keep_printed_jobs = [bool]$_.KeepPrintedJobs
            published = [bool]$_.Published
            queued = [bool]$_.Queued
            work_offline = [bool]$_.WorkOffline
            printer_status = $_.PrinterStatus
            detected_error_state = $_.DetectedErrorState
            extended_printer_status = $_.ExtendedPrinterStatus
            extended_detected_error_state = $_.ExtendedDetectedErrorState
            horizontal_resolution = $_.HorizontalResolution
            vertical_resolution = $_.VerticalResolution
            average_pages_per_minute = $_.AveragePagesPerMinute
            jobs = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'Jobs'
            location = $_.Location
            comment = $_.Comment
            server_name = $_.ServerName
        }
    }
}

Write-DiagUsbJson -InputObject $result