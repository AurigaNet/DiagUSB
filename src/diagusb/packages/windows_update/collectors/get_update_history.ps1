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

$result = New-DiagUsbCollectorResult -CollectorId 'update_history' -ScriptBlock {
    try {
        $logName = 'Microsoft-Windows-WindowsUpdateClient/Operational'
        $events = Get-WinEvent -LogName $logName -MaxEvents 20 -ErrorAction SilentlyContinue |
            Select-Object @{N='Fecha'; E={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}},
                          @{N='EventId'; E={$_.Id}},
                          @{N='Mensaje'; E={$_.Message}}

        if ($events) {
            $eventList = @()
            foreach ($event in $events) {
                $eventList += @{
                    fecha = $event.Fecha
                    evento_id = $event.EventId
                    mensaje = $event.Mensaje
                }
            }

            return @{
                status = 'ok'
                total_eventos = $eventList.Count
                eventos = $eventList
            }
        } else {
            return @{
                status = 'no_events'
                message = 'No se encontraron eventos en el log de Windows Update'
            }
        }
    } catch {
        return @{
            status = 'error'
            message = $_.Exception.Message
        }
    }
}

Write-DiagUsbJson -InputObject $result
