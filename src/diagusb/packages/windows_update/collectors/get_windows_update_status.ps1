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

$result = New-DiagUsbCollectorResult -CollectorId 'update_status' -ScriptBlock {
    try {
        $service = Get-Service -Name wuauserv -ErrorAction SilentlyContinue
        $autoUpdateService = Get-Service -Name TrustedInstaller -ErrorAction SilentlyContinue

        $lastUpdateTime = $null
        $scheduledScanTime = $null

        try {
            $lastUpdateRun = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install' -ErrorAction SilentlyContinue
            if ($lastUpdateRun) {
                $lastUpdateTime = $lastUpdateRun.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
            }
        } catch {}

        try {
            $scheduledTask = Get-ScheduledTask -TaskName 'Scheduled Scan' -TaskPath '\Microsoft\Windows\WindowsUpdate\' -ErrorAction SilentlyContinue
            if ($scheduledTask) {
                $trigger = $scheduledTask.Triggers | Select-Object -First 1
                if ($trigger) {
                    $scheduledScanTime = $trigger.StartBoundary
                }
            }
        } catch {}

        return @{
            status = 'ok'
            servicio_wuauserv = @{
                nombre = $service.Name
                estado = $service.Status
                tipo_inicio = $service.StartType
            }
            ultimo_update_install = $lastUpdateTime
            proximo_escanneo_programado = $scheduledScanTime
        }
    } catch {
        return @{
            status = 'error'
            message = $_.Exception.Message
        }
    }
}

Write-DiagUsbJson -InputObject $result
