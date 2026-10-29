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

$result = New-DiagUsbCollectorResult -CollectorId 'network_neighbors' -TimeoutSeconds 15 -ScriptBlock {
    $rutas = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)
    $puertas = @($rutas | ForEach-Object { [string]$_.NextHop } | Where-Object { $_ })

    $vecinos = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Sort-Object -Property IPAddress)

    $salida = @()
    foreach ($vecino in $vecinos) {
        if ($null -eq $vecino) { continue }
        $ip = [string]$vecino.IPAddress
        if (-not $ip) { continue }
        $octeto = 0
        try { $octeto = [int]($ip.Split('.')[0]) } catch { $octeto = 0 }
        $multicast = ($octeto -ge 224 -and $octeto -le 239) -or ($ip -eq '255.255.255.255')
        $enlaceLocal = $ip -like '169.254.*'
        $salida += [ordered]@{
            ip = $ip
            mac = [string]$vecino.LinkLayerAddress
            state = [string]$vecino.State
            interface_index = [int]$vecino.InterfaceIndex
            interface_alias = [string]$vecino.InterfaceAlias
            is_gateway = [bool]($ip -in $puertas)
            multicast = [bool]$multicast
            link_local = [bool]$enlaceLocal
        }
    }

    $visibles = @($salida | Where-Object {
        $_.state -in @('Reachable', 'Stale', 'Delay', 'Probe', 'Permanent') -and
        -not $_.multicast -and -not $_.link_local
    })
    $otros = @($visibles | Where-Object { -not $_.is_gateway })

    return [ordered]@{
        gateway_ips = @($puertas)
        neighbors = @($salida)
        neighbor_count = $salida.Count
        visible_count = $visibles.Count
        other_host_count = $otros.Count
    }
}

Write-DiagUsbJson -InputObject $result
