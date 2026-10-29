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

function Get-DiagUsbProcessInfo {
    param(
        [hashtable]$Cache,
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return [ordered]@{ name = ''; path = ''; company = '' }
    }
    if ($Cache.ContainsKey($ProcessId)) {
        return $Cache[$ProcessId]
    }

    $info = [ordered]@{ name = ''; path = ''; company = '' }
    $proceso = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -ne $proceso) {
        $info.name = [string]$proceso.ProcessName
        try {
            $ruta = [string]$proceso.Path
            if ($ruta) {
                $info.path = $ruta
                $version = $proceso.MainModule.FileVersionInfo
                if ($null -ne $version) {
                    $info.company = [string]$version.CompanyName
                }
            }
        }
        catch {
            $info.path = ''
        }
    }
    $Cache[$ProcessId] = $info
    return $info
}

function Test-DiagUsbSystemPath {
    param([string]$Path)

    if (-not $Path) { return $false }
    $raiz = [string]$env:SystemRoot
    if (-not $raiz) { return $false }
    return $Path.StartsWith($raiz, [System.StringComparison]::OrdinalIgnoreCase)
}

$result = New-DiagUsbCollectorResult -CollectorId 'listening_ports' -TimeoutSeconds 20 -ScriptBlock {
    $cache = @{}
    $tcp = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Sort-Object -Property LocalPort, LocalAddress)
    $udp = @(Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Sort-Object -Property LocalPort, LocalAddress)

    $tcpSalida = @()
    foreach ($conexion in $tcp) {
        if ($null -eq $conexion) { continue }
        $direccion = [string]$conexion.LocalAddress
        $procesoId = [int]$conexion.OwningProcess
        $proceso = Get-DiagUsbProcessInfo -Cache $cache -ProcessId $procesoId
        $comodin = $direccion -in @('0.0.0.0', '::', '[::]')
        $loopback = ($direccion -like '127.*') -or ($direccion -eq '::1')
        $tcpSalida += [ordered]@{
            local_address = $direccion
            local_port = [int]$conexion.LocalPort
            protocol = 'tcp'
            state = [string]$conexion.State
            owning_process = $procesoId
            process_name = $proceso.name
            process_path = $proceso.path
            process_company = $proceso.company
            wildcard = [bool]$comodin
            loopback = [bool]$loopback
            exposed = [bool]($comodin -and -not $loopback)
            system_process = [bool](Test-DiagUsbSystemPath -Path $proceso.path)
        }
    }

    $udpSalida = @()
    foreach ($extremo in $udp) {
        if ($null -eq $extremo) { continue }
        $direccion = [string]$extremo.LocalAddress
        $procesoId = [int]$extremo.OwningProcess
        $proceso = Get-DiagUsbProcessInfo -Cache $cache -ProcessId $procesoId
        $comodin = $direccion -in @('0.0.0.0', '::', '[::]')
        $loopback = ($direccion -like '127.*') -or ($direccion -eq '::1')
        $udpSalida += [ordered]@{
            local_address = $direccion
            local_port = [int]$extremo.LocalPort
            protocol = 'udp'
            state = ''
            owning_process = $procesoId
            process_name = $proceso.name
            process_path = $proceso.path
            process_company = $proceso.company
            wildcard = [bool]$comodin
            loopback = [bool]$loopback
            exposed = [bool]($comodin -and -not $loopback)
            system_process = [bool](Test-DiagUsbSystemPath -Path $proceso.path)
        }
    }

    $expuestosTcp = @($tcpSalida | Where-Object { $_.exposed })
    $expuestosUdp = @($udpSalida | Where-Object { $_.exposed })
    $terceros = @($tcpSalida | Where-Object {
        $_.exposed -and $_.process_path -and -not $_.system_process
    })

    return [ordered]@{
        tcp_listeners = @($tcpSalida)
        udp_endpoints = @($udpSalida)
        tcp_count = $tcpSalida.Count
        udp_count = $udpSalida.Count
        exposed_tcp_count = $expuestosTcp.Count
        exposed_udp_count = $expuestosUdp.Count
        third_party_exposed = @($terceros)
        third_party_exposed_count = $terceros.Count
    }
}

Write-DiagUsbJson -InputObject $result
