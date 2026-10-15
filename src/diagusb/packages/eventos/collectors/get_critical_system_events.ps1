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

$result = New-DiagUsbCollectorResult -CollectorId 'critical_events' -ScriptBlock {
    Get-WinEvent -LogName System -MaxEvents 30 -ErrorAction SilentlyContinue | Where-Object {
        $_.Level -eq 1 -or $_.Level -eq 2
    } | ForEach-Object {
        $timeCreated = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'TimeCreated'
        $message = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'Message'
        $userName = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'UserName'

        [ordered]@{
            time_created = $(if ($timeCreated) { ([DateTime]$timeCreated).ToString('o') } else { $null })
            id = $_.Id
            level = $_.Level
            level_display_name = $_.LevelDisplayName
            provider_name = $_.ProviderName
            message = $message
            user_name = $userName
        }
    }
}

Write-DiagUsbJson -InputObject $result