# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
#
# Arma el kit portable de DiagUSB: distribucion embebida oficial de Python
# (python.org) + codigo fuente + lanzadores, verifica firmas y SHA-256, y lo
# comprime en DiagUSB-kit-<version>.zip. Aborta con mensaje claro ante cualquier
# falla. No requiere red si se pasa -PythonZip con el zip ya descargado.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Salida,
    [string]$PythonZip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Constantes fijas del Python embebido oficial (no editar sin re-verificar) ---
$PYTHON_VERSION = '3.13.15'
$PYTHON_SHA256  = 'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'
$PYTHON_ZIP     = "python-$PYTHON_VERSION-embed-amd64.zip"
$PYTHON_URL     = "https://www.python.org/ftp/python/$PYTHON_VERSION/$PYTHON_ZIP"
$FIRMANTE_PSF   = 'Python Software Foundation'
$FIRMANTE_MS    = 'Microsoft Corporation'

function Escribir-Utf8SinBom {
    param([Parameter(Mandatory = $true)][string]$Ruta,
          [Parameter(Mandatory = $true)][string]$Contenido)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Ruta, $Contenido, $utf8)
}

function Normalizar-Crlf {
    param([Parameter(Mandatory = $true)][string]$Texto)
    return (($Texto -replace "`r`n", "`n") -replace "`n", "`r`n")
}

$Repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

# --- Version declarada ---
$versionPy = Join-Path $Repo 'src\diagusb\_version.py'
if (-not (Test-Path -LiteralPath $versionPy)) {
    throw "No se encontro $versionPy"
}
$texto = Get-Content -LiteralPath $versionPy -Raw
if ($texto -notmatch '__version__\s*=\s*"([^"]+)"') {
    throw 'No se pudo leer __version__ de src/diagusb/_version.py'
}
$Version = $Matches[1]
Write-Host "DiagUSB version declarada: $Version"

# --- Python embebido: obtener zip y verificar SHA-256 ---
$tmpZip = $null
if ($PythonZip) {
    if (-not (Test-Path -LiteralPath $PythonZip)) {
        throw "No existe el archivo indicado en -PythonZip: $PythonZip"
    }
    $zipPath = (Resolve-Path -LiteralPath $PythonZip).Path
    Write-Host "Usando zip provisto (sin red): $zipPath"
}
else {
    $tmpZip = Join-Path ([System.IO.Path]::GetTempPath()) "diagusb-$PYTHON_ZIP"
    Write-Host "Descargando: $PYTHON_URL"
    Invoke-WebRequest -Uri $PYTHON_URL -OutFile $tmpZip
    $zipPath = $tmpZip
}

$hashZip = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "SHA-256 del zip : $hashZip"
Write-Host "SHA-256 esperado: $PYTHON_SHA256"
if ($hashZip -ne $PYTHON_SHA256) {
    if ($tmpZip) { Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue }
    throw "SHA-256 invalido para $PYTHON_ZIP. Esperado=$PYTHON_SHA256 Obtenido=$hashZip"
}
Write-Host 'SHA-256 verificado contra la constante.'

# --- Destino ---
$Salida = [System.IO.Path]::GetFullPath($Salida)
if (-not (Test-Path -LiteralPath $Salida)) {
    New-Item -ItemType Directory -Path $Salida -Force | Out-Null
}
$KitRoot = Join-Path $Salida 'DiagUSB'
if (Test-Path -LiteralPath $KitRoot) {
    Write-Host "Limpiando destino previo: $KitRoot"
    Remove-Item -LiteralPath $KitRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $KitRoot -Force | Out-Null

# --- 1) Descomprimir Python embebido ---
$pyDir = Join-Path $KitRoot 'python'
Expand-Archive -LiteralPath $zipPath -DestinationPath $pyDir -Force
if ($tmpZip) { Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue }
Write-Host "Python embebido extraido en: $pyDir"

# --- 2) Verificar firmas de TODOS los binarios PE de Python ---
$binarios = Get-ChildItem -LiteralPath $pyDir -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' } |
    Sort-Object Name
if (-not $binarios) {
    throw 'No se encontraron binarios (*.exe/*.dll/*.pyd) para verificar firmas.'
}
$fallos = @()
foreach ($b in $binarios) {
    $f = Get-AuthenticodeSignature -LiteralPath $b.FullName
    $subject = ''
    if ($f.SignerCertificate) { $subject = $f.SignerCertificate.Subject }
    $esperado = if ($b.Name -like 'vcruntime*') { $FIRMANTE_MS } else { $FIRMANTE_PSF }
    Write-Host ("  {0,-26} {1,-12} {2}" -f $b.Name, $f.Status, $subject)
    if (($f.Status -ne 'Valid') -or ($subject -notlike "*$esperado*")) {
        $fallos += ("{0}: Status={1} Subject='{2}' (se esperaba '{3}')" -f $b.Name, $f.Status, $subject, $esperado)
    }
}
if ($fallos.Count -gt 0) {
    throw ("Firmas invalidas:`n  - " + ($fallos -join "`n  - "))
}
Write-Host 'Firmas verificadas: todos los binarios PE firmados por la PSF (o Microsoft para vcruntime*).'

# --- 3) Arbol del kit ---
# 3a) codigo fuente (sin __pycache__)
$srcDst = Join-Path $KitRoot 'src\diagusb'
New-Item -ItemType Directory -Path (Split-Path -Parent $srcDst) -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Repo 'src\diagusb') -Destination $srcDst -Recurse
Get-ChildItem -LiteralPath $srcDst -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force
Write-Host "Codigo fuente copiado en: $srcDst"

