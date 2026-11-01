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

$result = New-DiagUsbCollectorResult -CollectorId 'printer_drivers' -ScriptBlock {
    $spooler = Get-Service -Name 'Spooler' -ErrorAction SilentlyContinue
    if ($null -eq $spooler -or $spooler.Status -ne 'Running') {
        throw 'DIAGUSB_NOT_AVAILABLE: el servicio Spooler no esta en ejecucion; no se pueden enumerar controladores de impresora.'
    }

    Get-CimInstance -ClassName Win32_PrinterDriver | Sort-Object -Property Name | ForEach-Object {
        [ordered]@{
            name = $_.Name
            driver_path = $_.DriverPath
            config_file = $_.ConfigFile
            data_file = $_.DataFile
            help_file = $_.HelpFile
            inf_name = $_.InfName
            monitor_name = $_.MonitorName
            supported_platform = $_.SupportedPlatform
            version = $_.Version
            major_version = $(Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'MajorVersion')
            driver_date_utc = Convert-DiagUsbDateTime -Value (Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DriverDate')
        }
    }
}

Write-DiagUsbJson -InputObject $result