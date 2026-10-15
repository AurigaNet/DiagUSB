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