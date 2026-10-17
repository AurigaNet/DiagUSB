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
        $busType = "$($disk.BusType)"
        $counter = $null
        $motivo = $null

        if ($busType -eq 'USB') {
            $motivo = 'no aplica a unidades USB'
        }
        else {
            $job = Start-Job -ScriptBlock {
                param($devId)
                $d = @(Get-PhysicalDisk -ErrorAction SilentlyContinue) |
                    Where-Object { "$($_.DeviceId)" -eq $devId } | Select-Object -First 1
                if ($null -eq $d) { return }
                @(Get-StorageReliabilityCounter -PhysicalDisk $d -ErrorAction SilentlyContinue) |
                    Select-Object -First 1
            } -ArgumentList "$($disk.DeviceId)"
            $listo = $false
            try {
                $listo = [bool](Wait-Job -Job $job -Timeout 10)
                if ($listo) {
                    $counter = @(Receive-Job -Job $job -ErrorAction SilentlyContinue) | Select-Object -First 1
                }
            }
            finally {
                Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
                Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null
            }
            if (-not $listo) {
                $motivo = 'sin respuesta en 10 s'
            }
            elseif ($null -eq $counter) {
                $motivo = 'sin datos de confiabilidad'
            }
        }

        $reliability = $null
        $powerOnHours = $null
        $temperature = $null
        $reallocatedSectors = $null
        if ($null -ne $counter) {
            $powerOnHours = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'PowerOnHours'
            $temperature = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'Temperature'
            $reallocatedSectors = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'ReallocatedSectorsCount'
            $reliability = [ordered]@{
                power_on_hours = $powerOnHours
                temperature = $temperature
                reallocated_sectors = $reallocatedSectors
            }
        }

        $items += [ordered]@{
            device_id = $disk.DeviceId
            serial_number = $disk.SerialNumber
            friendly_name = $disk.FriendlyName
            bus_type = $busType
            media_type = switch ($disk.MediaType) { 0 { 'Unspecified' } 3 { 'HDD' } 4 { 'SSD' } 5 { 'SCM' } default { 'Unknown' } }
            size_gb = [math]::Round($disk.Size / 1GB, 2)
            health_status = "$($disk.HealthStatus)"
            operational_status = "$($disk.OperationalStatus)"
            reliability = $reliability
            reliability_motivo = $motivo
            power_on_hours = $powerOnHours
            temperature = $temperature
            reallocated_sectors = $reallocatedSectors
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
