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

$result = New-DiagUsbCollectorResult -CollectorId 'connectivity' -ScriptBlock {
    $tests = @()

    # Ping a 8.8.8.8
    $ping8 = Test-Connection -ComputerName 8.8.8.8 -Count 2 -ErrorAction SilentlyContinue
    $tests += [ordered]@{
        target = '8.8.8.8'
        type = 'icmp'
        success = if ($ping8) { $true } else { $false }
        latency_ms = if ($ping8) { [math]::Round(($ping8 | Measure-Object -Property ResponseTime -Average).Average, 2) } else { $null }
    }

    # Ping a 1.1.1.1
    $ping1 = Test-Connection -ComputerName 1.1.1.1 -Count 2 -ErrorAction SilentlyContinue
    $tests += [ordered]@{
        target = '1.1.1.1'
        type = 'icmp'
        success = if ($ping1) { $true } else { $false }
        latency_ms = if ($ping1) { [math]::Round(($ping1 | Measure-Object -Property ResponseTime -Average).Average, 2) } else { $null }
    }

    # Ping al gateway
    $gateway = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop
    if ($gateway) {
        $pingGw = Test-Connection -ComputerName $gateway -Count 2 -ErrorAction SilentlyContinue
        $tests += [ordered]@{
            target = $gateway
            type = 'gateway'
            success = if ($pingGw) { $true } else { $false }
            latency_ms = if ($pingGw) { [math]::Round(($pingGw | Measure-Object -Property ResponseTime -Average).Average, 2) } else { $null }
        }
    }

    # nslookup a google.com
    try {
        $nslookup = Resolve-DnsName -Name 'google.com' -Type A -ErrorAction Stop | Select-Object -First 1
        $tests += [ordered]@{
            target = 'google.com'
            type = 'dns'
            success = if ($nslookup) { $true } else { $false }
            resolved_ip = if ($nslookup) { $nslookup.IPAddress } else { $null }
            latency_ms = $null
        }
    } catch {
        $tests += [ordered]@{
            target = 'google.com'
            type = 'dns'
            success = $false
            resolved_ip = $null
            latency_ms = $null
        }
    }

    $tests
}

Write-DiagUsbJson -InputObject $result
