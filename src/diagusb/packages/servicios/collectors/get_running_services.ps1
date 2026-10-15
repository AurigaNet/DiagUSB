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

$result = New-DiagUsbCollectorResult -CollectorId 'running_services' -ScriptBlock {
    $runningServices = Get-Service | Where-Object { $_.Status -eq 'Running' } | Sort-Object -Property Name

    $servicesData = @()
    foreach ($svc in $runningServices) {
        $servicesData += [ordered]@{
            name = $svc.Name
            display_name = $svc.DisplayName
            service_type = [string]$svc.ServiceType
            start_mode = [string]$svc.StartType
            status = [string]$svc.Status
        }
    }

    [ordered]@{
        running_services = $servicesData
        total_running = $servicesData.Count
    }
}

Write-DiagUsbJson -InputObject $result
