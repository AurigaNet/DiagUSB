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

$result = New-DiagUsbCollectorResult -CollectorId 'hardware' -ScriptBlock {
    $computers = @(Get-CimInstance -ClassName Win32_ComputerSystem)
    $bios = @(Get-CimInstance -ClassName Win32_Bios)
    $baseboards = @(Get-CimInstance -ClassName Win32_BaseBoard)
    $cpus = @(Get-CimInstance -ClassName Win32_Processor)
    $gpus = @(Get-CimInstance -ClassName Win32_VideoController)
    $mems = @(Get-CimInstance -ClassName Win32_PhysicalMemory)
    $disks = @(Get-CimInstance -ClassName Win32_DiskDrive)
    $nets = @(Get-CimInstance -ClassName Win32_NetworkAdapter) | Where-Object { $_.PhysicalAdapter -eq $true } | Sort-Object -Property Name

    return [ordered]@{
        computer_system = @($computers | ForEach-Object {
            [ordered]@{
                manufacturer = $_.Manufacturer
                model = $_.Model
                domain = $_.Domain
                domain_role = $_.DomainRole
                pc_system_type = $_.PCSystemType
                pc_system_type_description = $_.PCSystemType
                total_physical_memory_bytes = $_.TotalPhysicalMemory
                nics = $_.NumberOfLogicalProcessors
            }
        })
        bios = @($bios | ForEach-Object {
            [ordered]@{
                manufacturer = $_.Manufacturer
                bios_version = $_.SMBIOSBIOSVersion
                release_date_utc = Convert-DiagUsbDateTime -Value $_.ReleaseDate
                serial_number = $_.SerialNumber
            }
        })
        baseboards = @($baseboards | ForEach-Object {
            [ordered]@{
                manufacturer = $_.Manufacturer
                product = $_.Product
                serial_number = $_.SerialNumber
            }
        })
        processors = @($cpus | ForEach-Object {
            [ordered]@{
                name = $_.Name
                manufacturer = $_.Manufacturer
                description = $_.Description
                number_of_cores = $_.NumberOfCores
                number_of_logical_processors = $_.NumberOfLogicalProcessors
                max_clock_speed_mhz = $_.MaxClockSpeed
                current_clock_speed_mhz = $_.CurrentClockSpeed
                l2_cache_size_kb = $_.L2CacheSize
                l3_cache_size_kb = $_.L3CacheSize
            }
        })
        video_controllers = @($gpus | ForEach-Object {
            [ordered]@{
                name = $_.Name
                adapter_compatibility = $_.AdapterCompatibility
                adapter_ram_bytes = $_.AdapterRAM
                driver_version = $_.DriverVersion
                driver_date_utc = Convert-DiagUsbDateTime -Value $_.DriverDate
                video_processor = $_.VideoProcessor
                current_refresh_rate_hz = $_.CurrentRefreshRate
                current_horizontal_resolution = $_.CurrentHorizontalResolution
                current_vertical_resolution = $_.CurrentVerticalResolution
                video_architecture = $_.VideoArchitecture
            }
        })
        physical_memory = @($mems | ForEach-Object {
            [ordered]@{
                capacity_bytes = $_.Capacity
                speed_mhz = $_.Speed
                manufacturer = $_.Manufacturer
                part_number = $_.PartNumber
                serial_number = $_.SerialNumber
                memory_type = $_.MemoryType
                form_factor = $_.FormFactor
            }
        })
        disk_drives = @($disks | ForEach-Object {
            [ordered]@{
                model = $_.Model
                manufacturer = $_.Manufacturer
                serial_number = $_.SerialNumber
                interface_type = $_.InterfaceType
                MediaType = $_.MediaType
                size_bytes = $_.Size
                partitions = $_.Partitions
                firmware_revision = $_.FirmwareRevision
                status = $_.Status
            }
        })
        network_adapters = @($nets | ForEach-Object {
            [ordered]@{
                name = $_.Name
                adapter_type = $_.AdapterType
                description = $_.Description
                mac_address = $_.MACAddress
                speed_bps = $_.Speed
                net_connection_id = $_.NetConnectionID
                net_connection_status = $_.NetConnectionStatus
                guid = $_.GUID
                pnp_device_id = $_.PNPDeviceID
            }
        })
    }
}

Write-DiagUsbJson -InputObject $result