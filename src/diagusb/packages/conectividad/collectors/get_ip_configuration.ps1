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
    # DHCP server y MAC del gateway (tabla ARP) por adaptador.
    $configPorIndice = @{}
    foreach ($conf in @(Get-CimInstance -ClassName Win32_NetworkAdapterConfiguration -ErrorAction SilentlyContinue)) {
        $configPorIndice[[int]$conf.InterfaceIndex] = $conf
    }

    Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | ForEach-Object {
        $ipv4Address = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'IPv4Address'
        $gateway = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'IPv4DefaultGateway'
        $dnsServer = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DNSServer'

        $ipInterface = Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        $dhcpEnabled = $null
        $dhcpServer = $null
        if ($null -ne $ipInterface) {
            $dhcpEnabled = "$($ipInterface.Dhcp)" -eq 'Enabled'
        }
        $conf = $configPorIndice[[int]$_.InterfaceIndex]
        if ($null -ne $conf -and $dhcpEnabled) {
            $dhcpServer = [string]$conf.DHCPServer
            if (-not $dhcpServer) { $dhcpServer = $null }
        }

        $gatewayMac = $null
        if ($gateway) {
            $gatewayMac = Get-DiagUsbGatewayMac `
                -GatewayIp ([string]$gateway.NextHop) `
                -InterfaceIndex ([string]$_.InterfaceIndex)
        }

        [ordered]@{
            interface_alias = $_.InterfaceAlias
            ipv4_address = $(if ($ipv4Address) { $ipv4Address.IPAddress } else { $null })
            ipv4_prefix = $(if ($ipv4Address) { $ipv4Address.PrefixLength } else { $null })
            ipv4_gateway = $(if ($gateway) { $gateway.NextHop } else { $null })
            gateway_mac = $gatewayMac
            dhcp_enabled = $dhcpEnabled
            dhcp_server = $dhcpServer
            dns_servers = $(if ($dnsServer) { $dnsServer.ServerAddresses } else { $null })
            interface_index = $_.InterfaceIndex
        }
    }
}

Write-DiagUsbJson -InputObject $result
