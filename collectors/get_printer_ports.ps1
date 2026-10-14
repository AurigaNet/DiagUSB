# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot '_common.ps1')

$result = New-DiagUsbCollectorResult -CollectorId 'printer_ports' -ScriptBlock {
    Get-CimInstance -ClassName Win32_TCPIPPrinterPort | Sort-Object -Property Name | ForEach-Object {
        [ordered]@{
            name = $_.Name
            host_address = $_.HostAddress
            port_number = $_.PortNumber
            protocol = $_.Protocol
            queue = $_.Queue
            snmp_enabled = [bool]$_.SNMPEnabled
            snmp_community = $_.SNMPCommunity
            snmp_dev_index = $_.SNMPDevIndex
            byte_count = [bool]$_.ByteCount
            double_spool = [bool]$_.DoubleSpool
        }
    }
}

Write-DiagUsbJson -InputObject $result