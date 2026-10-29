# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Prepara una publicacion local completa de DiagUSB a partir del codigo del
# repositorio: ejecuta la suite, arma el kit, lo verifica contra su propio
# SHA256SUMS.txt, corre la prueba de humo, opcionalmente construye el
# instalador y deja en dist\release\<version>\ los artefactos, las notas
# generadas desde el CHANGELOG y SHA256SUMS.txt.
#
# Falla cerrado: si la version no se puede leer, si el tag no coincide, si el
# kit no se genera o no pasa la verificacion, si falta un artefacto o si una
# prueba falla, termina con error y no deja una publicacion a medias.
#
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publicar_release.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publicar_release.ps1 -Tag v0.1.0 -ConInstalador -PythonZip C:\ruta\python-3.13.15-embed-amd64.zip
#
# Este script NO sube nada a GitHub, NO firma binarios y NO descarga imagenes
# del live USB. La publicacion en GitHub se hace desde el workflow
# .github\workflows\build-kit.yml o manualmente con gh (ver docs\PUBLICACION.md).

[CmdletBinding()]
param(
    [string]$Salida = 'dist\release',
    [string]$Python = 'python',
    [string]$PythonZip,
    [string]$Tag,
    [switch]$ConInstalador,
    [switch]$OmitirPruebas
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = Join-Path $Repo 'src'

function Escribir-Paso {
    param([Parameter(Mandatory = $true)][string]$Texto)
    Write-Host ''
    Write-Host ("==> {0}" -f $Texto) -ForegroundColor Cyan
}

function Invocar-Python {
    param([Parameter(Mandatory = $true)][string[]]$Argumentos)
    & $Python -X utf8 @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw ("Fallo 'python {0}' con codigo {1}." -f ($Argumentos -join ' '), $LASTEXITCODE)
    }
}

function Invocar-Script {
    param(
        [Parameter(Mandatory = $true)][string]$Script,
        [Parameter(Mandatory = $true)][hashtable]$Opciones
    )
    $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Script)
    foreach ($clave in $Opciones.Keys) {
        $valor = $Opciones[$clave]
        if ($valor -is [switch]) {
            if ($valor.IsPresent) { $argumentos += ('-' + $clave) }
        }
        else {
            $argumentos += ('-' + $clave)
            $argumentos += [string]$valor
        }
    }
    & powershell @argumentos
    if ($LASTEXITCODE -ne 0) {
        throw ("Fallo {0} con codigo {1}." -f (Split-Path -Leaf $Script), $LASTEXITCODE)
    }
}

# --- 1) Version y tag ---
Escribir-Paso 'Leyendo la version declarada'
$versionPy = Join-Path $Repo 'src\diagusb\_version.py'
if (-not (Test-Path -LiteralPath $versionPy -PathType Leaf)) {
    throw ("No se encontro {0}" -f $versionPy)
}
$textoVersion = Get-Content -LiteralPath $versionPy -Raw
if ($textoVersion -notmatch '__version__\s*=\s*"([^"]+)"') {
    throw 'No se pudo leer __version__ de src/diagusb/_version.py'
}
$Version = $Matches[1]
if ($Version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?$') {
    throw ("Version declarada con formato inesperado: {0}" -f $Version)
}
if (-not $Tag) { $Tag = 'v' + $Version }
$patronTag = '^v' + [regex]::Escape($Version) + '(-rc[0-9]+)?$'
if ($Tag -notmatch $patronTag) {
    throw ("El tag '{0}' no coincide con 'v{1}' ni con 'v{1}-rcN'." -f $Tag, $Version)
}
Write-Host ("Version: {0} | Tag: {1}" -f $Version, $Tag)

# --- 2) Suite de pruebas ---
if ($OmitirPruebas) {
    Write-Host 'Aviso: se omite la suite por -OmitirPruebas.' -ForegroundColor Yellow
}
else {
    Escribir-Paso 'Ejecutando la suite de pruebas'
    Invocar-Python -Argumentos @((Join-Path $Repo 'tests\run_tests.py'))
}

# --- 3) Kit portable ---
Escribir-Paso 'Armando el kit portable'
$kitDir = Join-Path $Repo 'dist\kit'
$opcionesKit = @{ Salida = $kitDir; Python = $Python }
if ($PythonZip) { $opcionesKit['PythonZip'] = $PythonZip }
Invocar-Script -Script (Join-Path $PSScriptRoot 'armar_kit.ps1') -Opciones $opcionesKit

$zip = Join-Path $kitDir ("DiagUSB-kit-{0}.zip" -f $Version)
if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
    throw ("No se genero el kit esperado: {0}" -f $zip)
}

