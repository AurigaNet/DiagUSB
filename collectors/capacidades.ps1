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

$result = New-DiagUsbCollectorResult -CollectorId 'capacidades' -TimeoutSeconds 25 -ScriptBlock {
    function Test-DiagUsbVirtualPrinter {
        param($Printer)

        $name = [string]$Printer.Name
        $driver = [string]$Printer.DriverName
        $port = [string]$Printer.PortName

        if ($port -match '^(PORTPROMPT:|SHRFAX:|nul:|FILE:)') { return $true }
        if ($port -match 'pdf|xps|onenote|fax') { return $true }
        if ($driver -match 'pdf|xps|onenote|fax|send to|microsoft print') { return $true }
        if ($name -match 'pdf|xps|onenote|fax|send to|microsoft print') { return $true }
        return $false
    }

    $printerQueryOk = $true
    $printerError = $null
    $printers = @()
    try {
        $printers = @(Get-CimInstance -ClassName Win32_Printer -ErrorAction Stop | ForEach-Object {
            [ordered]@{
                name = [string]$_.Name
                driver_name = [string]$_.DriverName
                port_name = [string]$_.PortName
                default = [bool]$_.Default
                network = [bool]$_.Network
                local = [bool]$_.Local
                work_offline = [bool]$_.WorkOffline
                printer_status = $_.PrinterStatus
                detected_error_state = $_.DetectedErrorState
                virtual = [bool](Test-DiagUsbVirtualPrinter $_)
            }
        })
    }
    catch {
        $printerQueryOk = $false
        $printerError = $_.Exception.Message
    }

    $spooler = Get-Service -Name Spooler -ErrorAction SilentlyContinue
    $realPrinters = @($printers | Where-Object { -not $_.virtual })
    $virtualPrinters = @($printers | Where-Object { $_.virtual })

    $networkQueryOk = $true
    $networkError = $null
    $adapters = @()
    try {
        $adaptersRaw = @(Get-NetAdapter -ErrorAction Stop | Where-Object { $_.Status -ne 'Not Present' })

        $ipv4PorIndice = @{}
        foreach ($ip in @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)) {
            $indice = [int]$ip.InterfaceIndex
            if (-not $ipv4PorIndice.ContainsKey($indice)) { $ipv4PorIndice[$indice] = @() }
            $ipv4PorIndice[$indice] += [string]$ip.IPAddress
        }

        $gatewayPorIndice = @{}
        foreach ($ruta in @(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)) {
            $indice = [int]$ruta.InterfaceIndex
            if (-not $gatewayPorIndice.ContainsKey($indice)) { $gatewayPorIndice[$indice] = @() }
            $gatewayPorIndice[$indice] += [string]$ruta.NextHop
        }

        foreach ($a in $adaptersRaw) {
            $indice = [int]$a.ifIndex
            $ipv4 = @()
            if ($ipv4PorIndice.ContainsKey($indice)) { $ipv4 = @($ipv4PorIndice[$indice]) }
            $gateways = @()
            if ($gatewayPorIndice.ContainsKey($indice)) { $gateways = @($gatewayPorIndice[$indice]) }
            $status = [string]$a.Status

            $adapters += [ordered]@{
                name = [string]$a.Name
                description = [string]$a.InterfaceDescription
                kind = Get-DiagUsbConnectionKind $a
                status = $status
                enabled = [bool]($status -ne 'Disabled')
                link_up = [bool]($status -eq 'Up')
                virtual = [bool]$a.Virtual
                media_type = [string]$a.PhysicalMediaType
                speed = [string]$a.LinkSpeed
                ipv4 = $ipv4
                gateways = $gateways
                has_ipv4 = [bool]($ipv4.Count -gt 0)
                has_gateway = [bool]($gateways.Count -gt 0)
            }
        }
    }
    catch {
        $networkQueryOk = $false
        $networkError = $_.Exception.Message
    }

    $fisicas = @($adapters | Where-Object { -not $_.virtual })
    $base = $fisicas
    $soloVirtuales = $false
    if ($fisicas.Count -eq 0 -and $adapters.Count -gt 0) {
        $base = $adapters
        $soloVirtuales = $true
    }
    $enlaces = @($base | Where-Object { $_.link_up })
    $wifi = @($base | Where-Object { $_.kind -eq 'wifi' })
    $wifiHabilitadas = @($wifi | Where-Object { $_.enabled })

    $tiposPresentes = @($base | ForEach-Object { $_.kind } | Sort-Object -Unique)
    $tiposActivos = @($enlaces | ForEach-Object { $_.kind } | Sort-Object -Unique)
    $nombresEnlace = @($enlaces | ForEach-Object { $_.name })

    $bateriaQueryOk = $true
    $bateriaError = $null
    $baterias = @()
    try {
        $baterias = @(Get-CimInstance -ClassName Win32_Battery -ErrorAction Stop)
    }
    catch {
        $bateriaQueryOk = $false
        $bateriaError = $_.Exception.Message
    }

    $lhmUrl = Get-DiagUsbLhmUrl
    $lhmProcess = @(Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -like '*LibreHardwareMonitor*' })
    $cpuQueryOk = $false
    $cpuTemperature = $null
    $cpuError = $null
    try {
        $cpuTemperature = Get-DiagUsbLhmCpuTemperature -TimeoutSec 2
        $cpuQueryOk = $true
        if ($null -eq $cpuTemperature) {
            $cpuError = 'LibreHardwareMonitor responde, pero no expone temperatura del CPU. Verifique PawnIO y ejecute LHM como administrador.'
        }
    }
    catch {
        $cpuError = $_.Exception.Message
    }
    if (-not $cpuQueryOk) {
        if ($lhmProcess.Count -gt 0) {
            $cpuError = 'LibreHardwareMonitor esta abierto, pero el servidor web no responde. Active Options > Remote Web Server > Run.'
        }
        else {
            $cpuError = 'LibreHardwareMonitor no esta activo. Abralo y active Options > Remote Web Server > Run (puerto 8085).'
        }
    }

    [ordered]@{
        printer_query_ok = $printerQueryOk
        printer_error = $printerError
        printers = [ordered]@{
            total = $printers.Count
            real = $realPrinters.Count
            virtual = $virtualPrinters.Count
            offline = @($realPrinters | Where-Object { $_.work_offline }).Count
            spooler = $(if ($spooler) { [string]$spooler.Status } else { 'Unknown' })
            items = $realPrinters
        }
        network_query_ok = $networkQueryOk
        network_error = $networkError
        network = [ordered]@{
            adapters = $adapters
            physical_count = $fisicas.Count
            virtual_only = $soloVirtuales
            has_adapter = [bool]($base.Count -gt 0)
            has_link = [bool]($enlaces.Count -gt 0)
            has_ipv4 = [bool](@($enlaces | Where-Object { $_.has_ipv4 }).Count -gt 0)
            has_gateway = [bool](@($enlaces | Where-Object { $_.has_gateway }).Count -gt 0)
            present_kinds = $tiposPresentes
            active_kinds = $tiposActivos
            link_names = $nombresEnlace
            wifi_present = [bool]($wifi.Count -gt 0)
            wifi_enabled = [bool]($wifiHabilitadas.Count -gt 0)
            wifi_link = [bool](@($wifi | Where-Object { $_.link_up }).Count -gt 0)
            wifi_connected = [bool](@($wifi | Where-Object { $_.link_up -and $_.has_ipv4 }).Count -gt 0)
        }
        battery = [ordered]@{
            query_ok = $bateriaQueryOk
            error = $bateriaError
            present = [bool]($baterias.Count -gt 0)
            count = $baterias.Count
        }
        cpu_temperature = [ordered]@{
            query_ok = $cpuQueryOk
            available = [bool]($cpuQueryOk -and $null -ne $cpuTemperature)
            url = $lhmUrl
            error = $cpuError
            process_running = [bool]($lhmProcess.Count -gt 0)
            cpu_name = $(if ($null -ne $cpuTemperature) { [string]$cpuTemperature.cpu_name } else { $null })
            max_temp_c = $(if ($null -ne $cpuTemperature) { $cpuTemperature.max_temp_c } else { $null })
            package_temp_c = $(if ($null -ne $cpuTemperature) { $cpuTemperature.package_temp_c } else { $null })
            sensor_count = $(if ($null -ne $cpuTemperature) { $cpuTemperature.sensor_count } else { 0 })
        }
    }
}

Write-DiagUsbJson -InputObject $result
