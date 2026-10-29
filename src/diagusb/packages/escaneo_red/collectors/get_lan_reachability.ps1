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

function Test-DiagUsbPing {
    param(
        [string]$Address,
        [int]$TimeoutMs = 600
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

$result = New-DiagUsbCollectorResult -CollectorId 'lan_reachability' -TimeoutSeconds 20 -ScriptBlock {
    $ruta = @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object -Property RouteMetric | Select-Object -First 1)
    if ($ruta.Count -eq 0) {
        throw 'DIAGUSB_NOT_AVAILABLE: no hay una ruta predeterminada IPv4.'
    }

    $puerta = [string]$ruta[0].NextHop
    $indice = [int]$ruta[0].InterfaceIndex
    if (-not $puerta -or $puerta -in @('0.0.0.0', '::')) {
        throw 'DIAGUSB_NOT_AVAILABLE: la ruta predeterminada no tiene una puerta de enlace utilizable.'
    }
    $puertaInfo = Test-DiagUsbPing -Address $puerta

    $vecinos = @(Get-NetNeighbor -InterfaceIndex $indice -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.State -in @('Reachable', 'Stale', 'Delay', 'Probe', 'Permanent') -and
            $_.IPAddress -ne $puerta -and
            $_.IPAddress -notlike '224.*' -and
            $_.IPAddress -notlike '239.*' -and
            $_.IPAddress -ne '255.255.255.255' -and
            $_.IPAddress -notlike '169.254.*'
        } |
        Sort-Object -Property @{ Expression = { if ($_.State -eq 'Reachable') { 0 } else { 1 } } }, IPAddress |
        Select-Object -First 8)

    $comprobados = @()
    foreach ($vecino in $vecinos) {
        if ($null -eq $vecino) { continue }
        $ip = [string]$vecino.IPAddress
        $info = Test-DiagUsbPing -Address $ip
        $comprobados += [ordered]@{
            ip = $ip
            mac = [string]$vecino.LinkLayerAddress
            reachable = [bool]$info.reachable
            rtt_ms = $info.rtt_ms
            status = $info.status
        }
    }

    $alcanzables = @($comprobados | Where-Object { $_.reachable })

    return [ordered]@{
        gateway_ip = $puerta
        interface_index = $indice
        gateway_reachable = [bool]$puertaInfo.reachable
        gateway_rtt_ms = $puertaInfo.rtt_ms
        gateway_status = $puertaInfo.status
        checked_count = $comprobados.Count
        reachable_count = $alcanzables.Count
        checked_hosts = @($comprobados)
    }
}

Write-DiagUsbJson -InputObject $result
