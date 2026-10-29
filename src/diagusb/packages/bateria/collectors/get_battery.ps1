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

$result = New-DiagUsbCollectorResult -CollectorId 'battery' -TimeoutSeconds 25 -ScriptBlock {
    $bateriasCim = @(Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue)
    if ($bateriasCim.Count -eq 0) {
        throw 'DIAGUSB_NOT_AVAILABLE: no se detecta ninguna bateria en este equipo.'
    }

    $principal = $bateriasCim[0]
    $estados = @{
        1  = 'Otro'
        2  = 'Desconocido'
        3  = 'Carga completa'
        4  = 'Carga baja'
        5  = 'Carga criticamente baja'
        6  = 'Cargando'
        7  = 'Cargando, alta'
        8  = 'Cargando, baja'
        9  = 'Cargando, criticamente baja'
        10 = 'Sin definir'
        11 = 'Carga parcial'
    }
    $codigoEstado = $principal.BatteryStatus
    $estado = [string]$codigoEstado
    if ($estados.ContainsKey([int]$codigoEstado)) { $estado = $estados[[int]$codigoEstado] }

    $carga = $null
    $cargaRaw = $principal.EstimatedChargeRemaining
    if ($cargaRaw -isnot [bool] -and $null -ne $cargaRaw) {
        try { $carga = [math]::Round([double]$cargaRaw, 1) } catch { $carga = $null }
    }

    # Reporte de bateria de powercfg: diseno frente a carga plena y ciclos.
    # El XML se crea en la carpeta temporal y SE BORRA SIEMPRE (finally).
    $notaReporte = ''
    $infoBaterias = @()
    $reporte = Join-Path ([System.IO.Path]::GetTempPath()) (
        'diagusb_bateria_' + [Guid]::NewGuid().ToString('N') + '.xml')
    try {
        $salida = & powercfg.exe /batteryreport /XML /OUTPUT $reporte 2>&1
        if (-not (Test-Path -LiteralPath $reporte)) {
            $notaReporte = 'powercfg no genero el reporte: ' + (($salida | Out-String).Trim())
        }
        else {
            $infoBaterias = @(Get-DiagUsbBatteryReportInfo -XmlPath $reporte)
            if ($infoBaterias.Count -eq 0) {
                $notaReporte = 'El reporte no incluye datos de capacidad.'
            }
        }
    }
    catch {
        $notaReporte = 'No se pudo leer el reporte de bateria: ' + $_.Exception.Message
    }
    finally {
        Remove-Item -LiteralPath $reporte -Force -ErrorAction SilentlyContinue
    }

    $reporteElegido = $null
    foreach ($candidato in @($infoBaterias | Where-Object {
            $_.design_capacity_mwh -and $_.full_charge_capacity_mwh })) {
        if ($null -eq $reporteElegido) { $reporteElegido = $candidato }
    }

    $diseno = $null
    $plena = $null
    $desgaste = $null
    $ciclos = $null
    $lote = ''
    if ($null -ne $reporteElegido) {
        $diseno = $reporteElegido.design_capacity_mwh
        $plena = $reporteElegido.full_charge_capacity_mwh
        $ciclos = $reporteElegido.ciclos
        $lote = [string]$reporteElegido.id
        if ($diseno -and $plena) {
            $desgaste = [math]::Round((1.0 - ($plena / $diseno)) * 100.0, 1)
            if ($desgaste -lt 0) { $desgaste = 0.0 }
        }
    }

    return [ordered]@{
        presente = $true
        carga_percent = $carga
        battery_status = $codigoEstado
        estado = $estado
        design_capacity_mwh = $diseno
        full_charge_capacity_mwh = $plena
        desgaste_percent = $desgaste
        ciclos = $ciclos
        fuente_capacidad = $(if ($null -ne $reporteElegido) { 'powercfg' } else { 'no_disponible' })
        nota_reporte = $notaReporte
        items = $infoBaterias
    }
}

Write-DiagUsbJson -InputObject $result
