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

function Test-DiagUsbGatewayPing {
    param(
        [string]$Address,
        [int]$TimeoutMs = 800
    )

    $ping = $null
    try {
        $ping = [System.Net.NetworkInformation.Ping]::new()
        $respuesta = $ping.Send($Address, $TimeoutMs)
        if ($null -eq $respuesta) {
            return [ordered]@{ reachable = $false; rtt_ms = $null; status = 'sin_respuesta' }
        }
        $alcanzable = ($respuesta.Status -eq [System.Net.NetworkInformation.IPStatus]::Success)
        return [ordered]@{
            reachable = [bool]$alcanzable
            rtt_ms = $(if ($alcanzable) { [int]$respuesta.RoundtripTime } else { $null })
            status = [string]$respuesta.Status
        }
    }
    catch {
        return [ordered]@{ reachable = $false; rtt_ms = $null; status = 'error' }
    }
    finally {
        if ($null -ne $ping) { $ping.Dispose() }
    }
}

$result = New-DiagUsbCollectorResult -CollectorId 'gateway_routes' -TimeoutSeconds 15 -ScriptBlock {
    $rutas = @()
    foreach ($ruta in @(Get-NetRoute -ErrorAction SilentlyContinue |
            Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0', '::/0') } |
            Sort-Object -Property AddressFamily, RouteMetric)) {
        if ($null -eq $ruta) { continue }
        $salto = [string]$ruta.NextHop
        $info = [ordered]@{ reachable = $false; rtt_ms = $null; status = 'no_comprobado' }
        if ($salto -and $salto -notin @('0.0.0.0', '::')) {
            $info = Test-DiagUsbGatewayPing -Address $salto
        }
        $rutas += [ordered]@{
            destination_prefix = [string]$ruta.DestinationPrefix
            next_hop = $salto
            interface_index = [int]$ruta.InterfaceIndex
            interface_alias = [string]$ruta.InterfaceAlias
            route_metric = [int]$ruta.RouteMetric
            address_family = [string]$ruta.AddressFamily
            state = [string]$ruta.State
            reachable = [bool]$info.reachable
            rtt_ms = $info.rtt_ms
            ping_status = $info.status
        }
    }

    $v4 = @($rutas | Where-Object { $_.address_family -eq 'IPv4' -and $_.next_hop -notin @('', '0.0.0.0') })
    $primera = $null
    if ($v4.Count -gt 0) {
        $primera = @($v4 | Sort-Object -Property route_metric | Select-Object -First 1)[0]
    }
    $alcanzables = @($rutas | Where-Object { $_.reachable })

    return [ordered]@{
        routes = @($rutas)
        gateway_count = $rutas.Count
        reachable_count = $alcanzables.Count
        primary_gateway = $(if ($null -ne $primera) { $primera.next_hop } else { '' })
        primary_reachable = $(if ($null -ne $primera) { $primera.reachable } else { $false })
        primary_interface_index = $(if ($null -ne $primera) { $primera.interface_index } else { $null })
    }
}

Write-DiagUsbJson -InputObject $result
