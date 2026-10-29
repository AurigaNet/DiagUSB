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

$result = New-DiagUsbCollectorResult -CollectorId 'gateway_dns_servers' -TimeoutSeconds 15 -ScriptBlock {
    $interfaces = @()
    $todos = @()
    foreach ($item in @(Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
            Sort-Object -Property InterfaceIndex, AddressFamily)) {
        if ($null -eq $item) { continue }
        $direcciones = @($item.ServerAddresses | Where-Object { $_ })
        if ($direcciones.Count -eq 0) { continue }
        $interfaces += [ordered]@{
            interface_index = [int]$item.InterfaceIndex
            interface_alias = [string]$item.InterfaceAlias
            address_family = [string]$item.AddressFamily
            addresses = @($direcciones)
            count = $direcciones.Count
        }
        foreach ($direccion in $direcciones) { $todos += [string]$direccion }
    }

    $unicos = @($todos | Sort-Object -Unique)
    return [ordered]@{
        interfaces = @($interfaces)
        interface_count = $interfaces.Count
        total_servers = $todos.Count
        unique_servers = @($unicos)
        unique_count = $unicos.Count
    }
}

Write-DiagUsbJson -InputObject $result
