# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

$result = New-DiagUsbCollectorResult -CollectorId 'printer_drivers' -ScriptBlock {
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