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

$result = New-DiagUsbCollectorResult -CollectorId 'installed_software' -ScriptBlock {
    $apps = @()
    try {
        $keys = @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
        )
        $apps = @(Get-ItemProperty -Path $keys -ErrorAction SilentlyContinue |
            Where-Object {
                $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -and
                -not $_.PSObject.Properties['SystemComponent']
            })
    } catch { $apps = @() }

    $features = @()
    $featuresAvailable = $false
    try {
        $features = @(Get-WindowsOptionalFeature -Online -ErrorAction Stop |
            Where-Object { $_.State -eq 'Enabled' })
        $featuresAvailable = $true
    } catch { $features = @() }

    $roles = @()
    try {
        if (Get-Command Get-WindowsFeature -ErrorAction SilentlyContinue) {
            $roles = @(Get-WindowsFeature -ErrorAction SilentlyContinue |
                Where-Object { $_.Installed -eq $true })
        }
    } catch { $roles = @() }

    $softwareList = @($apps | ForEach-Object {
        $o = $_
        $cruda = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'InstallDate'
        $fecha = $null
        if ($cruda -and [string]$cruda -match '^\d{8}') {
            try {
                $fecha = [datetime]::ParseExact([string]$cruda, 'yyyyMMdd',
                    [System.Globalization.CultureInfo]::InvariantCulture).ToString('o')
            } catch { $fecha = $null }
        }
        $psPath = [string]$o.PSPath
        $size = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'EstimatedSize'
        [ordered]@{
            name = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'DisplayName'
            vendor = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'Publisher'
            version = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'DisplayVersion'
            description = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'Comments'
            install_date = $fecha
            install_location = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'InstallLocation'
            url_info = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'URLInfoAbout'
            url_update = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'URLUpdateAbout'
            architecture = $(if ($psPath -match 'WOW6432Node') { 'x86' } else { 'x64/nativo' })
            estimated_size_mb = $(if ($size) { [math]::Round($size / 1024, 1) } else { $null })
            language = Get-DiagUsbPropertyValue -InputObject $o -PropertyName 'Language'
        }
    })

    $optionalFeatures = @($features | ForEach-Object {
        $d = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DisplayName'
        [ordered]@{
            feature_name = $_.FeatureName
            display_name = $(if ($d) { $d } else { $_.FeatureName })
            description = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'Description'
            state = [string]$_.State
            restart_needed = [bool]$_.RestartNeeded
        }
    })

    $windowsFeatures = @($roles | ForEach-Object {
        [ordered]@{
            feature_name = $_.Name
            display_name = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'DisplayName'
            description = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'Description'
            installed = [bool]$_.Installed
            installed_by = Get-DiagUsbPropertyValue -InputObject $_ -PropertyName 'InstalledBy'
        }
    })

    return [ordered]@{
        installed_products = $softwareList
        optional_features = $optionalFeatures
        optional_features_available = $featuresAvailable
        windows_features = $windowsFeatures
    }
}

Write-DiagUsbJson -InputObject $result
