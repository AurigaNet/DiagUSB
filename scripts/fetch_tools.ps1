# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

[CmdletBinding()]
param(
    [string]$ManifestPath,
    [string]$DownloadDir,
    [switch]$Ejecutar
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ManifestPath) {
    $ManifestPath = Join-Path $PSScriptRoot '..\tools\tools.manifest.json'
}

if (-not $DownloadDir) {
    $DownloadDir = Join-Path $PSScriptRoot '..\tools\downloads'
}

function Test-OfficialUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$OfficialDomain
    )

    $uri = [Uri]$Url
    $hostName = $uri.DnsSafeHost.ToLowerInvariant()
    $domain = $OfficialDomain.ToLowerInvariant()

    return $hostName -eq $domain -or $hostName.EndsWith('.' + $domain)
}

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "No se encontró el manifiesto: $ManifestPath"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if (-not $manifest.tools) {
    throw 'El manifiesto no contiene herramientas.'
}

$modo = if ($Ejecutar) { 'EJECUCIÓN REAL' } else { 'SIMULACIÓN' }
Write-Host "fetch_tools: $modo"
Write-Host "Manifiesto: $ManifestPath"
Write-Host "Destino: $DownloadDir"

foreach ($tool in $manifest.tools) {
    Write-Host ''
    Write-Host ("[{0}] estado={1}" -f $tool.name, $tool.estado)

    if ($tool.estado -eq 'excluido') {
        $motivo = if ($tool.motivo) { $tool.motivo } else { 'sin motivo documentado' }
        Write-Host ("  EXCLUIDA: {0}" -f $motivo)
        continue
    }

    if ($tool.estado -ne 'verificado') {
        Write-Host ("  RECHAZADO: estado '{0}' distinto de 'verificado'. Falla cerrado." -f $tool.estado)
        continue
    }

    if (-not $tool.url) {
        Write-Host '  RECHAZADO: URL pendiente o nula. Falla cerrado.'
        continue
    }

    if (-not $tool.sha256) {
        Write-Host '  RECHAZADO: SHA-256 pendiente o nulo. Falla cerrado.'
        continue
    }

    if (-not $tool.official_domain) {
        Write-Host '  RECHAZADO: dominio oficial pendiente o nulo. Falla cerrado.'
        continue
    }

    if (-not (Test-OfficialUrl -Url $tool.url -OfficialDomain $tool.official_domain)) {
        Write-Host ("  RECHAZADO: la URL no pertenece al dominio oficial declarado ({0})." -f $tool.official_domain)
        continue
    }

    if (-not $Ejecutar) {
        Write-Host ("  SIMULAR: descargar {0}" -f $tool.url)
        Write-Host ("  SIMULAR: verificar SHA-256 {0}" -f $tool.sha256)
        continue
    }

    New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null
    if ($tool.file) {
        $fileName = $tool.file
    }
    else {
        $fileName = Split-Path -Path ([Uri]$tool.url).AbsolutePath -Leaf
    }
    $destination = Join-Path $DownloadDir $fileName

    Write-Host ("  DESCARGANDO: {0}" -f $tool.url)
    Invoke-WebRequest -Uri $tool.url -OutFile $destination

    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $tool.sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $destination -Force
        throw ("SHA-256 inválido para {0}. Esperado={1} Obtenido={2}" -f $tool.name, $tool.sha256, $hash)
    }

    Write-Host ("  OK: hash verificado en {0}" -f $destination)
}
