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

$result = New-DiagUsbCollectorResult -CollectorId 'outdated_drivers' -ScriptBlock {
    $cutoffOld = (Get-Date).AddYears(-5)

    $errorCodes = @{
        1  = 'El dispositivo no esta configurado correctamente'
        10 = 'No se puede encontrar el controlador del dispositivo'
        12 = 'El dispositivo no dispone de recursos suficientes'
        14 = 'El dispositivo no puede funcionar hasta que se reinicie el equipo'
        16 = 'No se pueden determinar todas las capacidades del dispositivo'
        18 = 'Se requiere la reconfiguracion del dispositivo'
        19 = 'El controlador del dispositivo esta danado'
        21 = 'El sistema esta desactivando el dispositivo'
        22 = 'El dispositivo esta usando un recurso de IRQ que ya esta en uso'
        24 = 'El dispositivo no esta presente, no funciona o esta desconectado'
        28 = 'Los controladores del dispositivo no estan instalados'
        31 = 'El dispositivo no puede funcionar porque no puede cargar el controlador'
        32 = 'El dispositivo solicita PNP de 32 bits que no puede usar el driver'
        37 = 'Windows no puede inicializar el controlador del dispositivo'
        39 = 'El registro del dispositivo no tiene la seccion BSS'
        41 = 'Windows no puede cargar el controlador del dispositivo'
        43 = 'Windows ha detenido el dispositivo porque ha informado de problemas'
        47 = 'El dispositivo esta preparado para la retirada en caliente, esperando confirmacion'
        48 = 'El controlador del dispositivo esta bloqueado por otra aplicacion'
        52 = 'Windows no puede verificar la firma digital del dispositivo'
        54 = 'El dispositivo ha sido detenido por reinicio solicitado'
        56 = 'No se podra buscar hasta que el sistema se reinicie'
    }

    $problems = @{}
    try {
        foreach ($ent in @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop)) {
            if ($ent.DeviceID -and $ent.ConfigManagerErrorCode -and $ent.ConfigManagerErrorCode -ne 0) {
                $problems[$ent.DeviceID] = $ent.ConfigManagerErrorCode
            }
        }
    } catch { }

    $list = @()
    foreach ($d in @(Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction Stop)) {
        if (-not $d.DeviceName) { continue }

        $fecha = $null
        if ($d.DriverDate) {
            try { $fecha = [datetime]$d.DriverDate } catch { $fecha = $null }
        }

        $mfr = [string]$d.Manufacturer
        $esSistema = (-not $mfr) -or $mfr -match 'Microsoft|^\(' -or
            $d.DeviceName -match '^(Intel|AMD) Processor$'

        $codigo = 0
        if ($d.DeviceID -and $problems.ContainsKey($d.DeviceID)) {
            $codigo = [int]$problems[$d.DeviceID]
        }

        $esGenerico = $d.DeviceName -match '(?i)basic display|basic render|base system device|generic (usb|pnp|nic|hid|bluetooth|wireless)'
        $antiguo = $fecha -and (-not $esSistema) -and $fecha -lt $cutoffOld

        $motivos = @()
        if ($codigo -ne 0) { $motivos += 'advertencia' }
        if ($esGenerico) { $motivos += 'generico' }
        if ($antiguo) { $motivos += 'antiguo' }
        if ($motivos.Count -eq 0) { continue }

        $list += [ordered]@{
            device_name = $d.DeviceName
            driver_version = $d.DriverVersion
            driver_date = $(if ($fecha) { $fecha.ToString('yyyy-MM-dd') } else { $null })
            manufacturer = $mfr
            config_error_code = $codigo
            config_error_text = $(if ($codigo -ne 0 -and $errorCodes.ContainsKey([int]$codigo)) { $errorCodes[[int]$codigo] } else { $null })
            reasons = $motivos
        }
    }
    $list
}

Write-DiagUsbJson -InputObject $result
