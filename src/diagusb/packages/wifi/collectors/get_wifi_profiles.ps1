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

$result = New-DiagUsbCollectorResult -CollectorId 'wifi_profiles' -ScriptBlock {
    $profiles = netsh wlan show profiles | Select-String -Pattern '^\s*All User Profile\s*:\s*(.+)$' | ForEach-Object { $_.Matches.Groups[1].Value.Trim() }
    $output = @()
    foreach ($profile in $profiles) {
        $details = netsh wlan show profile name="$profile" key=clear | Select-Object -SkipLast 1
        $output += [ordered]@{
            name = $profile
            details = ($details | Out-String).Trim()
        }
    }
    $output
}

Write-DiagUsbJson -InputObject $result