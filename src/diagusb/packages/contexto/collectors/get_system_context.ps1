# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
# Deteccion automatica del contexto del sistema: notebook, desktop o servidor

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

$result = New-DiagUsbCollectorResult -CollectorId 'system_context' -ScriptBlock {
    $context = [ordered]@{
        system_type = 'unknown'
        form_factor = 'unknown'
        is_virtual = $false
        manufacturer = ''
        model = ''
        domain = ''
        has_battery = $false
        has_wifi = $false
        processor_family = ''
        total_memory_gb = 0
        os_type = 'workstation'
        os_version = ''
        uptime_hours = 0
        is_domain_member = $false
    }

    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction SilentlyContinue
    if ($null -ne $computerSystem) {
        $context.manufacturer = "$($computerSystem.Manufacturer)"
        $context.model = "$($computerSystem.Model)"
        $context.domain = "$($computerSystem.Domain)"
        $context.total_memory_gb = [int]($computerSystem.TotalPhysicalMemory / 1GB)
        $context.is_domain_member = [bool]$computerSystem.PartOfDomain
        $context.is_virtual = Test-DiagUsbVirtual -Manufacturer $context.manufacturer -Model $context.model
    }

    $battery = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue
    if ($null -ne $battery) {
        $context.has_battery = $true
    }

    $chassis = Get-CimInstance -ClassName Win32_SystemEnclosure -ErrorAction SilentlyContinue
    if ($null -ne $chassis) {
        $chassisTypes = @(Get-DiagUsbPropertyValue -InputObject $chassis -PropertyName 'ChassisTypes')
        if ($chassisTypes.Count -gt 0 -and $null -ne $chassisTypes[0]) {
            if (9 -in $chassisTypes -or 10 -in $chassisTypes) {
                $context.form_factor = 'laptop'
            } elseif (3 -in $chassisTypes -or 6 -in $chassisTypes -or 7 -in $chassisTypes) {
                $context.form_factor = 'tower'
            } elseif (12 -in $chassisTypes) {
                $context.form_factor = 'rack'
            } elseif (17 -in $chassisTypes -or 18 -in $chassisTypes) {
                $context.form_factor = 'blade'
            } elseif (23 -in $chassisTypes) {
                $context.form_factor = 'rack'
            }
        }
    }

    $processor = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction SilentlyContinue) | Select-Object -First 1
    if ($null -ne $processor) {
        $procName = "$($processor.Name)".ToLower()
        $context.processor_family = "$($processor.Name)"

        if ($procName -match 'xeon|epyc') {
            $context.system_type = 'server'
        }
        elseif ($procName -match 'core\s*(i[3-9]|[1-9])|core\s*2\s*duo|celeron|pentium|ryzen') {
            if ($context.system_type -eq 'unknown') {
                $context.system_type = $(if ($context.form_factor -eq 'laptop' -or $context.has_battery) { 'notebook' } else { 'desktop' })
            }
        }
    }

    $netAdapters = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.PhysicalMediaType -match 'Wireless|Wi-Fi|802\.11' }
    if ($null -ne $netAdapters) {
        $context.has_wifi = $true
        if ($context.system_type -eq 'unknown') {
            $context.system_type = 'notebook'
        }
    }

    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue
    if ($null -ne $os) {
        $context.os_version = "$($os.Caption) $($os.Version)"

        $lastBoot = Get-DiagUsbPropertyValue -InputObject $os -PropertyName 'LastBootUpTime'
        if ($lastBoot) {
            $context.uptime_hours = [int]((Get-Date) - ([DateTime]$lastBoot)).TotalHours
        }

        if ("$($os.Caption)" -match 'Server') {
            $context.os_type = 'server'
            if ($context.system_type -eq 'unknown') {
                $context.system_type = 'server'
            }
        }
    }

    if ($context.system_type -eq 'unknown') {
        if ($context.is_virtual -and $context.total_memory_gb -ge 8) {
            $context.system_type = 'server'
        }
        elseif ($context.has_battery) {
            $context.system_type = 'notebook'
        }
        else {
            $context.system_type = 'desktop'
        }
    }

    return $context
}

Write-DiagUsbJson -InputObject $result
