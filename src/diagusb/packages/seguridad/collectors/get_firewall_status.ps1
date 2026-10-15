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

$result = New-DiagUsbCollectorResult -CollectorId 'firewall_status' -ScriptBlock {
    $profiles = @()

    try {
        $firewallProfiles = Get-NetFirewallProfile -ErrorAction Stop

        foreach ($profile in $firewallProfiles) {
            $inbound = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'DefaultInboundAction'
            $outbound = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'DefaultOutboundAction'
            $logPath = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'LogFileName'
            $logMaxKb = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'LogMaxSizeKilobytes'
            $logDropped = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'LogDroppedPackets'
            $logSuccess = Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'LogSuccessfulConnections'

            $profiles += [ordered]@{
                name = $profile.Name
                enabled = [bool]$profile.Enabled
                default_inbound_action = $(if ($null -ne $inbound) { $inbound.ToString() } else { $null })
                default_outbound_action = $(if ($null -ne $outbound) { $outbound.ToString() } else { $null })
                allow_inbound_rules = [bool](Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'AllowInboundRules')
                allow_local_firewall_rules = [bool](Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'AllowLocalFirewallRules')
                notify_on_listen = [bool](Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'NotifyOnListen')
                allow_unicast_response_to_multicast = [bool](Get-DiagUsbPropertyValue -InputObject $profile -PropertyName 'AllowUnicastResponseToMulticast')
                log_dropped_packets = $logDropped
                log_successful_connections = $logSuccess
                log_file_path = $logPath
                log_max_size_kb = $logMaxKb
            }
        }
    }
    catch {
        if ($_.Exception.Message -like '* acceso*' -or $_.Exception.Message -like '* denied*' -or $_.Exception.Message -like '* permiso*') {
            throw 'DIAGUSB_DENIED: No se tienen permisos para consultar el firewall. Ejecute como Administrador.'
        }
        throw "DIAGUSB_NOT_AVAILABLE: No se pudo obtener el estado del firewall: $($_.Exception.Message)"
    }

    return $profiles
}

Write-DiagUsbJson -InputObject $result
