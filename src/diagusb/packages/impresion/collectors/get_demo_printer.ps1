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

$result = New-DiagUsbCollectorResult -CollectorId 'demo_printer' -ScriptBlock {
    [ordered]@{
        printers = @(
            [ordered]@{
                device_id = 'DemoPrinter_OK'
                name = 'HP LaserJet Pro M404n (Simulado)'
                system_name = $env:COMPUTERNAME
                driver_name = 'HP LaserJet Pro M404n'
                port_name = '192.168.1.100'
                default = $true
                network = $true
                local = $false
                shared = $false
                share_name = $null
                hidden = $false
                direct = $false
                do_complete_first = $true
                enable_bidi = $true
                keep_printed_jobs = $false
                published = $false
                queued = $true
                work_offline = $false
                printer_status = 'OK'
                detected_error_state = 0
                extended_printer_status = 1
                extended_detected_error_state = 0
                horizontal_resolution = 1200
                vertical_resolution = 1200
                average_pages_per_minute = 40
                jobs = 0
                location = 'Oficina Principal'
                comment = 'Impresora de red simulada - Funcionando correctamente'
                server_name = "\\$env:COMPUTERNAME"
            },
            [ordered]@{
                device_id = 'DemoPrinter_Error'
                name = 'Canon G3010 (Simulado)'
                system_name = $env:COMPUTERNAME
                driver_name = 'Canon G3010 series'
                port_name = 'USB001'
                default = $false
                network = $false
                local = $true
                shared = $true
                share_name = 'Canon_G3010'
                hidden = $false
                direct = $false
                do_complete_first = $false
                enable_bidi = $true
                keep_printed_jobs = $false
                published = $true
                queued = $true
                work_offline = $false
                printer_status = 'Error'
                detected_error_state = 8
                extended_printer_status = 2
                extended_detected_error_state = 8
                horizontal_resolution = 600
                vertical_resolution = 600
                average_pages_per_minute = 10
                jobs = 1
                location = 'Oficina Secundario'
                comment = 'Impresora local simulada - Estado de error'
                server_name = "\\$env:COMPUTERNAME"
            }
        )
        ports = @(
            [ordered]@{
                name = '192.168.1.100'
                host_address = '192.168.1.100'
                port_number = 9100
                protocol = 1
                queue = $null
                snmp_enabled = $false
                snmp_community = 'public'
                snmp_dev_index = 1
                byte_count = $true
                double_spool = $false
            },
            [ordered]@{
                name = 'USB001'
                host_address = '192.168.1.101'
                port_number = 9100
                protocol = 1
                queue = 'Canon_Queue'
                snmp_enabled = $true
                snmp_community = 'public'
                snmp_dev_index = 2
                byte_count = $true
                double_spool = $false
            }
        )
        drivers = @(
            [ordered]@{
                name = 'HP LaserJet Pro M404n'
                driver_path = 'C:\Windows\System32\DriverStore\FileRepository\hpbu153.inf_arm64_a52a\hpbu153.dll'
                config_file = 'C:\Windows\System32\DriverStore\FileRepository\hpbu153.inf_arm64_a52a\hpbu153.ini'
                data_file = 'C:\Windows\System32\DriverStore\FileRepository\hpbu153.inf_arm64_a52a\hpbu153.dat'
                help_file = 'C:\Windows\System32\DriverStore\FileRepository\hpbu153.inf_arm64_a52a\hpbu153.chm'
                inf_name = 'hpbu153.inf'
                monitor_name = 'HP Standard TCP/IP Port Monitor'
                supported_platform = 'Windows NT x86'
                version = '1.0.2.0'
                major_version = 1
                driver_date_utc = '2024-03-15T00:00:00.0000000'
            },
            [ordered]@{
                name = 'Canon G3010 series'
                driver_path = 'C:\Windows\System32\DriverStore\FileRepository\cnr1849.inf_arm64_8d99\cnr1849.dll'
                config_file = 'C:\Windows\System32\DriverStore\FileRepository\cnr1849.inf_arm64_8d99\cnr1849.ini'
                data_file = 'C:\Windows\System32\DriverStore\FileRepository\cnr1849.inf_arm64_8d99\cnr1849.dat'
                help_file = $null
                inf_name = 'cnr1849.inf'
                monitor_name = 'Canon Standard Port Monitor'
                supported_platform = 'Windows NT x86'
                version = '6.5.1.0'
                major_version = 6
                driver_date_utc = '2023-11-20T00:00:00.0000000'
            }
        )
        spooler = [ordered]@{
            name = 'Spooler'
            display_name = 'Print Spooler'
            state = 'Running'
            start_mode = 'Auto'
            started = $true
            start_name = 'LocalSystem'
            process_id = 1234
            exit_code = 0
            service_type = 'Share Process'
        }
        print_jobs = @(
            [ordered]@{
                name = 'DemoPrinter_Error - 45'
                document = 'documento_bloqueado.pdf'
                driver_name = 'Canon G3010 series'
                host_print_queue = 'Canon_Queue'
                job_id = 45
                owner = 'usuario_demo'
                priority = 1
                size_bytes = 2048576
                total_pages = 10
                pages_printed = 0
                elapsed_time_seconds = 3600
                status_mask = 12
                time_submitted_utc = '2026-10-14T08:30:00.0000000'
            }
        )
    }
}

Write-DiagUsbJson -InputObject $result
