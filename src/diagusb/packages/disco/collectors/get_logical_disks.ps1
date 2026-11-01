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

$result = New-DiagUsbCollectorResult -CollectorId 'logical_disks' -ScriptBlock {
    $items = @()

    # Fuente principal: la API de volumenes de .NET. No depende del proveedor
    # WMI de almacenamiento, que puede estar deshabilitado (servicio smphost
    # detenido) y devolver Size/FreeSpace vacios sin informar error.
    try {
        foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
            if ($null -eq $drive) { continue }
            if (-not $drive.IsReady) { continue }
            $tipo = $drive.DriveType
            if ($tipo -ne [System.IO.DriveType]::Fixed -and
                $tipo -ne [System.IO.DriveType]::Removable) { continue }

            try {
                $totalBytes = [double]$drive.TotalSize
                $freeBytes = [double]$drive.AvailableFreeSpace
            }
            catch { continue }
            if ($totalBytes -le 0) { continue }

            $freePercent = [math]::Round(($freeBytes / $totalBytes) * 100, 1)
            $items += [ordered]@{
                device_id = $drive.Name.TrimEnd([char]'\')
                drive_type = $(if ($tipo -eq [System.IO.DriveType]::Fixed) { 'Fixed' } else { 'Removable' })
                total_gb = [math]::Round($totalBytes / 1GB, 2)
                free_gb = [math]::Round($freeBytes / 1GB, 2)
                used_percent = [math]::Round(100 - $freePercent, 1)
                free_percent = $freePercent
                volume_name = [string]$drive.VolumeLabel
                file_system = [string]$drive.DriveFormat
            }
        }
    }
    catch {
        # Si .NET falla se intenta el respaldo WMI.
    }

    # Respaldo: WMI, solo si .NET no devolvio unidades. Se descartan las
    # unidades sin tamano real para no informar 0 GB ni 100% usado.
    if ($items.Count -eq 0) {
        $disks = @(Get-CimInstance -ClassName Win32_LogicalDisk -ErrorAction SilentlyContinue |
            Where-Object {
                $_.DriveType -in @(2, 3) -and
                $null -ne $_.Size -and [double]$_.Size -gt 0
            })
        foreach ($disk in $disks) {
            $totalBytes = [double]$disk.Size
            $freeBytes = [double]$disk.FreeSpace
            $freePercent = [math]::Round(($freeBytes / $totalBytes) * 100, 1)

            $items += [ordered]@{
                device_id = [string]$disk.DeviceID
                drive_type = switch ($disk.DriveType) { 2 { 'Removable' } 3 { 'Fixed' } default { 'Unknown' } }
                total_gb = [math]::Round($totalBytes / 1GB, 2)
                free_gb = [math]::Round($freeBytes / 1GB, 2)
                used_percent = [math]::Round(100 - $freePercent, 1)
                free_percent = $freePercent
                volume_name = [string]$disk.VolumeName
                file_system = [string]$disk.FileSystem
            }
        }
    }

    return $items
}

Write-DiagUsbJson -InputObject $result
