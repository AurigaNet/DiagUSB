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
    $monitors = @(Get-CimInstance -ClassName Win32_DesktopMonitor -ErrorAction SilentlyContinue)
    $monitorIds = @()
    try {
        $monitorIds = @(Get-CimInstance -Namespace 'root\wmi' -ClassName WmiMonitorID -ErrorAction Stop)
    }
    catch {
        $monitorIds = @()
    }
    $usbDevices = @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.PNPDeviceID -like 'USB\*' } | Sort-Object -Property Name)
    $csproduct = @(Get-CimInstance -ClassName Win32_ComputerSystemProduct)
    $enclosure = @(Get-CimInstance -ClassName Win32_SystemEnclosure -ErrorAction SilentlyContinue)
    $esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $firmwareType = [string]$env:firmware_type
    if (-not $firmwareType) { $firmwareType = 'desconocido' }
    $secureBoot = 'no_aplica'
    if ($firmwareType -ieq 'UEFI') {
        try {
            $secureBoot = if (Confirm-SecureBootUEFI) { 'activado' } else { 'desactivado' }
        }
        catch {
            $secureBoot = 'requiere_admin'
        }
    }
    $tpmEstado = 'requiere_admin'
    $tpmVersion = ''
    if ($esAdmin) {
        try {
            $tpm = @(Get-CimInstance -Namespace 'root\cimv2\Security\MicrosoftTpm' -ClassName Win32_Tpm -ErrorAction Stop)
            if ($tpm.Count -gt 0) {
                $tpmEstado = 'presente'
                $tpmVersion = [string]$tpm[0].SpecVersion
            }
            else { $tpmEstado = 'no_presente' }
        }
        catch {
            $tpmEstado = 'requiere_admin'
        }
    }
    $discoFisicos = @{}
    try {
        Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
            $discoFisicos[[string]$_.DeviceId] = $_
        }
    }
    catch { }
    $chassisNombres = @{
        1  = 'Otro'
        2  = 'Desconocido'
        3  = 'Escritorio'
        4  = 'Escritorio compacto'
        5  = 'Pizza box'
        6  = 'Mini torre'
        7  = 'Torre'
        8  = 'Portable'
        9  = 'Laptop'
        10 = 'Notebook'
        11 = 'De mano'
        12 = 'Estacion de acoplamiento'
        13 = 'Todo en uno'
        14 = 'Subnotebook'
        24 = 'PC de mesa compacto'
        30 = 'Tableta'
        31 = 'Convertible'
        32 = 'Extraible'
    }
    $machineGuid = [string](Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid -ErrorAction SilentlyContinue).MachineGuid
    $macsFisicas = @()
    foreach ($n in $nets) {
        $desc = ([string]$n.Name + ' ' + [string]$n.Description)
        if ($desc -match 'bluetooth|vpn|virtual|vmware|virtualbox|hyper-?v|tap|tunnel|teredo|loopback|wan miniport') { continue }
        if ([string]$n.PNPDeviceID -like 'usb\*') { continue }
        $mac = [string]$n.MACAddress
        if ($mac) { $macsFisicas += $mac }
    }
    $discoArranque = ''
    foreach ($disco in $disks) {
        $particiones = @(Get-CimAssociatedInstance -InputObject $disco -ResultClassName Win32_DiskPartition -ErrorAction SilentlyContinue)
        foreach ($part in $particiones) {
            $logicos = @(Get-CimAssociatedInstance -InputObject $part -ResultClassName Win32_LogicalDisk -ErrorAction SilentlyContinue)
            if (@($logicos | Where-Object { $_.DeviceID -eq $env:SystemDrive })) {
                $discoArranque = [string]$disco.SerialNumber
                break
            }
        }
        if ($discoArranque) { break }
    }

    return [ordered]@{
        identidad = [ordered]@{
            smbios_uuid = $(if ($csproduct) { [string]$csproduct[0].UUID } else { '' })
            system_serial = $(if ($csproduct) { [string]$csproduct[0].IdentifyingNumber } else { '' })
            chassis_serial = $(if ($enclosure) { [string]$enclosure[0].SerialNumber } else { '' })
            chassis_asset_tag = $(if ($enclosure) { [string]$enclosure[0].SMBIOSAssetTag } else { '' })
            machine_guid = $machineGuid
            macs_fisicas = @($macsFisicas)
            disco_arranque = $discoArranque
        }
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
                smbios_version = "$($_.SMBIOSMajorVersion).$($_.SMBIOSMinorVersion)"
                release_date_utc = Convert-DiagUsbDateTime -Value $_.ReleaseDate
                serial_number = $_.SerialNumber
            }
        })
        firmware = [ordered]@{
            modo_arranque = $firmwareType
            secure_boot = $secureBoot
            tpm = $tpmEstado
            tpm_version = $tpmVersion
            fabricante = $(if ($bios) { [string]$bios[0].Manufacturer } else { '' })
            version = $(if ($bios) { [string]$bios[0].SMBIOSBIOSVersion } else { '' })
            fecha_utc = $(if ($bios) { Convert-DiagUsbDateTime -Value $bios[0].ReleaseDate } else { $null })
        }
        enclosure = [ordered]@{
            chassis_types = @($enclosure | ForEach-Object { $_.ChassisTypes } | ForEach-Object { [string]$_ })
            chassis_descriptions = @($enclosure | ForEach-Object { $_.ChassisTypes } |
                Where-Object { $chassisNombres.ContainsKey([int]$_) } |
                ForEach-Object { $chassisNombres[[int]$_] })
            manufacturer = $(if ($enclosure) { [string]$enclosure[0].Manufacturer } else { '' })
        }
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
                device_locator = $_.DeviceLocator
                bank_label = $_.BankLabel
                capacity_bytes = $_.Capacity
                speed_mhz = $_.Speed
                configured_clock_speed_mhz = $_.ConfiguredClockSpeed
                manufacturer = $_.Manufacturer
                part_number = $_.PartNumber
                serial_number = $_.SerialNumber
                memory_type = $_.MemoryType
                form_factor = $_.FormFactor
            }
        })
        monitors = @($monitors | ForEach-Object {
            [ordered]@{
                device_id = $_.DeviceID
                name = $_.Name
                manufacturer = $_.MonitorManufacturer
                monitor_type = $_.MonitorType
                screen_width = $_.ScreenWidth
                screen_height = $_.ScreenHeight
                availability = $_.Availability
                pnp_device_id = $_.PNPDeviceID
            }
        })
        monitor_ids = @($monitorIds | ForEach-Object {
            [ordered]@{
                instance_name = $_.InstanceName
                manufacturer = Convert-DiagUsbUint16Text -Value $_.ManufacturerName
                friendly_name = Convert-DiagUsbUint16Text -Value $_.UserFriendlyName
                serial_number = Convert-DiagUsbUint16Text -Value $_.SerialNumberID
                year_of_manufacture = $_.YearOfManufacture
                week_of_manufacture = $_.WeekOfManufacture
                active = $_.Active
            }
        })
        usb_devices = @($usbDevices | ForEach-Object {
            [ordered]@{
                name = $_.Name
                description = $_.Description
                manufacturer = $_.Manufacturer
                device_class = $_.PNPClass
                service = $_.Service
                status = $_.Status
                config_manager_error_code = $_.ConfigManagerErrorCode
                present = $_.Present
                pnp_device_id = $_.PNPDeviceID
            }
        })
        disk_drives = @($disks | ForEach-Object {
            $fi = $discoFisicos[[string]$_.Index]
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
                physical_media_type = $(if ($fi) { [string]$fi.MediaType } else { 'desconocido' })
                bus_type = $(if ($fi) { [string]$fi.BusType } else { 'desconocido' })
                health_status = $(if ($fi) { [string]$fi.HealthStatus } else { 'no_disponible' })
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