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

$result = New-DiagUsbCollectorResult -CollectorId 'input_devices' -TimeoutSeconds 20 -ScriptBlock {
    $teclados = @(Get-CimInstance -ClassName Win32_Keyboard -ErrorAction SilentlyContinue |
        Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                description = [string]$_.Description
                status = [string]$_.Status
                config_manager_error_code = [int]$_.ConfigManagerErrorCode
                pnp_device_id = [string]$_.PNPDeviceID
                layout = [string]$_.Layout
                function_keys = [int]$_.NumberOfFunctionKeys
            }
        })

    $punteros = @(Get-CimInstance -ClassName Win32_PointingDevice -ErrorAction SilentlyContinue |
        Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                description = [string]$_.Description
                status = [string]$_.Status
                config_manager_error_code = [int]$_.ConfigManagerErrorCode
                pnp_device_id = [string]$_.PNPDeviceID
                buttons = [int]$_.NumberOfButtons
                hardware_type = [string]$_.HardwareType
                pointing_type = [string]$_.PointingType
            }
        })

    $pnpTeclados = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter "PNPClass='Keyboard'" -ErrorAction SilentlyContinue |
        Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                status = [string]$_.Status
                config_manager_error_code = [int]$_.ConfigManagerErrorCode
                pnp_device_id = [string]$_.PNPDeviceID
                present = [bool]$_.Present
                service = [string]$_.Service
            }
        })

    $pnpPunteros = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter "PNPClass='Mouse'" -ErrorAction SilentlyContinue |
        Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                status = [string]$_.Status
                config_manager_error_code = [int]$_.ConfigManagerErrorCode
                pnp_device_id = [string]$_.PNPDeviceID
                present = [bool]$_.Present
                service = [string]$_.Service
            }
        })

    $totalTeclados = $teclados.Count
    if ($totalTeclados -eq 0) { $totalTeclados = $pnpTeclados.Count }
    $totalPunteros = $punteros.Count
    if ($totalPunteros -eq 0) { $totalPunteros = $pnpPunteros.Count }

    return [ordered]@{
        keyboards = @($teclados)
        pointing_devices = @($punteros)
        pnp_keyboards = @($pnpTeclados)
        pnp_pointing_devices = @($pnpPunteros)
        keyboard_count = $totalTeclados
        pointing_device_count = $totalPunteros
    }
}

Write-DiagUsbJson -InputObject $result
