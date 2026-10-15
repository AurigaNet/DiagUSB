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

$result = New-DiagUsbCollectorResult -CollectorId 'physical_disks' -ScriptBlock {
    $physicalDisks = Get-PhysicalDisk -ErrorAction Stop

    $items = @()
    foreach ($disk in $physicalDisks) {
        $reliability = @(Get-StorageReliabilityCounter -PhysicalDisk $disk -ErrorAction SilentlyContinue) | Select-Object -First 1

        $powerOnHours = $null
        $temperature = $null
        $reallocatedSectors = $null
        if ($null -ne $reliability) {
            $powerOnHours = Get-DiagUsbPropertyValue -InputObject $reliability -PropertyName 'PowerOnHours'
            $temperature = Get-DiagUsbPropertyValue -InputObject $reliability -PropertyName 'Temperature'
            $reallocatedSectors = Get-DiagUsbPropertyValue -InputObject $reliability -PropertyName 'ReallocatedSectorsCount'
        }

        $items += [ordered]@{
            device_id = $disk.DeviceId
            serial_number = $disk.SerialNumber
            friendly_name = $disk.FriendlyName
            media_type = switch ($disk.MediaType) { 0 { 'Unspecified' } 3 { 'HDD' } 4 { 'SSD' } 5 { 'SCM' } default { 'Unknown' } }
            size_gb = [math]::Round($disk.Size / 1GB, 2)
            health_status = "$($disk.HealthStatus)"
            operational_status = "$($disk.OperationalStatus)"
            power_on_hours = $powerOnHours
            temperature = $temperature
            reallocated_sectors = $reallocatedSectors
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
