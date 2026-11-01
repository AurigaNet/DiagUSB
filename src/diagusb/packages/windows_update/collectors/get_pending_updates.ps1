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

$result = New-DiagUsbCollectorResult -CollectorId 'pending_updates' -ScriptBlock {
    $moduleAvailable = Get-Module -ListAvailable -Name PSWindowsUpdate -ErrorAction SilentlyContinue

    if (-not $moduleAvailable) {
        throw 'DIAGUSB_NOT_AVAILABLE: el modulo PSWindowsUpdate no esta instalado; no se pueden consultar las actualizaciones pendientes.'
    }

    try {
        Import-Module PSWindowsUpdate -Force -ErrorAction Stop
        $updates = Get-WindowsUpdate -Category 'Updates' -ErrorAction SilentlyContinue |
            Select-Object @{N='KB'; E={$_.KB}},
                          @{N='Title'; E={$_.Title}},
                          @{N='Severity'; E={$_.Severity}},
                          @{N='Size'; E={$_.Size}},
                          @{N='IsInstalled'; E={$_.IsInstalled}},
                          @{N='IsHidden'; E={$_.Hidden}}

        $pendingUpdates = $updates | Where-Object { -not $_.IsInstalled }

        $updateList = @()
        foreach ($update in $pendingUpdates) {
            $updateList += @{
                kb = $update.KB
                titulo = $update.Title
                importancia = $update.Severity
                tamanho_mb = [math]::Round($update.Size / 1MB, 2)
            }
        }

        return @{
            status = 'ok'
            modulo_activo = $true
            actualizaciones_pendientes = $updateList.Count
            actualizaciones = $updateList
        }
    } catch {
        throw ("DIAGUSB_NOT_AVAILABLE: no se pudo consultar PSWindowsUpdate: " + $_.Exception.Message)
    }
}

Write-DiagUsbJson -InputObject $result
