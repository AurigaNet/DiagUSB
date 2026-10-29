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

$result = New-DiagUsbCollectorResult -CollectorId 'hosts_entries' -TimeoutSeconds 15 -ScriptBlock {
    $ruta = Join-Path ([string]$env:SystemRoot) 'System32\drivers\etc\hosts'
    if (-not (Test-Path -LiteralPath $ruta)) {
        throw 'DIAGUSB_NOT_AVAILABLE: no se encontro el archivo hosts del sistema.'
    }

    $entradas = @()
    foreach ($linea in @(Get-Content -LiteralPath $ruta -Encoding UTF8 -ErrorAction Stop)) {
        $sinComentario = ([string]$linea).Split('#')[0].Trim()
        if (-not $sinComentario) { continue }
        $partes = @($sinComentario -split '\s+' | Where-Object { $_ })
        if ($partes.Count -lt 2) { continue }

        $ip = $null
        if (-not [System.Net.IPAddress]::TryParse($partes[0], [ref]$ip)) { continue }
        $nombres = @($partes[1..($partes.Count - 1)])
        $entradas += [ordered]@{
            ip = $partes[0]
            hostnames = @($nombres)
            loopback = [bool]([System.Net.IPAddress]::IsLoopback($ip))
        }
    }

    $noLoopback = @($entradas | Where-Object { -not $_.loopback })

    return [ordered]@{
        path = $ruta
        entries = @($entradas)
        active_count = $entradas.Count
        non_loopback_count = $noLoopback.Count
        non_loopback = @($noLoopback)
    }
}

Write-DiagUsbJson -InputObject $result
