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

$result = New-DiagUsbCollectorResult -CollectorId 'antivirus_status' -ScriptBlock {
    $antivirusInfo = @()

    try {
        $mpStatus = Get-MpComputerStatus -ErrorAction Stop
        $signatureLastUpdated = Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntivirusSignatureLastUpdated'
        $antivirusInfo += [ordered]@{
            source = 'Windows Defender'
            enabled = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntivirusEnabled')
            real_time_protection = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'RealTimeProtectionEnabled')
            behavior_monitor = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'BehaviorMonitorEnabled')
            ioav_protection = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'IOAVProtectionEnabled')
            signatures_enabled = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntispywareEnabled')
            signature_version = Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntivirusSignatureVersion'
            signature_age_days = if ($signatureLastUpdated) {
                ((Get-Date) - $signatureLastUpdated).Days
            } else { $null }
            signature_last_updated = if ($signatureLastUpdated) {
                Convert-DiagUsbDateTime -Value $signatureLastUpdated
            } else { $null }
            computer_antispyware_enabled = [bool](Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntispywareEnabled')
            antivirus_configured = Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntivirusConfigured'
            antispyware_configured = Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'AntispywareConfigured'
            real_time_contamination = Get-DiagUsbPropertyValue -InputObject $mpStatus -PropertyName 'RealTimeContaminationProtection'
        }
    }
    catch {
        if ($_.Exception.Message -notlike '* acceso*' -and $_.Exception.Message -notlike '* denied*') {
            Write-Warning "Windows Defender no disponible: $($_.Exception.Message)"
        }
    }

    try {
        $securityCenterProducts = Get-CimInstance -Namespace Root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction Stop
        foreach ($product in $securityCenterProducts) {
            $antivirusInfo += [ordered]@{
                source = 'WMI SecurityCenter2'
                display_name = $product.displayName
                instance_guid = $product.instanceGuid
                product_state = $product.productState
                enabled = (($product.productState -band 0xF000) -eq 0x1000)
                up_to_date = (($product.productState -band 0xF0) -eq 0)
                signature_status = ($product.productState -band 0xF0)
            }
        }
    }
    catch {
        if ($_.Exception.Message -notlike '* acceso*' -and $_.Exception.Message -notlike '* denied*') {
            Write-Warning "WMI SecurityCenter2 no disponible: $($_.Exception.Message)"
        }
    }

    return $antivirusInfo
}

Write-DiagUsbJson -InputObject $result