# 3b) colectores compartidos: src\collectors\_common.ps1 (el walk de los .ps1
#     y core/integridad.py buscan '<ancestro>\collectors\_common.ps1')
$colDst = Join-Path $KitRoot 'src\collectors'
Copy-Item -LiteralPath (Join-Path $Repo 'collectors') -Destination $colDst -Recurse
Write-Host "Colectores compartidos en: $colDst"

# 3c) manifiesto de hashes (core/integridad.py lo busca en <raiz-kit>/manifiesto_hashes.json)
$manifiesto = Join-Path $KitRoot 'manifiesto_hashes.json'
python -X utf8 (Join-Path $Repo 'scripts\generar_manifiesto.py') $manifiesto
if ($LASTEXITCODE -ne 0) { throw 'Fallo la generacion del manifiesto de hashes.' }
if (-not (Test-Path -LiteralPath $manifiesto)) { throw "No se genero el manifiesto: $manifiesto" }

# 3d) LICENSE
Copy-Item -LiteralPath (Join-Path $Repo 'LICENSE') -Destination (Join-Path $KitRoot 'LICENSE') -Force

# 3e) LEEME.txt
$leeme = @'
DiagUSB - Kit portable
======================

Este kit incluye DiagUSB y una distribucion embebida de Python 3.13.15
(c) Python Software Foundation, redistribuida bajo su propia licencia.
No incluye ejecutables propios: DiagUSB es codigo fuente Python que se ejecuta
con el interprete incluido en la carpeta python\.

Como usar:
  1) Copie la carpeta DiagUSB al pendrive o al equipo destino.
  2) Ejecute Iniciar_DiagUSB.cmd (interfaz web) o Iniciar_DiagUSB_consola.cmd (menu).
  3) Acepte el dialogo de Administrador (UAC) para obtener datos completos. Si lo
     rechaza, el programa continua con permisos limitados.

Notas:
  - El programa es de SOLO LECTURA: no modifica la configuracion del equipo.
  - No envia datos por red; la interfaz web escucha solo en 127.0.0.1.
  - Los informes se guardan en la carpeta del kit (subcarpeta reports\).
  - Los binarios de python\ estan firmados por Python Software Foundation (y por
     Microsoft para vcruntime*). python313.zip y los archivos .py NO estan
     cubiertos por firma digital.
  - SHA256SUMS.txt permite comprobar la integridad de los archivos del kit.

Copyright (C) 2026 Daniel Ricardo Novoa
Licencia: GPL-3.0-or-later (ver LICENSE)
'@
Escribir-Utf8SinBom -Ruta (Join-Path $KitRoot 'LEEME.txt') -Contenido (Normalizar-Crlf $leeme)

# --- 4) python313._pth (sin import site) ---
$mm = (($PYTHON_VERSION -split '\.')[0..1] -join '')
$pthName = "python$mm._pth"
$pth = "python$mm.zip`r`n.`r`n..\src`r`n"
Escribir-Utf8SinBom -Ruta (Join-Path $pyDir $pthName) -Contenido $pth
Write-Host "Escrito $pthName con: python$mm.zip, ., ..\src"

# --- 5) Lanzadores ---
$lanzadorWeb = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "KIT=%~dp0"
title DiagUSB - Iniciar (interfaz web)
cd /d "%KIT%"

echo ============================================================
echo  DiagUSB - Iniciar (interfaz web)
echo ============================================================
echo.

if not exist "%KIT%python\python.exe" (
    echo ERROR: no se encontro python\python.exe en el kit.
    goto :error
)

echo Verificando la firma digital de python\python.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-AuthenticodeSignature -LiteralPath '%KIT%python\python.exe'; if ($f.Status -eq 'HashMismatch' -or $f.Status -eq 'NotSigned') { Write-Host ('FIRMA INVALIDA (' + $f.Status + '). No se ejecutara nada.'); exit 2 } elseif ($f.Status -ne 'Valid') { Write-Host ('AVISO: no se pudo validar la firma (' + $f.Status + '); se continuara.'); exit 0 } else { Write-Host ('Firma valida: ' + $f.SignerCertificate.Subject); exit 0 }"
if errorlevel 2 goto :firma_mala
if errorlevel 1 goto :error

