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

$result = New-DiagUsbCollectorResult -CollectorId 'network_drivers' -ScriptBlock {
    Get-CimInstance -ClassName Win32_PnPSignedDriver | Where-Object { $_.DeviceClass -match 'Net|Adapter|Ethernet|WiFi|WLAN' } | Sort-Object -Property DeviceName | ForEach-Object {
        $driverDate = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DriverDate'
        $isSigned = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'IsSigned'
        $signer = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'Signer'

        [ordered]@{
            device_name = $_.DeviceName
            driver_version = $_.DriverVersion
            driver_date = Convert-DiagUsbDateTime -Value $driverDate
            manufacturer = $_.Manufacturer
            device_class = $_.DeviceClass
            device_id = $_.DeviceID
            inf_name = $_.InfName
            is_signed = $isSigned
            signer = $signer
        }
    }
}

Write-DiagUsbJson -InputObject $result
