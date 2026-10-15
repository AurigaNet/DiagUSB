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

$result = New-DiagUsbCollectorResult -CollectorId 'memory_status' -ScriptBlock {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem

    $totalVisibleMemoryKB = $os.TotalVisibleMemorySize
    $freePhysicalMemoryKB = $os.FreePhysicalMemory
    $totalVirtualMemoryKB = $os.TotalVirtualMemorySize
    $freeVirtualMemoryKB = $os.FreeVirtualMemory

    $usedPhysicalMemoryKB = $totalVisibleMemoryKB - $freePhysicalMemoryKB
    $usedVirtualMemoryKB = $totalVirtualMemoryKB - $freeVirtualMemoryKB

    $physicalMemoryPercent = if ($totalVisibleMemoryKB -gt 0) {
        [math]::Round(($usedPhysicalMemoryKB / $totalVisibleMemoryKB) * 100, 2)
    } else { 0 }

    $virtualMemoryPercent = if ($totalVirtualMemoryKB -gt 0) {
        [math]::Round(($usedVirtualMemoryKB / $totalVirtualMemoryKB) * 100, 2)
    } else { 0 }

    return [ordered]@{
        total_visible_memory_kb = $totalVisibleMemoryKB
        free_physical_memory_kb = $freePhysicalMemoryKB
        used_physical_memory_kb = $usedPhysicalMemoryKB
        physical_memory_usage_percent = $physicalMemoryPercent
        total_virtual_memory_kb = $totalVirtualMemoryKB
        free_virtual_memory_kb = $freeVirtualMemoryKB
        used_virtual_memory_kb = $usedVirtualMemoryKB
        virtual_memory_usage_percent = $virtualMemoryPercent
    }
}

Write-DiagUsbJson -InputObject $result