# --- 4) Verificacion estricta del ZIP ---
Escribir-Paso 'Verificando el ZIP contra su SHA256SUMS.txt (modo estricto)'
Invocar-Python -Argumentos @('-m', 'diagusb', 'verificar-kit', $zip, '--estricto')

# --- 5) Prueba de humo sobre el kit descomprimido ---
Escribir-Paso 'Probando el kit armado'
$opcionesPrueba = @{ Kit = (Join-Path $kitDir 'DiagUSB') }
Invocar-Script -Script (Join-Path $PSScriptRoot 'probar_kit.ps1') -Opciones $opcionesPrueba

# --- 6) Instalador opcional ---
$instalador = $null
if ($ConInstalador) {
    Escribir-Paso 'Construyendo el instalador (PyInstaller + Inno Setup)'
    Invocar-Script -Script (Join-Path $PSScriptRoot 'build_installer.ps1') `
        -Opciones @{ Python = $Python }
    $instalador = Join-Path $Repo ("dist\installer\DiagUSB-Setup-{0}.exe" -f $Version)
    if (-not (Test-Path -LiteralPath $instalador -PathType Leaf)) {
        throw ("No se genero el instalador esperado: {0}" -f $instalador)
    }
}

# --- 7) Destino de la publicacion ---
if ([System.IO.Path]::IsPathRooted($Salida)) {
    $raizSalida = [System.IO.Path]::GetFullPath($Salida)
}
else {
    $raizSalida = [System.IO.Path]::GetFullPath((Join-Path $Repo $Salida))
}
$destino = Join-Path $raizSalida $Version
if (Test-Path -LiteralPath $destino) {
    Write-Host ("Limpiando publicacion previa: {0}" -f $destino)
    Remove-Item -LiteralPath $destino -Recurse -Force
}
New-Item -ItemType Directory -Path $destino -Force | Out-Null

Escribir-Paso 'Copiando artefactos'
$zipDestino = Join-Path $destino (Split-Path -Leaf $zip)
Copy-Item -LiteralPath $zip -Destination $zipDestino -Force
Write-Host ("  {0}" -f (Split-Path -Leaf $zipDestino))
$artefactos = @($zipDestino)
if ($instalador) {
    $instaladorDestino = Join-Path $destino (Split-Path -Leaf $instalador)
    Copy-Item -LiteralPath $instalador -Destination $instaladorDestino -Force
    Write-Host ("  {0}" -f (Split-Path -Leaf $instaladorDestino))
    $artefactos += $instaladorDestino
}

# --- 8) Notas y metadatos desde el CHANGELOG ---
Escribir-Paso 'Generando notas de publicacion'
$notas = Join-Path $destino ("NOTAS-{0}.md" -f $Version)
$metadatos = Join-Path $destino 'release.json'
$argumentosNotas = @(
    '-m', 'diagusb', 'notas-release',
    '--version', $Version,
    '--tag', $Tag,
    '--salida', $notas,
    '--json-salida', $metadatos
)
foreach ($artefacto in $artefactos) {
    $argumentosNotas += @('--artefacto', $artefacto)
}
Invocar-Python -Argumentos $argumentosNotas

# --- 9) SHA256SUMS.txt de la publicacion ---
Escribir-Paso 'Escribiendo SHA256SUMS.txt'
$publicados = @($artefactos) + @($notas, $metadatos)
$lineas = foreach ($archivo in $publicados) {
    if (-not (Test-Path -LiteralPath $archivo -PathType Leaf)) {
        throw ("Falta un artefacto de la publicacion: {0}" -f $archivo)
    }
    $hash = (Get-FileHash -LiteralPath $archivo -Algorithm SHA256).Hash.ToLowerInvariant()
    "{0}  {1}" -f $hash, (Split-Path -Leaf $archivo)
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    (Join-Path $destino 'SHA256SUMS.txt'),
    (($lineas -join "`r`n") + "`r`n"),
    $utf8)

# --- 10) Resumen ---
Write-Host ''
Write-Host 'Publicacion preparada' -ForegroundColor Green
Write-Host ("  Carpeta : {0}" -f $destino)
Write-Host ("  Version : {0}" -f $Version)
Write-Host ("  Tag     : {0}" -f $Tag)
foreach ($archivo in (Get-ChildItem -LiteralPath $destino -File | Sort-Object Name)) {
    $hash = (Get-FileHash -LiteralPath $archivo.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host ("  {0}  {1} ({2} bytes)" -f $hash, $archivo.Name, $archivo.Length)
}
Write-Host ''
Write-Host 'Siguiente paso: revisar las notas y publicar manualmente o con el workflow.'
exit 0
