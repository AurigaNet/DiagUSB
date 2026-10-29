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

$result = New-DiagUsbCollectorResult -CollectorId 'dns_resolution' -TimeoutSeconds 15 -ScriptBlock {
    $nombre = [string]$env:USERDNSDOMAIN
    if (-not $nombre) { $nombre = 'www.msftconnecttest.com' }

    $cronometro = [System.Diagnostics.Stopwatch]::StartNew()
    $exito = $false
    $direcciones = @()
    $errorTexto = ''
    $agotado = $false
    $tarea = $null

    try {
        $tarea = [System.Net.Dns]::BeginGetHostAddresses($nombre, $null, $null)
        if (-not $tarea.AsyncWaitHandle.WaitOne(4000, $false)) {
            $agotado = $true
            $errorTexto = 'tiempo de espera agotado'
        }
        else {
            try {
                $resultado = [System.Net.Dns]::EndGetHostAddresses($tarea)
                $direcciones = @($resultado | ForEach-Object { $_.IPAddressToString })
                $exito = ($direcciones.Count -gt 0)
                if (-not $exito) { $errorTexto = 'sin direcciones' }
            }
            catch {
                $errorTexto = $_.Exception.Message
            }
        }
    }
    catch {
        $errorTexto = $_.Exception.Message
    }
    finally {
        $cronometro.Stop()
        if ($null -ne $tarea) {
            try { $tarea.AsyncWaitHandle.Close() } catch { }
        }
    }

    return [ordered]@{
        query_name = $nombre
        success = [bool]$exito
        elapsed_ms = [int]$cronometro.ElapsedMilliseconds
        timed_out = [bool]$agotado
        addresses = @($direcciones)
        address_count = $direcciones.Count
        error = $errorTexto
        sampled_at_utc = Get-DiagUsbTimestampUtc
    }
}

Write-DiagUsbJson -InputObject $result
