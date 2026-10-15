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

$result = New-DiagUsbCollectorResult -CollectorId 'wifi_networks' -ScriptBlock {
    $networks = netsh wlan show networks mode=bssid
    $output = @()
    $current = $null
    foreach ($line in $networks) {
        if ($line -match '^\s*SSID\s+\d+\s*:\s*(.+)$') {
            if ($current) { $output += $current }
            $current = [ordered]@{
                ssid = $matches[1].Trim()
                bssid = @()
                signal = @()
                channel = @()
                type = $null
                authentication = $null
                radio_type = $null
            }
        } elseif ($line -match '^\s*BSSID\s+\d+\s*:\s*(.+)$') {
            $current.bssid += $matches[1].Trim()
        } elseif ($line -match '^\s*Signal\s*:\s*(\d+)%') {
            $current.signal += [int]$matches[1]
        } elseif ($line -match '^\s*Channel\s*:\s*(\d+)') {
            $current.channel += [int]$matches[1]
        } elseif ($line -match '^\s*Network type\s*:\s*(.+)$') {
            $current.type = $matches[1].Trim()
        } elseif ($line -match '^\s*Authentication\s*:\s*(.+)$') {
            $current.authentication = $matches[1].Trim()
        } elseif ($line -match '^\s*Radio type\s*:\s*(.+)$') {
            $current.radio_type = $matches[1].Trim()
        }
    }
    if ($current) { $output += $current }
    $output
}

Write-DiagUsbJson -InputObject $result