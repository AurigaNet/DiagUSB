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

$result = New-DiagUsbCollectorResult -CollectorId 'network_adapters' -ScriptBlock {
    Get-NetAdapter | Where-Object { $_.PhysicalMediaType -match 'Wireless|802.3' } | Sort-Object -Property Name | ForEach-Object {
        [ordered]@{
            name = $_.Name
            status = $_.Status
            state = if ($_.Status -eq 'Up') { 'Up' } else { 'Down' }
            speed = $_.LinkSpeed
            mac_address = $_.MacAddress
            type = $_.InterfaceDescription
            media_type = $_.PhysicalMediaType
            vlan_id = $_.VlanID
        }
    }
}

Write-DiagUsbJson -InputObject $result
