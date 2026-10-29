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

function Get-DiagUsbConnectionKind {
    param($Adapter)

    $texto = ("$($Adapter.InterfaceDescription) $($Adapter.Name)").ToLowerInvariant()
    $media = ([string]$Adapter.PhysicalMediaType).ToLowerInvariant()

    if ($texto -match 'bluetooth|personal area network|\bpan\b') { return 'bluetooth' }
    if ($texto -match 'remote ndis|rndis|usb.*(tether|network)|tether|apple.*(mobile|iphone)|android.*(usb|tether)') { return 'usb_tethering' }
    if ($texto -match 'wi-?fi|wireless|802\.11' -or $media -match '802\.11|wireless') { return 'wifi' }
    if ($texto -match 'wwan|mobile broadband|cellular|\blte\b' -or $media -match 'wwan') { return 'wwan' }
    if ($texto -match 'ethernet|802\.3' -or $media -match '802\.3') { return 'ethernet' }
    return 'other'
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

function Convert-DiagUsbUint16Text {
    param($Value)

    if ($null -eq $Value) { return '' }
    try {
        $texto = -join (@($Value) | Where-Object { $_ -ne 0 } |
            ForEach-Object { [char][int]$_ })
        return $texto.Trim()
    }
    catch {
        return ''
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

function Get-DiagUsbLhmUrl {
    $default = 'http://127.0.0.1:8085'
    $envUrl = [string]$env:DIAGUSB_LHM_URL
    if (-not $envUrl) { return $default }
    try {
        $uri = [Uri]$envUrl
        if ($uri.Scheme -notin @('http', 'https')) { return $default }
        if (-not $uri.IsLoopback) { return $default }
        return $uri.GetLeftPart([UriPartial]::Authority)
    }
    catch {
        return $default
    }
}

function Test-DiagUsbLhmCpuNode {
    param($Node)

    if ($null -eq $Node) { return $false }
    $text = [string](Get-DiagUsbPropertyValue -InputObject $Node -PropertyName 'Text')
    $image = [string](Get-DiagUsbPropertyValue -InputObject $Node -PropertyName 'ImageURL')

    if ($image -match '(?i)(^|[/\\])cpu[^/\\]*\.(png|gif|jpe?g|svg)$') {
        return $true
    }
    if ($text -match '(?i)\b(gpu|graphics|radeon|geforce|nvidia|arc|iris|uhd)\b') {
        return $false
    }
    return [bool]($text -match '(?i)\b(ryzen|threadripper|epyc|athlon|sempron|xeon|pentium|celeron|core\s*(i[3579]|ultra)|cpu|processor)\b')
}

function Get-DiagUsbLhmCpuTemperature {
    param([int]$TimeoutSec = 3)

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
    $cpuNodes = @()
    foreach ($root in @($document)) {
        if ($null -eq $root) { continue }
        foreach ($child in @(Get-DiagUsbPropertyValue -InputObject $root -PropertyName 'Children')) {
            if ($null -ne $child -and (Test-DiagUsbLhmCpuNode -Node $child)) {
                $cpuNodes += $child
            }
        }
    }
    if ($cpuNodes.Count -eq 0) { return $null }

    $names = @()
    $sensors = @()
    foreach ($cpu in $cpuNodes) {
        $name = [string](Get-DiagUsbPropertyValue -InputObject $cpu -PropertyName 'Text')
        if ($name) { $names += $name }

        $pending = [System.Collections.Generic.Stack[object]]::new()
        foreach ($child in @(Get-DiagUsbPropertyValue -InputObject $cpu -PropertyName 'Children')) {
            if ($null -ne $child) { $pending.Push($child) }
        }

        while ($pending.Count -gt 0) {
            $node = $pending.Pop()
            $text = [string](Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Text')
            $value = [string](Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Value')
            foreach ($child in @(Get-DiagUsbPropertyValue -InputObject $node -PropertyName 'Children')) {
                if ($null -ne $child) { $pending.Push($child) }
            }

            if (-not $text -or $text -match '(?i)distance|tjmax|throttl|limit') { continue }
            $match = [regex]::Match($value, '(?i)(-?\d+(?:[.,]\d+)?)\s*(?:\u00B0\s*)?C\b')
            if (-not $match.Success) { continue }
            try {
                $temperature = [double]::Parse(
                    $match.Groups[1].Value.Replace(',', '.'),
                    [System.Globalization.CultureInfo]::InvariantCulture)
            }
            catch {
                continue
            }
            if ($temperature -le 0 -or $temperature -ge 130) { continue }

            $kind = 'other'
            if ($text -match '(?i)package|tctl|tdie') { $kind = 'package' }
            elseif ($text -match '(?i)\bcore\b') { $kind = 'core' }

            $sensors += [ordered]@{
                name = $text
                temperature_c = [math]::Round($temperature, 1)
                kind = $kind
            }
        }
    }

    if ($sensors.Count -eq 0) { return $null }

    $packageTemps = @($sensors | Where-Object { $_.kind -eq 'package' } |
        ForEach-Object { [double]$_.temperature_c })
    $coreTemps = @($sensors | Where-Object { $_.kind -eq 'core' } |
        ForEach-Object { [double]$_.temperature_c })
    $allTemps = @($sensors | ForEach-Object { [double]$_.temperature_c })

    $packageTemp = $null
    if ($packageTemps.Count -gt 0) {
        $packageTemp = ($packageTemps | Measure-Object -Maximum).Maximum
    }
    $maxCoreTemp = $null
    $averageCoreTemp = $null
    if ($coreTemps.Count -gt 0) {
        $maxCoreTemp = ($coreTemps | Measure-Object -Maximum).Maximum
        $averageCoreTemp = [math]::Round(
            ($coreTemps | Measure-Object -Average).Average, 1)
    }
    $maxTemp = ($allTemps | Measure-Object -Maximum).Maximum

    return [pscustomobject][ordered]@{
        source = 'librehardwaremonitor'
        url = $base
        cpu_name = ($names -join ' + ')
        package_temp_c = $packageTemp
        max_core_temp_c = $maxCoreTemp
        average_core_temp_c = $averageCoreTemp
        max_temp_c = $maxTemp
        sensor_count = $sensors.Count
        sensors = $sensors
    }
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

function Get-DiagUsbBatteryReportInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$XmlPath
    )

    $xml = [xml](Get-Content -LiteralPath $XmlPath -Raw -Encoding UTF8)
    $info = Get-DiagUsbPropertyValue -InputObject $xml -PropertyName 'BatteryInformation'
    if ($null -eq $info) {
        throw 'El reporte de bateria no tiene el formato esperado (falta BatteryInformation).'
    }

    $baterias = @(Get-DiagUsbPropertyValue -InputObject $info -PropertyName 'Battery')
    if ($baterias.Count -eq 0 -and $null -eq (Get-DiagUsbPropertyValue -InputObject $info -PropertyName 'Battery')) {
        throw 'El reporte de bateria no tiene el formato esperado (falta Battery).'
    }

    function Convert-DiagUsbBatteryNumber {
        param([string]$Texto)
        if ([string]::IsNullOrWhiteSpace($Texto)) { return $null }
        try {
            $valor = [double]::Parse($Texto.Trim(), [System.Globalization.CultureInfo]::InvariantCulture)
            if ($valor -le 0) { return $null }
            return [math]::Round($valor, 1)
        }
        catch {
            return $null
        }
    }

    $resultados = @()
    foreach ($bat in $baterias) {
        if ($null -eq $bat) { continue }
        $resultados += [ordered]@{
            id = [string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'Id')
            fabricante = [string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'Manufacturer')
            chemistry = [string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'Chemistry')
            design_capacity_mwh = Convert-DiagUsbBatteryNumber ([string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'DesignCapacity'))
            full_charge_capacity_mwh = Convert-DiagUsbBatteryNumber ([string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'FullChargeCapacity'))
            ciclos = Convert-DiagUsbBatteryNumber ([string](Get-DiagUsbPropertyValue -InputObject $bat -PropertyName 'CycleCount'))
        }
    }
    return $resultados
}

function Get-DiagUsbGatewayMac {
    param(
        [string]$GatewayIp = '',
        [string]$InterfaceIndex = '',
        $Vecinos = $null
    )

    if (-not $GatewayIp) { return $null }
    $tabla = $Vecinos
    if ($null -eq $tabla) {
        $parametros = @{ IPAddress = $GatewayIp; ErrorAction = 'SilentlyContinue' }
        if ($InterfaceIndex) { $parametros['InterfaceIndex'] = $InterfaceIndex }
        $tabla = @(Get-NetNeighbor @parametros)
    }
    $vecino = @($tabla | Where-Object {
        $_.State -in @('Reachable', 'Stale', 'Probe', 'Delay', 'Permanent')
    } | Select-Object -First 1)
    if ($vecino.Count -gt 0) {
        $mac = [string]$vecino[0].LinkLayerAddress
        if ($mac) { return $mac }
    }
    return 'no_disponible'
}

function Write-DiagUsbJson {
    param(
        [Parameter(Mandatory = $true)]
        $InputObject,
        [int]$Depth = 8
    )

    $InputObject | ConvertTo-Json -Depth $Depth
}
