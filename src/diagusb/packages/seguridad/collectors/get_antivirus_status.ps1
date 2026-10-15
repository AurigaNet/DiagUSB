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
        $antivirusInfo += [ordered]@{
            source = 'Windows Defender'
            enabled = [bool]$mpStatus.AntivirusEnabled
            real_time_protection = [bool]$mpStatus.RealTimeProtectionEnabled
            behavior_monitor = [bool]$mpStatus.BehaviorMonitorEnabled
            ioav_protection = [bool]$mpStatus.IOAVProtectionEnabled
            signatures_enabled = [bool]$mpStatus.AntispywareEnabled
            signature_version = $mpStatus.AntivirusSignatureVersion
            signature_age_days = if ($mpStatus.AntivirusSignatureLastUpdated) {
                ((Get-Date) - $mpStatus.AntivirusSignatureLastUpdated).Days
            } else { $null }
            signature_last_updated = if ($mpStatus.AntivirusSignatureLastUpdated) {
                Convert-DiagUsbDateTime -Value $mpStatus.AntivirusSignatureLastUpdated
            } else { $null }
            computer_antispyware_enabled = [bool]$mpStatus.AntispywareEnabled
            antivirus_configured = [bool]$mpStatus.AntivirusConfigured
            antispyware_configured = [bool]$mpStatus.AntispywareConfigured
            real_time_contamination = [bool]$mpStatus.RealTimeContaminationProtection
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
                enabled = ($product.productState -band 0x1000) -eq 0
                up_to_date = (($product.productState -shr 16) -band 0xFF) -eq 0
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