echo.
echo ------------------------------------------------------------
echo  Que hace DiagUSB:
echo   - Ejecuta consultas de SOLO LECTURA con PowerShell sobre este equipo.
echo   - Solicita permisos de Administrador (UAC) para obtener datos completos.
echo   - NO modifica la configuracion del equipo.
echo   - NO envia datos por red.
echo   - Abre la interfaz web local en 127.0.0.1 (solo en este equipo).
echo   - Guarda los informes en la carpeta del kit.
echo ------------------------------------------------------------
echo.
set /p RESPUESTA=¿Continuar? (S/N): 
if /i not "%RESPUESTA%"=="S" (
    echo Operacion cancelada por el usuario.
    goto :fin
)

echo.
echo Iniciando DiagUSB ...
"%KIT%python\python.exe" -I -B -m diagusb --open web %*
if errorlevel 1 goto :error
goto :fin

:error
echo.
echo ERROR: DiagUSB termino con un error. Revise el mensaje anterior.
pause

:firma_mala
echo.
echo ERROR: la firma digital de python\python.exe no es valida. No se ejecutara DiagUSB.
pause

:fin
endlocal
'@
Escribir-Utf8SinBom -Ruta (Join-Path $KitRoot 'Iniciar_DiagUSB.cmd') -Contenido (Normalizar-Crlf $lanzadorWeb)

$lanzadorConsola = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "KIT=%~dp0"
title DiagUSB - Iniciar (consola)
cd /d "%KIT%"

echo ============================================================
echo  DiagUSB - Iniciar (menu de consola)
echo ============================================================
echo.

if not exist "%KIT%python\python.exe" (
    echo ERROR: no se encontro python\python.exe en el kit.
    goto :error
)

echo Verificando la firma digital de python\python.exe ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-AuthenticodeSignature -LiteralPath '%KIT%python\python.exe'; if ($f.Status -eq 'HashMismatch' -or $f.Status -eq 'NotSigned') { Write-Host ('FIRMA INVALIDA (' + $f.Status + '). No se ejecutara nada.'); exit 2 } elseif ($f.Status -ne 'Valid') { Write-Host ('AVISO: no se pudo validar la firma (' + $f.Status + '); se continuara.'); exit 0 } else { Write-Host ('Firma valida: ' + $f.SignerCertificate.Subject); exit 0 }"
if errorlevel 2 goto :firma_mala
if errorlevel 1 goto :error

echo.
echo ------------------------------------------------------------
echo  Que hace DiagUSB:
echo   - Ejecuta consultas de SOLO LECTURA con PowerShell sobre este equipo.
echo   - Solicita permisos de Administrador (UAC) para obtener datos completos.
echo   - NO modifica la configuracion del equipo.
echo   - NO envia datos por red.
echo   - Guarda los informes en la carpeta del kit.
echo ------------------------------------------------------------
echo.
set /p RESPUESTA=¿Continuar? (S/N): 
if /i not "%RESPUESTA%"=="S" (
    echo Operacion cancelada por el usuario.
    goto :fin
)

echo.
echo Iniciando DiagUSB (consola) ...
"%KIT%python\python.exe" -I -B -m diagusb %*
if errorlevel 1 goto :error
goto :fin

:error
echo.
echo ERROR: DiagUSB termino con un error. Revise el mensaje anterior.
pause

:firma_mala
echo.
echo ERROR: la firma digital de python\python.exe no es valida. No se ejecutara DiagUSB.
pause

:fin
endlocal
'@
Escribir-Utf8SinBom -Ruta (Join-Path $KitRoot 'Iniciar_DiagUSB_consola.cmd') -Contenido (Normalizar-Crlf $lanzadorConsola)

# --- 6) SHA256SUMS.txt (rutas relativas a la raiz del zip: DiagUSB/...) ---
$entradas = Get-ChildItem -LiteralPath $KitRoot -Recurse -File |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
    Sort-Object FullName
$lineas = foreach ($e in $entradas) {
    $rel = 'DiagUSB/' + ($e.FullName.Substring($KitRoot.Length + 1) -replace '\\', '/')
    "$((Get-FileHash -LiteralPath $e.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $rel"
}
Escribir-Utf8SinBom -Ruta (Join-Path $KitRoot 'SHA256SUMS.txt') -Contenido (($lineas -join "`r`n") + "`r`n")
Write-Host ("SHA256SUMS.txt escrito ({0} archivos)." -f $entradas.Count)

# --- 7) Comprimir ---
$zipOut = Join-Path $Salida "DiagUSB-kit-$Version.zip"
if (Test-Path -LiteralPath $zipOut) { Remove-Item -LiteralPath $zipOut -Force }
tar -a -c -f $zipOut -C $Salida DiagUSB
if ($LASTEXITCODE -ne 0) { throw 'Fallo la compresion del kit con tar.' }
$hashOut = (Get-FileHash -LiteralPath $zipOut -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host ''
Write-Host "Kit generado : $zipOut"
Write-Host "SHA-256      : $hashOut"
Write-Host "Version      : $Version"
