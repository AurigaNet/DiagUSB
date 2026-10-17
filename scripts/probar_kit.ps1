# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Prueba de humo de un kit de DiagUSB ya armado. Pensada para CI (no pide UAC,
# no es interactiva). Verifica la integridad del kit, la firma del interprete,
# la version, el listado de paquetes y un diagnostico real de SOLO LECTURA, y
# valida el PDF generado. Sale con codigo 0 si todo pasa, 1 si algo falla.
#
# Uso:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\probar_kit.ps1 -Kit <carpeta del kit>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Kit,
    [string]$Repo,
    [string]$Symptom = 'la_impresora_no_imprime',
    [string]$Package = 'impresion'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$fallos = @()
function Ok { param([string]$m) Write-Host ("  [OK]    {0}" -f $m) }
function Falla { param([string]$m) Write-Host ("  [FALLA] {0}" -f $m); $script:fallos += $m }

if (-not $Repo) {
    $Repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
}

# --- Raiz del kit (la que contiene SHA256SUMS.txt) ---
$Kit = [System.IO.Path]::GetFullPath($Kit)
if (-not (Test-Path -LiteralPath $Kit -PathType Container)) {
    throw ("No existe la carpeta del kit: {0}" -f $Kit)
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
$py = Join-Path $Kit 'python\python.exe'
Write-Host ("Kit: {0}" -f $Kit)
Write-Host ("Repo: {0}" -f $Repo)

# Ejecuta el interprete del kit sin que el stderr de un proceso nativo aborte el
# script (PowerShell 5.1 + ErrorActionPreference=Stop). Devuelve el exit code.
function Invocar {
    param([string[]]$Argumentos, [string]$Log)
    $viejo = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $py @Argumentos > $Log 2>&1
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $viejo
    }
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("probar_kit_" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null

try {
    # --- 1) Integridad contra SHA256SUMS.txt ---
    Write-Host '1) Integridad (SHA256SUMS.txt)'
    if (-not (Test-Path -LiteralPath $py -PathType Leaf)) {
        Falla 'no existe python\python.exe'
    }
    $prefijo = $kitName + '/'
    $nArch = 0
    foreach ($linea in (Get-Content -LiteralPath (Join-Path $Kit 'SHA256SUMS.txt') -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($linea)) { continue }
        $partes = $linea -split '\s+', 2
        if ($partes.Count -ne 2) { Falla ("linea invalida: {0}" -f $linea); continue }
        $rel = $partes[1]
        if ($rel.StartsWith($prefijo)) { $rel = $rel.Substring($prefijo.Length) }
        $f = Join-Path $Kit ($rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { Falla ("falta {0}" -f $rel); continue }
        $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($h -ne $partes[0].ToLowerInvariant()) { Falla ("hash distinto en {0}" -f $rel) }
        $nArch++
    }
    if ($fallos.Count -eq 0) { Ok ("{0} archivos con hash correcto" -f $nArch) }

    # --- 2) Firma del interprete ---
    Write-Host '2) Firma de python\python.exe'
    if (Test-Path -LiteralPath $py -PathType Leaf) {
        $firma = Get-AuthenticodeSignature -LiteralPath $py
        $subject = ''
        if ($firma.SignerCertificate) { $subject = $firma.SignerCertificate.Subject }
        if ($firma.Status -eq 'Valid' -and $subject -like '*Python Software Foundation*') {
            Ok ("firma valida: {0}" -f $subject)
        }
        else {
            Falla ("firma invalida: Status={0} Subject='{1}'" -f $firma.Status, $subject)
        }
    }

    # --- 3) Version ---
    Write-Host '3) Version'
    $verEsperada = ''
    $verPy = Join-Path $Repo 'src\diagusb\_version.py'
    if (Test-Path -LiteralPath $verPy) {
        $t = Get-Content -LiteralPath $verPy -Raw
        if ($t -match '__version__\s*=\s*"([^"]+)"') { $verEsperada = $Matches[1] }
    }
    $logVer = Join-Path $tmp 'version.log'
    Invocar -Argumentos @('-I', '-B', '-m', 'diagusb', '--version') -Log $logVer | Out-Null
    $verSalida = ''
    if (Test-Path -LiteralPath $logVer) {
        $verSalida = ([System.IO.File]::ReadAllText($logVer)).Trim()
    }
    Write-Host ("  salida: {0}" -f $verSalida)
    if ($verEsperada -and $verSalida -notmatch [regex]::Escape($verEsperada)) {
        Falla ("la version no coincide con {0}" -f $verEsperada)
    }
    else {
        Ok 'version coincide'
    }

    # --- 4) list-packages ---
    Write-Host '4) list-packages'
    $code = Invocar -Argumentos @('-I', '-B', '-m', 'diagusb', 'list-packages') -Log (Join-Path $tmp 'list-packages.log')
    if ($code -ne 0) { Falla ("list-packages salio con codigo {0}" -f $code) }
    else { Ok 'list-packages OK' }

    # --- 5) Diagnostico real (solo lectura, modo estandar sin UAC) ---
    Write-Host '5) Diagnostico real (modo estandar, sin UAC)'
    $code = Invocar -Argumentos @('-I', '-B', '-m', 'diagusb', 'diagnose',
        '-s', $Symptom, '-p', $Package, '-o', $tmp) -Log (Join-Path $tmp 'diag.log')
    if ($code -ne 0) { Falla ("diagnose salio con codigo {0}" -f $code) }
    else { Ok 'diagnose OK' }

    $pdf = Get-ChildItem -LiteralPath $tmp -Filter '*.pdf' -File | Select-Object -First 1
    if (-not $pdf) {
        Falla 'no se genero ningun PDF'
    }
    else {
        Ok ("PDF generado: {0} ({1} bytes)" -f $pdf.Name, $pdf.Length)
        $validador = Join-Path $Repo 'tests\validar_pdf.py'
        if (Test-Path -LiteralPath $validador) {
            $code = Invocar -Argumentos @('-X', 'utf8', $validador, $pdf.FullName) -Log (Join-Path $tmp 'pdf.log')
            if ($code -ne 0) { Falla 'el PDF no paso la validacion estructural' }
            else { Ok 'PDF valido' }
        }
        else {
            Falla ("no se encontro el validador: {0}" -f $validador)
        }
    }

    # --- 6) Sin __pycache__ ---
    Write-Host '6) Sin __pycache__'
    $pc = Get-ChildItem -LiteralPath $Kit -Recurse -Directory -Filter '__pycache__'
    if ($pc) {
        foreach ($d in $pc) { Falla ("quedo __pycache__ en {0}" -f $d.FullName) }
    }
    else {
        Ok 'no se creo __pycache__'
    }
}
finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# --- Resultado ---
Write-Host ''
if ($fallos.Count -gt 0) {
    Write-Host ("RESULTADO: FALLO ({0} problemas)" -f $fallos.Count)
    exit 1
}
Write-Host 'RESULTADO: OK'
exit 0
