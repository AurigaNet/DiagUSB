# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Copia un kit de DiagUSB ya armado (carpeta que contiene SHA256SUMS.txt, por
# ejemplo la que deja armar_kit.ps1) a un pendrive. No formatea, no particiona
# y no borra mas que la carpeta del kit en el destino. Verifica la integridad
# del origen antes de copiar y la del destino despues de copiar, contra
# SHA256SUMS.txt. Sin -Ejecutar solo simula (no toca el pendrive).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]$')]
    [string]$Unidad,
    [Parameter(Mandatory = $true)]
    [string]$Kit,
    [switch]$Ejecutar
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Leer-Manifiesto {
    param([Parameter(Mandatory = $true)][string]$Ruta,
          [Parameter(Mandatory = $true)][string]$Prefijo)
    $entradas = @()
    foreach ($linea in (Get-Content -LiteralPath $Ruta -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($linea)) { continue }
        $partes = $linea -split '\s+', 2
        if ($partes.Count -ne 2 -or $partes[0].Length -ne 64) {
            throw ("Linea invalida en SHA256SUMS.txt: '{0}'" -f $linea)
        }
        $rel = $partes[1]
        if ($rel.StartsWith($Prefijo)) { $rel = $rel.Substring($Prefijo.Length) }
        $entradas += [pscustomobject]@{
            Hash = $partes[0].ToLowerInvariant()
            Rel  = ($rel -replace '/', '\')
        }
    }
    return $entradas
}

function Verificar-Arbol {
    param([Parameter(Mandatory = $true)][string]$Raiz,
          [Parameter(Mandatory = $true)]$Entradas,
          [Parameter(Mandatory = $true)][string]$Etiqueta)
    $fallos = @()
    foreach ($e in $Entradas) {
        $f = Join-Path $Raiz $e.Rel
        if (-not (Test-Path -LiteralPath $f -PathType Leaf)) {
            $fallos += ("falta {0}" -f $e.Rel)
            continue
        }
        $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($h -ne $e.Hash) {
            $fallos += ("hash distinto en {0}" -f $e.Rel)
        }
    }
    if ($fallos.Count -gt 0) {
        $msg = ("Verificacion {0} fallida:" -f $Etiqueta) + "`n  - " + ($fallos -join "`n  - ")
        throw $msg
    }
}

$driveLetter = $Unidad.ToUpperInvariant()
$targetRoot = '{0}:\' -f $driveLetter
$systemDrive = $env:SystemDrive.TrimEnd('\').TrimEnd(':').ToUpperInvariant()

Write-Host ('armar_pendrive: modo {0}' -f $(if ($Ejecutar) { 'EJECUCIÓN REAL' } else { 'SIMULACIÓN' }))
Write-Host ("Unidad solicitada: {0}" -f $targetRoot)

if ($driveLetter -eq $systemDrive) {
    throw ("La unidad {0}: es la del sistema. Operación cancelada." -f $driveLetter)
}

# --- Carpeta del kit (raiz con SHA256SUMS.txt) ---
$Kit = [System.IO.Path]::GetFullPath($Kit)
if (-not (Test-Path -LiteralPath $Kit -PathType Container)) {
    throw ("No existe la carpeta del kit indicada en -Kit: {0}" -f $Kit)
}
if (-not (Test-Path -LiteralPath (Join-Path $Kit 'SHA256SUMS.txt') -PathType Leaf)) {
    $sub = Join-Path $Kit 'DiagUSB'
    if (Test-Path -LiteralPath (Join-Path $sub 'SHA256SUMS.txt') -PathType Leaf) {
        $Kit = $sub
    }
    else {
        throw ("La carpeta del kit no contiene SHA256SUMS.txt: {0}" -f $Kit)
    }
}
$kitName = Split-Path -Leaf $Kit
$entradas = Leer-Manifiesto -Ruta (Join-Path $Kit 'SHA256SUMS.txt') -Prefijo ($kitName + '/')
Write-Host ("Kit de origen : {0}" -f $Kit)
Write-Host ("Carpeta en destino: {0}\{1}" -f $targetRoot.TrimEnd('\'), $kitName)
Write-Host ("Archivos a copiar : {0}" -f $entradas.Count)

# --- Verificar integridad del origen ---
Verificar-Arbol -Raiz $Kit -Entradas $entradas -Etiqueta 'del origen'
Write-Host 'Origen verificado: todos los hashes coinciden con SHA256SUMS.txt.'

if (-not $Ejecutar) {
    Write-Host 'SIMULAR: no se formatea, no se particiona y no se borra ningún dispositivo.'
    Write-Host ("SIMULAR: se copiaría {0} a {1}{2}\." -f $Kit, $targetRoot, $kitName)
    Write-Host 'SIMULAR: después de copiar se verificarían los hashes contra SHA256SUMS.txt.'
    exit 0
}

if (-not (Test-Path -LiteralPath $targetRoot)) {
    throw ("La unidad {0} no existe o no está accesible." -f $targetRoot)
}

$disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}:'" -f $driveLetter)
if ($disk -and $disk.DriveType -ne 2) {
    Write-Warning ("La unidad {0}: no se reporta como extraíble (DriveType={1})." -f $driveLetter, $disk.DriveType)
}

$confirmation = Read-Host ("Escriba la letra de unidad {0} para confirmar la copia" -f $driveLetter)
if ($confirmation.ToUpperInvariant() -ne $driveLetter) {
    throw 'Confirmación inválida. Operación cancelada.'
}

$destKit = Join-Path $targetRoot $kitName
if (Test-Path -LiteralPath $destKit) {
    Write-Host ("Limpiando carpeta previa en el destino: {0}" -f $destKit)
    Remove-Item -LiteralPath $destKit -Recurse -Force
}
Copy-Item -LiteralPath $Kit -Destination $targetRoot -Recurse -Force
Write-Host ("Copiado en: {0}" -f $destKit)

# --- Verificar integridad del destino ---
Verificar-Arbol -Raiz $destKit -Entradas $entradas -Etiqueta 'del destino'
Write-Host ("Verificado: {0} archivos copiados con hashes correctos." -f $entradas.Count)
Write-Host 'Listo. Para usar, ejecute Iniciar_DiagUSB.cmd desde la carpeta del kit en el pendrive.'
