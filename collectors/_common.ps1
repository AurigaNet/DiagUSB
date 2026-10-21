# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Emitir UTF-8 en stdout para que Python/navegador reciban acentos correctos
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
} catch { }
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

function Get-DiagUsbTimestampUtc {
    return [DateTime]::UtcNow.ToString('o')
}

function Test-DiagUsbVirtual {
    param(
        [AllowEmptyString()][string]$Manufacturer = '',
        [AllowEmptyString()][string]$Model = ''
    )
    $texto = ("$Manufacturer $Model").ToLowerInvariant()
    return [bool]($texto -match 'vmware|virtualbox|innotek|qemu|kvm|xen|parallels|hyper-v|virtual machine|virtual platform|bhyve')
}

function Get-DiagUsbCaptureContext {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $culture = Get-Culture
    $uiCulture = Get-UICulture
    $os = Get-CimInstance -ClassName Win32_OperatingSystem

    return [ordered]@{
        computer_name = $env:COMPUTERNAME
        user = $identity.Name
        is_elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        windows = [ordered]@{
            caption = $os.Caption
            version = $os.Version
            build_number = $os.BuildNumber
            locale = $os.Locale
            os_architecture = $os.OSArchitecture
        }
        regional_settings = [ordered]@{
            culture_name = $culture.Name
            culture_lcid = $culture.LCID
            ui_culture_name = $uiCulture.Name
            ui_culture_lcid = $uiCulture.LCID
            decimal_separator = $culture.NumberFormat.NumberDecimalSeparator
            list_separator = $culture.TextInfo.ListSeparator
        }
        powershell = [ordered]@{
            version = $PSVersionTable.PSVersion.ToString()
            edition = $PSVersionTable.PSEdition
            compatible_versions = @($PSVersionTable.PSCompatibleVersions | ForEach-Object { $_.ToString() })
        }
    }
}

function Get-DiagUsbErrorDetails {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.ErrorRecord]$ErrorRecord
    )

    return [ordered]@{
        type = $ErrorRecord.Exception.GetType().FullName
        message = $ErrorRecord.Exception.Message
        fully_qualified_error_id = $ErrorRecord.FullyQualifiedErrorId
        category = $ErrorRecord.CategoryInfo.Category.ToString()
        target_name = $ErrorRecord.CategoryInfo.TargetName
        target_type = $ErrorRecord.CategoryInfo.TargetType
        script_stack_trace = $ErrorRecord.ScriptStackTrace
    }
}

function New-DiagUsbCollectorResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CollectorId,
        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock,
        [int]$TimeoutSeconds = 15,
        [hashtable]$Metadata = @{}
    )

    $startedAtUtc = Get-DiagUsbTimestampUtc
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $context = Get-DiagUsbCaptureContext
    $errors = @()
    $notes = @()
    $status = 'error'
    $data = $null

    try {
        $data = & $ScriptBlock
        $items = @($data)
        if ($items.Count -eq 0) {
            $status = 'empty'
            $data = @()
        }
        else {
            $status = 'ok'
            $data = $items
        }
    }
    catch {
        $errors = @((Get-DiagUsbErrorDetails -ErrorRecord $_))
        $message = $_.Exception.Message

        if ($message -like 'DIAGUSB_NOT_AVAILABLE:*') {
            $status = 'not_available'
        }
        elseif ($message -like 'DIAGUSB_DENIED:*') {
            $status = 'denied'
        }
        elseif ($message -like 'DIAGUSB_TIMEOUT:*') {
            $status = 'timeout'
        }
        else {
            $status = 'error'
        }

        $data = @()
    }
    finally {
        $stopwatch.Stop()
    }

    return [ordered]@{
        schema_version = 1
        collector_id = $CollectorId
        captured_at_utc = $startedAtUtc
        query = [ordered]@{
            status = $status
            duration_ms = $stopwatch.ElapsedMilliseconds
            timeout_seconds = $TimeoutSeconds
        }
        context = $context
        metadata = $Metadata
        data = $data
        errors = $errors
        notes = $notes
    }
}

function Convert-DiagUsbDateTime {
    param(
        $Value
    )

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [DateTime]) {
        return $Value.ToUniversalTime().ToString('o')
    }

    try {
        return ([Management.ManagementDateTimeConverter]::ToDateTime([string]$Value)).ToUniversalTime().ToString('o')
    }
    catch {
        return [string]$Value
    }
}

function Get-DiagUsbPropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        $InputObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    $property = $InputObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Get-DiagUsbServiceRecord {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $service = Get-CimInstance -ClassName Win32_Service -Filter ("Name='{0}'" -f $Name)
    if (-not $service) {
        throw 'DIAGUSB_NOT_AVAILABLE: el servicio solicitado no existe.'
    }

    return [ordered]@{
        name = $service.Name
        display_name = $service.DisplayName
        state = $service.State
        start_mode = $service.StartMode
        started = [bool]$service.Started
        start_name = $service.StartName
        process_id = $service.ProcessId
        exit_code = $service.ExitCode
        service_type = $service.ServiceType
    }
}

function Get-DiagUsbEventRecord {
    param(
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Eventing.Reader.EventRecord]$Event
    )

    $xml = [xml]$Event.ToXml()
    $eventData = @()
    foreach ($dataNode in $xml.Event.EventData.Data) {
        $eventData += [ordered]@{
            name = $dataNode.Name
            value = [string]$dataNode.'#text'
        }
    }

    return [ordered]@{
        id = $Event.Id
        record_id = $Event.RecordId
        level = $Event.Level
        level_display_name = $Event.LevelDisplayName
        task = $Event.Task
        opcode = $Event.Opcode
        keywords = $Event.Keywords
        provider_name = $Event.ProviderName
        log_name = $Event.LogName
        machine_name = $Event.MachineName
        time_created_utc = $(if ($Event.TimeCreated) { $Event.TimeCreated.ToUniversalTime().ToString('o') } else { $null })
        activity_id = $(if ($Event.ActivityId) { $Event.ActivityId.Guid } else { $null })
        user_id = $(if ($Event.UserId) { $Event.UserId.Value } else { $null })
        event_data = $eventData
    }
}

function Write-DiagUsbJson {
    param(
        [Parameter(Mandatory = $true)]
        $InputObject,
        [int]$Depth = 8
    )

    $InputObject | ConvertTo-Json -Depth $Depth
}
