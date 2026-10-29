# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
# Construye el instalador unico de DiagUSB para Windows x64.

[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$InnoSetup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$VersionPy = Join-Path $Repo 'src\diagusb\_version.py'
$Iss = Join-Path $Repo 'installer\DiagUSB.iss'
$Payload = Join-Path $Repo 'dist\DiagUSB'
$Salida = Join-Path $Repo 'dist\installer'

function Escribir-Paso {
    param([string]$Texto)
    Write-Host ""
    Write-Host "==> $Texto" -ForegroundColor Cyan
}

function Buscar-InnoSetup {
    if ($InnoSetup) {
        if (Test-Path -LiteralPath $InnoSetup) { return (Resolve-Path -LiteralPath $InnoSetup).Path }
        throw "No existe el compilador de Inno Setup indicado: $InnoSetup"
    }
    $comando = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($comando) { return $comando.Source }
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    foreach ($candidato in $candidatos) {
        if ($candidato -and (Test-Path -LiteralPath $candidato)) { return $candidato }
    }
    throw "No se encontro Inno Setup 6. Instalalo con: winget install --id JRSoftware.InnoSetup --exact"
}

if (-not (Test-Path -LiteralPath $VersionPy)) { throw "No se encontro $VersionPy" }
$textoVersion = Get-Content -LiteralPath $VersionPy -Raw
if ($textoVersion -notmatch '__version__\s*=\s*"([^"]+)"') {
    throw "No se pudo leer __version__ de $VersionPy"
}
$Version = $Matches[1]

Escribir-Paso "Verificando dependencias de build"
& $Python -c "import PyInstaller, PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Faltan dependencias. Ejecuta: $Python -m pip install pyinstaller pillow"
}
$Iscc = Buscar-InnoSetup

Escribir-Paso "Generando recursos de marca y metadatos"
& $Python -X utf8 (Join-Path $Repo 'scripts\generar_marca.py')
if ($LASTEXITCODE -ne 0) { throw "Fallo la generacion de recursos de marca." }
& $Python -X utf8 (Join-Path $Repo 'scripts\generar_version_info.py')
if ($LASTEXITCODE -ne 0) { throw "Fallo la generacion de version_info." }
& $Python -X utf8 (Join-Path $Repo 'scripts\generar_manifiesto.py')
if ($LASTEXITCODE -ne 0) { throw "Fallo la generacion del manifiesto." }

Escribir-Paso "Limpiando payload anterior"
if (Test-Path -LiteralPath $Payload) {
    Remove-Item -LiteralPath $Payload -Recurse -Force
}
if (Test-Path -LiteralPath $Salida) {
    Get-ChildItem -LiteralPath $Salida -Filter 'DiagUSB-Setup-*.exe' -File -ErrorAction SilentlyContinue |
        Remove-Item -Force
}
New-Item -ItemType Directory -Force -Path $Salida | Out-Null

Escribir-Paso "Construyendo aplicacion windowed con PyInstaller"
Push-Location $Repo
try {
    & $Python -m PyInstaller 'build\diagusb_gui.spec' --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "Fallo PyInstaller." }
}
finally {
    Pop-Location
}

$Exe = Join-Path $Payload 'DiagUSB.exe'
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "PyInstaller no genero $Exe"
}

Escribir-Paso "Compilando instalador con Inno Setup"
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
$textoIss = [System.IO.File]::ReadAllText($Iss, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($Iss, $textoIss, $utf8Bom)

Push-Location $Repo
try {
    & $Iscc "/DMiAppVersion=$Version" 'installer\DiagUSB.iss'
    if ($LASTEXITCODE -ne 0) { throw "Fallo Inno Setup." }
}
finally {
    Pop-Location
}

$Instalador = Join-Path $Salida "DiagUSB-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $Instalador)) {
    throw "No se genero el instalador esperado: $Instalador"
}

$Hash = (Get-FileHash -LiteralPath $Instalador -Algorithm SHA256).Hash.ToLowerInvariant()
$Tamano = [math]::Round((Get-Item -LiteralPath $Instalador).Length / 1MB, 2)

Write-Host ""
Write-Host "Instalador listo: $Instalador" -ForegroundColor Green
Write-Host "Version: $Version"
Write-Host "Tamano: $Tamano MB"
Write-Host "SHA-256: $Hash"
