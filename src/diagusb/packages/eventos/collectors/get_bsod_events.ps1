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

$result = New-DiagUsbCollectorResult -CollectorId 'bsod_events' -ScriptBlock {
    $events = Get-WinEvent -LogName System -MaxEvents 100 -ErrorAction SilentlyContinue | Where-Object { $_.Id -eq 1001 }
    $events | ForEach-Object {
        [ordered]@{
            time_created = $_.TimeCreated.ToString('o')
            id = $_.Id
            level_display_name = $_.LevelDisplayName
            provider_name = $_.ProviderName
            message = $_.Message
            user_name = $_.UserName
        }
    }
}

Write-DiagUsbJson -InputObject $result