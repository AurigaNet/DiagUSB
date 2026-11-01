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

$result = New-DiagUsbCollectorResult -CollectorId 'capture_drivers' -TimeoutSeconds 20 -ScriptBlock {
    $controladores = @()
    foreach ($driver in @(Get-CimInstance -ClassName Win32_SystemDriver -ErrorAction SilentlyContinue |
            Where-Object { [string]$_.Name -match '(?i)^(npcap|npcap_wifi|npf|pcap)$' })) {
        if ($null -eq $driver) { continue }
        $controladores += [ordered]@{
            name = [string]$driver.Name
            display_name = [string]$driver.DisplayName
            state = [string]$driver.State
            start_mode = [string]$driver.StartMode
            path_name = [string]$driver.PathName
        }
    }

    $dispositivos = @()
    $pnp = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter "Name LIKE '%Npcap%' OR Name LIKE '%WinPcap%'" -ErrorAction SilentlyContinue)
    foreach ($dispositivo in $pnp) {
        if ($null -eq $dispositivo) { continue }
        $dispositivos += [ordered]@{
            name = [string]$dispositivo.Name
            status = [string]$dispositivo.Status
            config_manager_error_code = [int]$dispositivo.ConfigManagerErrorCode
            pnp_device_id = [string]$dispositivo.PNPDeviceID
        }
    }

    $enEjecucion = @($controladores | Where-Object { $_.state -eq 'Running' })
    return [ordered]@{
        drivers = @($controladores)
        devices = @($dispositivos)
        driver_count = $controladores.Count
        device_count = $dispositivos.Count
        running_count = $enEjecucion.Count
        present = [bool](($controladores.Count + $dispositivos.Count) -gt 0)
    }
}

Write-DiagUsbJson -InputObject $result
