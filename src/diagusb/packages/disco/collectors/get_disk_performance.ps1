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

$result = New-DiagUsbCollectorResult -CollectorId 'disk_performance' -ScriptBlock {
    $perfData = Get-CimInstance -ClassName Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object { $_.Name -ne '_Total' }

    $items = @()
    foreach ($disk in $perfData) {
        $items += [ordered]@{
            disk = $disk.Name
            read_bytes_per_sec = $disk.DiskReadBytesPerSec
            write_bytes_per_sec = $disk.DiskWriteBytesPerSec
            read_ops_per_sec = $disk.DiskReadsPerSec
            write_ops_per_sec = $disk.DiskWritesPerSec
            avg_transfer_sec = $(if ($disk.AvgDisksecPerTransfer) { [math]::Round($disk.AvgDisksecPerTransfer / 1000, 4) } else { 0 })
            current_disk_queue_length = $disk.CurrentDiskQueueLength
            percent_disk_time = $disk.PercentDiskTime
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
