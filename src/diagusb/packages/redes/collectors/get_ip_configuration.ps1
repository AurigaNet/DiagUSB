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

$result = New-DiagUsbCollectorResult -CollectorId 'ip_configuration' -ScriptBlock {
    Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | ForEach-Object {
        $ipv4Address = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'IPv4Address'
        $gateway = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'IPv4DefaultGateway'
        $dnsServer = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DNSServer'

        $dhcpEnabled = $null
        $ipInterface = Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        if ($null -ne $ipInterface) {
            $dhcpEnabled = "$($ipInterface.Dhcp)" -eq 'Enabled'
        }

        [ordered]@{
            interface_alias = $_.InterfaceAlias
            ipv4_address = $(if ($ipv4Address) { $ipv4Address.IPAddress } else { $null })
            ipv4_prefix = $(if ($ipv4Address) { $ipv4Address.PrefixLength } else { $null })
            ipv4_gateway = $(if ($gateway) { $gateway.NextHop } else { $null })
            dhcp_enabled = $dhcpEnabled
            dns_servers = $(if ($dnsServer) { $dnsServer.ServerAddresses } else { $null })
            interface_index = $_.InterfaceIndex
        }
    }
}

Write-DiagUsbJson -InputObject $result
