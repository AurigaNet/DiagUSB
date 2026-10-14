# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

$result = New-DiagUsbCollectorResult -CollectorId 'spooler_service' -ScriptBlock {
    $serviceRecord = Get-DiagUsbServiceRecord -Name 'Spooler'
    $service = Get-Service -Name 'Spooler' -ErrorAction Stop

    [ordered]@{
        spooler = $serviceRecord
        required_services = @($service.ServicesDependedOn | Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = $_.Name
                display_name = $_.DisplayName
                status = [string]$_.Status
                service_type = [string]$_.ServiceType
            }
        })
        dependent_services = @($service.DependentServices | Sort-Object -Property Name | ForEach-Object {
            [ordered]@{
                name = $_.Name
                display_name = $_.DisplayName
                status = [string]$_.Status
                service_type = [string]$_.ServiceType
            }
        })
    }
}

Write-DiagUsbJson -InputObject $result