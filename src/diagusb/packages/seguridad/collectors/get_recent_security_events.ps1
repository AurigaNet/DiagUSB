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

$result = New-DiagUsbCollectorResult -CollectorId 'security_events' -ScriptBlock {
    $events = @()

    try {
        $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'DIAGUSB_DENIED: Se requieren permisos de Administrador para leer el Log de Seguridad.'
        }

        $securityEvents = Get-WinEvent -LogName Security -MaxEvents 20 -ErrorAction Stop |
            Where-Object { $_.Id -in @(4624, 4625, 4634, 4647, 4672, 4719, 4732, 4733, 4756, 4757) } |
            ForEach-Object {
                [ordered]@{
                    id = $_.Id
                    record_id = $_.RecordId
                    level = $_.Level
                    level_display_name = $_.LevelDisplayName
                    provider_name = $_.ProviderName
                    message = $_.Message
                    time_created_utc = if ($_.TimeCreated) { $_.TimeCreated.ToUniversalTime().ToString('o') } else { $null }
                    keywords = $_.Keywords
                    task = $_.Task
                    opcode = $_.Opcode
                    event_data = @($_.Properties | ForEach-Object { $_.Value.ToString() })
                }
            }

        $events = $securityEvents
    }
    catch {
        if ($_.Exception.Message -like '* acceso*' -or $_.Exception.Message -like '* denied*' -or $_.Exception.Message -like '* permiso*') {
            throw 'DIAGUSB_DENIED: Se requieren permisos de Administrador para leer el Log de Seguridad.'
        }
        if ($_.Exception.Message -like '* no existe*' -or $_.Exception.Message -like '* not found*') {
            throw 'DIAGUSB_NOT_AVAILABLE: El Log de Seguridad no está disponible en este sistema.'
        }
        throw "DIAGUSB_NOT_AVAILABLE: No se pudieron leer los eventos de seguridad: $($_.Exception.Message)"
    }

    return $events
}

Write-DiagUsbJson -InputObject $result
