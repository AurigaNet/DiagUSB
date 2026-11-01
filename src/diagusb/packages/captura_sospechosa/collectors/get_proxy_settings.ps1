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

function Remove-DiagUsbProxyCredentials {
    param([string]$Value)

    if (-not $Value) { return '' }
    $limpio = [regex]::Replace($Value, '(?i)(//)[^/@\s]+@', '$1[credenciales]@')
    $limpio = [regex]::Replace($limpio, '(?i)^([^/@\s:]+):([^/@\s]+)@', '[credenciales]@')
    return $limpio
}

$result = New-DiagUsbCollectorResult -CollectorId 'proxy_settings' -TimeoutSeconds 15 -ScriptBlock {
    $clave = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    $valores = Get-ItemProperty -Path $clave -ErrorAction SilentlyContinue

    $habilitado = $false
    $servidor = ''
    $autoConfig = ''
    $autoDetectar = $false
    if ($null -ne $valores) {
        $habilitado = ([int](Get-DiagUsbPropertyValue -InputObject $valores -PropertyName 'ProxyEnable') -ne 0)
        $servidor = [string](Get-DiagUsbPropertyValue -InputObject $valores -PropertyName 'ProxyServer')
        $autoConfig = [string](Get-DiagUsbPropertyValue -InputObject $valores -PropertyName 'AutoConfigURL')
        $autoDetectar = ([int](Get-DiagUsbPropertyValue -InputObject $valores -PropertyName 'AutoDetect') -ne 0)
    }

    $servidor = Remove-DiagUsbProxyCredentials -Value $servidor
    $autoConfig = Remove-DiagUsbProxyCredentials -Value $autoConfig

    $entorno = @()
    foreach ($nombre in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')) {
        $valor = [string][Environment]::GetEnvironmentVariable($nombre)
        if ($valor) {
            $entorno += [ordered]@{
                name = $nombre
                value = Remove-DiagUsbProxyCredentials -Value $valor
            }
        }
    }

    # NO_PROXY no es un proxy: es una lista de exclusiones. Se informa aparte
    # para no contarla como configuracion que desvia el trafico.
    $noProxy = [string][Environment]::GetEnvironmentVariable('NO_PROXY')

    $loopback = $false
    if ($servidor -match '(?i)(^|[=;\s])(127\.0\.0\.1|localhost)(:|\b)') {
        $loopback = $true
    }

    return [ordered]@{
        user_proxy_enabled = [bool]$habilitado
        user_proxy_server = $servidor
        auto_config_url = $autoConfig
        auto_detect = [bool]$autoDetectar
        loopback_proxy = [bool]$loopback
        manual_remote_proxy = [bool]($habilitado -and $servidor -and -not $loopback)
        environment_proxy = @($entorno)
        environment_proxy_count = $entorno.Count
        no_proxy = $noProxy
    }
}

Write-DiagUsbJson -InputObject $result
