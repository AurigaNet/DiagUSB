# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Verifica, en modo solo lectura, el SHA-256 de las imagenes externas del
# pendrive de arranque contra tools\tools.manifest.json. No descarga,
# formatea, particiona ni escribe nada: solo lee los archivos indicados y
# Get-FileHash. Si falta un archivo o el hash no coincide, termina con
# codigo 1. Las herramientas excluidas se muestran con su motivo.

[CmdletBinding()]
param(
    [string]$Carpeta,
    [string]$Manifiesto
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $Carpeta) {
    $Carpeta = Join-Path $scriptDir '..\tools\downloads'
}
if (-not $Manifiesto) {
    $Manifiesto = Join-Path $scriptDir '..\tools\tools.manifest.json'
}

function Get-Campo {
    param(
        [Parameter(Mandatory = $true)]$Objeto,
        [Parameter(Mandatory = $true)][string]$Nombre
    )
    $propiedad = $Objeto.PSObject.Properties[$Nombre]
    if (-not $propiedad -or $null -eq $propiedad.Value) {
        return ''
    }
    return [string]$propiedad.Value
}

function Test-DominioOficial {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Dominio
    )
    try {
        $uri = [Uri]$Url
    }
    catch {
        return $false
    }
    if ($uri.Scheme -notin @('http', 'https')) {
        return $false
    }
    $hostName = $uri.DnsSafeHost.ToLowerInvariant()
    $dominioNormal = $Dominio.ToLowerInvariant().TrimStart('.')
    if (-not $hostName -or -not $dominioNormal) {
        return $false
    }
    return ($hostName -eq $dominioNormal) -or $hostName.EndsWith('.' + $dominioNormal)
}

if (-not (Test-Path -LiteralPath $Manifiesto -PathType Leaf)) {
    throw "No existe el manifiesto: $Manifiesto"
}
$Carpeta = [System.IO.Path]::GetFullPath($Carpeta)
if (-not (Test-Path -LiteralPath $Carpeta -PathType Container)) {
    throw "No existe la carpeta con las imagenes descargadas: $Carpeta"
}

$datos = Get-Content -LiteralPath $Manifiesto -Raw | ConvertFrom-Json
if (-not $datos.tools) {
    throw 'El manifiesto no contiene herramientas.'
}

Write-Host 'verificar_live_usb: modo solo lectura (no descarga ni escribe)'
Write-Host ("Manifiesto: {0}" -f $Manifiesto)
Write-Host ("Carpeta   : {0}" -f $Carpeta)
Write-Host ''

$verificadas = 0
$excluidas = 0
$fallos = 0

foreach ($tool in @($datos.tools)) {
    $nombre = Get-Campo -Objeto $tool -Nombre 'name'
    if (-not $nombre) {
        $nombre = Get-Campo -Objeto $tool -Nombre 'nombre'
    }
    $estado = (Get-Campo -Objeto $tool -Nombre 'estado').ToLowerInvariant()

    if ($estado -eq 'excluido') {
        $excluidas++
        $motivo = Get-Campo -Objeto $tool -Nombre 'motivo'
        if (-not $motivo) { $motivo = 'excluida sin motivo documentado' }
        Write-Host ("[EXCLUIDA] {0}: {1}" -f $nombre, $motivo)
        continue
    }

    if ($estado -ne 'verificado') {
        Write-Host ("[PENDIENTE] {0}: estado '{1}', no se verifica." -f $nombre, $estado)
        continue
    }

    $verificadas++
    $problemas = @()
    foreach ($campo in @('official_domain', 'url', 'version', 'sha256', 'license', 'file')) {
        if (-not (Get-Campo -Objeto $tool -Nombre $campo)) {
            $problemas += ("falta {0}" -f $campo)
        }
    }

    $sha = (Get-Campo -Objeto $tool -Nombre 'sha256').ToLowerInvariant()
    if ($sha -and $sha -notmatch '^[0-9a-f]{64}$') {
        $problemas += 'SHA-256 con formato invalido'
    }

    $url = Get-Campo -Objeto $tool -Nombre 'url'
    $dominio = Get-Campo -Objeto $tool -Nombre 'official_domain'
    if ($url -and $dominio -and -not (Test-DominioOficial -Url $url -Dominio $dominio)) {
        $problemas += 'la URL no pertenece al dominio oficial'
    }

    if ($problemas.Count -gt 0) {
        $fallos++
        Write-Host ("[ERROR] {0}: {1}" -f $nombre, ($problemas -join '; '))
        continue
    }

    $archivo = Get-Campo -Objeto $tool -Nombre 'file'
    $ruta = Join-Path $Carpeta $archivo
    if (-not (Test-Path -LiteralPath $ruta -PathType Leaf)) {
        $fallos++
        Write-Host ("[FALTA] {0}: {1}" -f $nombre, $ruta)
        continue
    }

    $obtenido = (Get-FileHash -LiteralPath $ruta -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($obtenido -ne $sha) {
        $fallos++
        Write-Host ("[HASH NO COINCIDE] {0}: {1}" -f $nombre, $archivo)
        Write-Host ("  esperado: {0}" -f $sha)
        Write-Host ("  obtenido: {0}" -f $obtenido)
        continue
    }

    Write-Host ("[OK] {0} {1}: {2}" -f $nombre, (Get-Campo -Objeto $tool -Nombre 'version'), $archivo)
}

Write-Host ''
if ($verificadas -eq 0) {
    Write-Host 'No hay imagenes verificadas en el manifiesto.'
    exit 0
}
if ($fallos -gt 0) {
    Write-Host ("Verificacion fallida: {0} de {1} imagen(es) con problemas. Excluidas: {2}." -f $fallos, $verificadas, $excluidas)
    exit 1
}

Write-Host ("Verificacion completa: {0} imagen(es) coinciden con el SHA-256 oficial. Excluidas: {1}." -f $verificadas, $excluidas)
exit 0
