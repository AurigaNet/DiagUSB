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

$result = New-DiagUsbCollectorResult -CollectorId 'critical_services' -ScriptBlock {
    $criticalServiceNames = @(
        'Spooler',
        'Dnscache',
        'Dhcp',
        'EventLog',
        'LanmanServer',
        'LanmanWorkstation',
        'Netlogon',
        'W32Time',
        'WindowsUpdate'
    )

    $alerts = @()
    $servicesData = @()

    foreach ($svcName in $criticalServiceNames) {
        $service = Get-CimInstance -ClassName Win32_Service -Filter ("Name='{0}'" -f $svcName)

        if ($null -eq $service) {
            continue
        }

        $serviceInfo = [ordered]@{
            name = $service.Name
            display_name = $service.DisplayName
            state = $service.State
            start_mode = $service.StartMode
            process_id = $service.ProcessId
        }

        $servicesData += $serviceInfo

        # Alertar si el servicio esta detenido y deberia estar corriendo
        $shouldBeRunning = $service.StartMode -in @('Auto', 'Manual')
        if ($service.State -ne 'Running' -and $shouldBeRunning) {
            $alerts += [ordered]@{
                service_name = $service.Name
                display_name = $service.DisplayName
                current_state = $service.State
                start_mode = $service.StartMode
                message = "El servicio critico '{0}' esta detenido y deveria estar en ejecucion" -f $service.DisplayName
            }
        }
    }

    [ordered]@{
        critical_services = $servicesData
        alerts = $alerts
        total_critical = $servicesData.Count
        total_alerts = $alerts.Count
    }
}

Write-DiagUsbJson -InputObject $result
