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

$result = New-DiagUsbCollectorResult -CollectorId 'os' -ScriptBlock {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem

    $lastBoot = Get-DiagUsbPropertyValue -InputObject $os -PropertyName 'LastBootUpTime'
    $uptime = if ($lastBoot) { (Get-Date) - ([DateTime]$lastBoot) } else { $null }

    $osInfo = [ordered]@{
        caption = $os.Caption
        version = $os.Version
        build_number = $os.BuildNumber
        display_version = Get-DiagUsbPropertyValue -InputObject $os -PropertyName 'DisplayVersion'
        service_pack_major = $os.ServicePackMajorVersion
        service_pack_minor = $os.ServicePackMinorVersion
        architecture = $os.OSArchitecture
        last_boot_up_time_utc = $(if ($lastBoot) { ([DateTime]$lastBoot).ToUniversalTime().ToString('o') } else { $null })
        local_date_time = $(if ($os.LocalDateTime) { ([DateTime]$os.LocalDateTime).ToString('o') } else { $null })
        time_zone = [TimeZoneInfo]::Local.StandardName
        daylight_saving_active = [TimeZoneInfo]::Local.IsDaylightSavingTime([DateTime]::Now)
        system_drive = $os.SystemDrive
        windows_directory = $os.WindowsDirectory
        total_visible_memory_kb = $os.TotalVisibleMemorySize
        free_physical_memory_kb = $os.FreePhysicalMemory
        total_virtual_memory_kb = $os.TotalVirtualMemorySize
        free_virtual_memory_kb = $os.FreeVirtualMemory
        total_page_file_kb = Get-DiagUsbPropertyValue -InputObject $os -PropertyName 'TotalSwapSpaceSize'
        free_page_file_kb = Get-DiagUsbPropertyValue -InputObject $os -PropertyName 'FreeSwapSpaceSize'
        number_of_processes = $os.NumberOfProcesses
        max_number_of_processes = $os.MaxNumberOfProcesses
        number_of_users = $os.NumberOfUsers
        machine_name = $os.CSName
    }

    $systemInfo = if ($cs) {
        [ordered]@{
            manufacturer = $cs.Manufacturer
            model = $cs.Model
            name = $cs.Name
            number_of_processors = $cs.NumberOfProcessors
            number_of_logical_processors = $cs.NumberOfLogicalProcessors
            total_physical_memory_kb = $cs.TotalPhysicalMemory
            domain = $cs.Domain
            domain_role = $cs.DomainRole
            part_of_domain = $cs.PartOfDomain
            hypervisor_present = $cs.HypervisorPresent
        }
    } else { $null }

    return [ordered]@{
        operating_system = $osInfo
        system_info = $systemInfo
        uptime = $(if ($uptime) { $uptime.ToString() } else { $null })
        uptime_seconds = $(if ($uptime) { [math]::Round($uptime.TotalSeconds) } else { $null })
    }
}

Write-DiagUsbJson -InputObject $result
