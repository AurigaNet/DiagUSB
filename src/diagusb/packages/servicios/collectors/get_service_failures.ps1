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

$result = New-DiagUsbCollectorResult -CollectorId 'service_failures' -ScriptBlock {
    # Servicios configurados en Automatico que NO estan Running (fallo real).
    # Los servicios en Manual/Desactivado detenidos son comportamiento normal.
    $failedServices = Get-CimInstance Win32_Service | Where-Object {
        $_.StartMode -eq 'Auto' -and $_.State -ne 'Running'
    } | Sort-Object -Property Name

    $failuresData = @()
    foreach ($svc in $failedServices) {
        # Los servicios por usuario (Type 0x40, p. ej. BluetoothUserService) y
        # los de inicio por disparador estan detenidos por diseno hasta que
        # ocurre el evento que los inicia. No son fallas.
        $clave = "HKLM:\SYSTEM\CurrentControlSet\Services\$($svc.Name)"
        $config = $null
        try {
            $config = Get-ItemProperty -LiteralPath $clave -ErrorAction Stop
        }
        catch {
            $config = $null
        }

        $tipo = 0
        if ($null -ne $config -and $null -ne $config.Type) {
            try { $tipo = [int]$config.Type } catch { $tipo = 0 }
        }
        $esServicioUsuario = (($tipo -band 0x40) -ne 0)
        $tieneDisparador = $false
        try {
            $tieneDisparador = Test-Path -LiteralPath (Join-Path $clave 'TriggerInfo')
        }
        catch {
            $tieneDisparador = $false
        }
        if ($esServicioUsuario -or $tieneDisparador) { continue }

        $failuresData += [ordered]@{
            name = $svc.Name
            display_name = $svc.DisplayName
            state = $svc.State
            start_mode = $svc.StartMode
            exit_code = $svc.ExitCode
            process_id = $svc.ProcessId
        }
    }

    # Buscar eventos recientes de fallo de servicios en Application log
    $serviceEventFailures = @()
    try {
        $events = Get-WinEvent -FilterHashtable @{
            LogName = 'Application'
            Level = 1 # Error
            ProviderName = 'Service Control Manager'
            StartTime = (Get-Date).AddDays(-7)
        } -MaxEvents 50 -ErrorAction SilentlyContinue

        foreach ($event in $events) {
            if ($event.Message -match 'service' -or $event.ProviderName -eq 'Service Control Manager') {
                $serviceEventFailures += [ordered]@{
                    event_id = $event.Id
                    time_created = $event.TimeCreated.ToUniversalTime().ToString('o')
                    message = $event.Message
                    provider = $event.ProviderName
                }
            }
        }
    }
    catch {
        # Si no hay permisos para leer eventos, continuar sin ellos
    }

    [ordered]@{
        failed_services = $failuresData
        service_events = $serviceEventFailures
        total_failed = $failuresData.Count
        total_events = $serviceEventFailures.Count
    }
}

Write-DiagUsbJson -InputObject $result
