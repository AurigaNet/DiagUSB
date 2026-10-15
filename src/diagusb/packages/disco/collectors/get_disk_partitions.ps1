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

$result = New-DiagUsbCollectorResult -CollectorId 'disk_partitions' -ScriptBlock {
    $partitions = Get-CimInstance -ClassName Win32_DiskPartition | Where-Object { $_.Size -gt 0 }

    $items = @()
    foreach ($partition in $partitions) {
        $items += [ordered]@{
            disk_index = $partition.DiskIndex
            partition_index = $partition.Index
            partition_type = if ($partition.Type -like '*GPT*') { 'GPT' } elseif ($partition.Type -like '*MBR*') { 'MBR' } else { 'Unknown' }
            size_gb = [math]::Round($partition.Size / 1GB, 2)
            starting_offset = $partition.StartingOffset
            bootable = $partition.Bootable
            boot_partition = $partition.BootPartition
            primary_partition = $partition.PrimaryPartition
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
