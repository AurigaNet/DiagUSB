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

$result = New-DiagUsbCollectorResult -CollectorId 'installed_patches' -ScriptBlock {
    $hotfixes = @(Get-HotFix | Sort-Object -Property HotFixID)
    $cimHotfixes = @(Get-CimInstance -ClassName Win32_QuickFixEngineering | Sort-Object -Property HotFixID)

    $hotfixList = @($hotfixes | ForEach-Object {
        [ordered]@{
            hotfix_id = $_.HotFixID
            description = $_.Description
            installed_by = $_.InstalledBy
            installed_on = $(if ($_.InstalledOn) { $_.InstalledOn.ToUniversalTime().ToString('o') } else { $null })
            cs_name = $_.CSName
        }
    })

    $cimHotfixList = @($cimHotfixes | ForEach-Object {
        [ordered]@{
            hotfix_id = $_.HotFixID
            description = $_.Description
            installed_by = $_.InstalledBy
            installed_on = $(if ($_.InstalledOn) { $_.InstalledOn.ToUniversalTime().ToString('o') } else { $null })
            cs_name = $_.CSName
        }
    })

    return [ordered]@{
        hotfixes = $hotfixList
        cim_hotfixes = $cimHotfixList
    }
}

Write-DiagUsbJson -InputObject $result