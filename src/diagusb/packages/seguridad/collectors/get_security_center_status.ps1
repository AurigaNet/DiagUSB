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

$result = New-DiagUsbCollectorResult -CollectorId 'security_center' -ScriptBlock {
    $securityProducts = @()

    try {
        $antivirusProducts = Get-CimInstance -Namespace Root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop
        foreach ($product in $antivirusProducts) {
            $state = ($product.productState -shr 16) -band 0xFF
            $securityProducts += [ordered]@{
                type = 'antivirus'
                display_name = $product.displayName
                instance_guid = $product.instanceGuid
                product_state = $product.productState
                enabled = ($product.productState -band 0x1000) -eq 0
                up_to_date = $state -eq 0
                state_description = switch ($state) {
                    0 { 'Actualizado' }
                    16 { 'En espera de actualizaciones' }
                    32 { 'Actualizacion en progreso' }
                    48 { 'No actualizado' }
                    64 { 'Actualizacion fallida' }
                    default { 'Desconocido' }
                }
            }
        }
    }
    catch {
        Write-Warning "No se pudo obtener productos antivirus via WMI: $($_.Exception.Message)"
    }

    try {
        $antispywareProducts = Get-CimInstance -Namespace Root/SecurityCenter2 -ClassName AntiSpywareProduct -ErrorAction Stop
        foreach ($product in $antispywareProducts) {
            $state = ($product.productState -shr 16) -band 0xFF
            $securityProducts += [ordered]@{
                type = 'antispyware'
                display_name = $product.displayName
                instance_guid = $product.instanceGuid
                product_state = $product.productState
                enabled = ($product.productState -band 0x1000) -eq 0
                up_to_date = $state -eq 0
                state_description = switch ($state) {
                    0 { 'Actualizado' }
                    16 { 'En espera de actualizaciones' }
                    32 { 'Actualizacion en progreso' }
                    48 { 'No actualizado' }
                    64 { 'Actualizacion fallida' }
                    default { 'Desconocido' }
                }
            }
        }
    }
    catch {
        Write-Warning "No se pudo obtener productos antispyware via WMI: $($_.Exception.Message)"
    }

    return $securityProducts
}

Write-DiagUsbJson -InputObject $result
