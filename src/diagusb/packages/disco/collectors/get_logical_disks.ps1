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

$result = New-DiagUsbCollectorResult -CollectorId 'logical_disks' -ScriptBlock {
    $disks = Get-CimInstance -ClassName Win32_LogicalDisk | Where-Object { $_.DriveType -in @(2, 3) }

    $items = @()
    foreach ($disk in $disks) {
        $totalSize = if ($disk.Size) { [math]::Round($disk.Size / 1GB, 2) } else { 0 }
        $freeSpace = if ($disk.FreeSpace) { [math]::Round($disk.FreeSpace / 1GB, 2) } else { 0 }
        $freePercent = if ($disk.Size -gt 0) { [math]::Round(($disk.FreeSpace / $disk.Size) * 100, 1) } else { 0 }
        $usedPercent = [math]::Round(100 - $freePercent, 1)

        $items += [ordered]@{
            device_id = $disk.DeviceID
            drive_type = switch ($disk.DriveType) { 2 { 'Removable' } 3 { 'Fixed' } default { 'Unknown' } }
            total_gb = $totalSize
            free_gb = $freeSpace
            used_percent = $usedPercent
            free_percent = $freePercent
            volume_name = $disk.VolumeName
            file_system = $disk.FileSystem
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
