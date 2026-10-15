# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Path)) {
    throw "No se encontró el archivo: $Path"
}

$hash = Get-FileHash -LiteralPath $Path -Algorithm SHA256
Write-Output ("Archivo : {0}" -f $hash.Path)
Write-Output ("SHA256  : {0}" -f $hash.Hash.ToLowerInvariant())