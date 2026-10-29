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

$result = New-DiagUsbCollectorResult -CollectorId 'dns_servers' -ScriptBlock {
    Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses.Count -gt 0 } | ForEach-Object {
        $interface = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue
        [ordered]@{
            interface_alias = $_.InterfaceAlias
            interface_name = if ($interface) { $interface.Name } else { $null }
            dns_servers = $_.ServerAddresses
        }
    }
}

Write-DiagUsbJson -InputObject $result
