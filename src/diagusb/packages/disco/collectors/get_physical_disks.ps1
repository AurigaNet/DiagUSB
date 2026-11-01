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

$result = New-DiagUsbCollectorResult -CollectorId 'physical_disks' -TimeoutSeconds 30 -ScriptBlock {
    # El modulo Storage depende del servicio smphost. Si esta detenido,
    # Get-PhysicalDisk devuelve una lista vacia sin error y el equipo
    # aparentaria no tener discos. Se consulta primero el servicio.
    $proveedorStorage = $true
    try {
        $smphost = Get-Service -Name 'smphost' -ErrorAction SilentlyContinue
        if ($null -ne $smphost -and $smphost.Status -ne 'Running') {
            $proveedorStorage = $false
        }
    }
    catch {
        $proveedorStorage = $true
    }

    $physicalDisks = @()
    if ($proveedorStorage) {
        $physicalDisks = @(Get-PhysicalDisk -ErrorAction SilentlyContinue)
    }

    # Respaldo sin el modulo Storage: Win32_DiskDrive + SMART.
    if ($physicalDisks.Count -eq 0) {
        $wmiDisks = @(Get-CimInstance -ClassName Win32_DiskDrive -ErrorAction SilentlyContinue |
            Sort-Object -Property Index)
        if ($wmiDisks.Count -eq 0) {
            throw 'DIAGUSB_NOT_AVAILABLE: no se pudieron leer los discos fisicos (Storage y Win32_DiskDrive sin datos).'
        }

        $smart = @{}
        try {
            foreach ($sensor in @(Get-CimInstance -Namespace 'root\wmi' `
                    -ClassName 'MSStorageDriver_FailurePredictStatus' `
                    -ErrorAction SilentlyContinue)) {
                if ($null -ne $sensor -and $sensor.InstanceName) {
                    $smart[[string]$sensor.InstanceName] = $sensor
                }
            }
        }
        catch {
            $smart = @{}
        }

        $items = @()
        foreach ($disk in $wmiDisks) {
            $serial = ([string]$disk.SerialNumber).Trim()
            $estado = [string]$disk.Status
            $prediccion = $null

            $smartInfo = $null
            $claveSmart = "$([string]$disk.PNPDeviceID)_0"
            if ($smart.ContainsKey($claveSmart)) {
                $smartInfo = $smart[$claveSmart]
            }
            else {
                foreach ($clave in $smart.Keys) {
                    if ($serial -and $clave -like "*$serial*") {
                        $smartInfo = $smart[$clave]
                        break
                    }
                }
            }
            if ($null -ne $smartInfo) {
                $prediccion = [bool]$smartInfo.PredictFailure
            }

            $items += [ordered]@{
                device_id = [string]$disk.Index
                serial_number = $serial
                friendly_name = ([string]$disk.Model).Trim()
                bus_type = [string]$disk.InterfaceType
                media_type = 'Unknown'
                media_type_detalle = [string]$disk.MediaType
                size_gb = [math]::Round(([double]$disk.Size) / 1GB, 2)
                health_status = $(if ($prediccion -eq $true) { 'Warning' } else { $estado })
                operational_status = $(if ($estado -eq 'OK') { 'OK' } else { $estado })
                reliability = $null
                reliability_motivo = 'solo estado SMART basico; sin horas, temperatura ni sectores reasignados'
                power_on_hours = $null
                temperature = $null
                reallocated_sectors = $null
                smart_predict_failure = $prediccion
            }
        }

        return $items
    }

    $jobs = [ordered]@{}
    foreach ($disk in $physicalDisks) {
        if ("$($disk.BusType)" -eq 'USB') { continue }
        $devId = "$($disk.DeviceId)"
        $jobs[$devId] = Start-Job -ScriptBlock {
            param($target)
            $d = @(Get-PhysicalDisk -ErrorAction SilentlyContinue) |
                Where-Object { "$($_.DeviceId)" -eq $target } | Select-Object -First 1
            if ($null -eq $d) { return }
            @(Get-StorageReliabilityCounter -PhysicalDisk $d -ErrorAction SilentlyContinue) |
                Select-Object -First 1
        } -ArgumentList "$($disk.DeviceId)"
    }

    $completados = @{}
    if ($jobs.Count -gt 0) {
        foreach ($job in @(Wait-Job -Job @($jobs.Values) -Timeout 10)) {
            $completados[$job.Id] = $true
        }
    }

    $counters = @{}
    $vencidos = @{}
    foreach ($devId in $jobs.Keys) {
        $job = $jobs[$devId]
        if ($completados.ContainsKey($job.Id)) {
            $counters[$devId] = @(Receive-Job -Job $job -ErrorAction SilentlyContinue) |
                Select-Object -First 1
        }
        else {
            $vencidos[$devId] = $true
        }
    }
    foreach ($job in $jobs.Values) {
        Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue | Out-Null
    }

    $items = @()
    foreach ($disk in $physicalDisks) {
        $devId = "$($disk.DeviceId)"
        $busType = "$($disk.BusType)"
        $counter = $null
        $motivo = $null

        if ($busType -eq 'USB') {
            $motivo = 'no aplica a unidades USB'
        }
        elseif ($vencidos.ContainsKey($devId)) {
            $motivo = 'sin respuesta en 10 s'
        }
        else {
            $counter = $counters[$devId]
            if ($null -eq $counter) {
                $motivo = 'sin datos de confiabilidad'
            }
        }

        $reliability = $null
        $powerOnHours = $null
        $temperature = $null
        $reallocatedSectors = $null
        if ($null -ne $counter) {
            $powerOnHours = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'PowerOnHours'
            $temperature = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'Temperature'
            $reallocatedSectors = Get-DiagUsbPropertyValue -InputObject $counter -PropertyName 'ReallocatedSectorsCount'
            $reliability = [ordered]@{
                power_on_hours = $powerOnHours
                temperature = $temperature
                reallocated_sectors = $reallocatedSectors
            }
        }

        $items += [ordered]@{
            device_id = $disk.DeviceId
            serial_number = $disk.SerialNumber
            friendly_name = $disk.FriendlyName
            bus_type = $busType
            media_type = switch ($disk.MediaType) { 0 { 'Unspecified' } 3 { 'HDD' } 4 { 'SSD' } 5 { 'SCM' } default { 'Unknown' } }
            size_gb = [math]::Round($disk.Size / 1GB, 2)
            health_status = "$($disk.HealthStatus)"
            operational_status = "$($disk.OperationalStatus)"
            reliability = $reliability
            reliability_motivo = $motivo
            power_on_hours = $powerOnHours
            temperature = $temperature
            reallocated_sectors = $reallocatedSectors
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
