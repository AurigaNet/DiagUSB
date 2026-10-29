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

function Get-DiagUsbFanSpeedsFromLhm {
    param([int]$TimeoutSec = 8)

    $base = Get-DiagUsbLhmUrl
    $uri = "$base/data.json"
    $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec $TimeoutSec -MaximumRedirection 0 -ErrorAction Stop
    if ([int]$response.StatusCode -ne 200) {
        throw "LibreHardwareMonitor respondio HTTP $($response.StatusCode)."
    }

    $stream = Get-DiagUsbPropertyValue -InputObject $response -PropertyName 'RawContentStream'
    $raw = [string](Get-DiagUsbPropertyValue -InputObject $response -PropertyName 'Content')
    if ($stream) {
        $bytes = [byte[]]$stream.ToArray()
    }
    else {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($raw)
    }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $bytes = $bytes[3..($bytes.Length - 1)]
    }
    $texto = [System.Text.Encoding]::UTF8.GetString($bytes)
    $document = $texto | ConvertFrom-Json

    $sensors = @()
    $pending = [System.Collections.Generic.Stack[object]]::new()
    foreach ($root in @($document)) {
        if ($null -ne $root) { $pending.Push($root) }
    }
    while ($pending.Count -gt 0) {
        $node = $pending.Pop()
        $text = [string](Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Text')
        $value = [string](Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Value')
        foreach ($child in @(Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Children')) {
            if ($null -ne $child) { $pending.Push($child) }
        }

        # Solo nodos hoja con valor en RPM. Un ventilador no tiene RPM fraccionarias:
        # '1.234' o '1,234' son miles (se quitan) y '1200,5' es decimal (se trunca).
        $match = [regex]::Match($value, '(?i)^\s*(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d+)?\s*RPM\s*$')
        if (-not $match.Success) { continue }
        try {
            $rpm = [int]($match.Groups[1].Value -replace '[.,]', '')
        }
        catch {
            continue
        }
        $sensors += [ordered]@{
            name = $text
            rpm = $rpm
        }
    }

    $rpms = @($sensors | ForEach-Object { [int]$_.rpm })
    $maxRpm = 0
    if ($rpms.Count -gt 0) {
        $maxRpm = [int](($rpms | Measure-Object -Maximum).Maximum)
    }

    return [ordered]@{
        source = 'librehardwaremonitor'
        url = $base
        available = $true
        sampled_at_utc = Get-DiagUsbTimestampUtc
        fan_rpms = @($rpms)
        max_fan_rpm = $maxRpm
        sensor_count = $sensors.Count
        sensors = @($sensors)
    }
}

$result = New-DiagUsbCollectorResult -CollectorId 'fan_speeds' -TimeoutSeconds 15 -ScriptBlock {
    try {
        $data = Get-DiagUsbFanSpeedsFromLhm -TimeoutSec 8
    }
    catch {
        throw "DIAGUSB_NOT_AVAILABLE: $($_.Exception.Message)"
    }
    return $data
}

Write-DiagUsbJson -InputObject $result
