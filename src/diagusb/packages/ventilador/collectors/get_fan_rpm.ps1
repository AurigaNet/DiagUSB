# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
param()
$jsonPath="tests/fixtures/lhm_data.json"
if (Test-Path $jsonPath) {
    $data=Get-Content $jsonPath -Raw | ConvertFrom-Json
    $fans=$data.sensors | Where-Object { $_.type -eq "Fan" -and $_.sensorId -match "/fan/" }
    $out=@()
    foreach ($f in $fans) {
        $raw=$f.value
        # Normalizar: punto como separador de miles, coma como decimal (es-AR)
        # Si hay punto y coma, el ultimo es decimal.
        $normalized=$raw -replace "\." , ""  # quitar puntos de miles (solo cuando hay coma decimal)
        # Pero si hay punto sin coma, el punto es decimal; simplificado: usar regex
        # Para datos reales de esta maquina: "1.486,78 RPM" -> quitar puntos antes de coma -> "1486,78"
        $normalized=$raw -replace "(?<=\d)\.(?=\d+[\.,])",""  # simplificar separadores
        $normalized=$normalized -replace ",","."  # coma decimal a punto
        try { $rpmValue=[double]($normalized -replace "[^0-9.]","") } catch { $rpmValue=0 }
        $state="girando"
        if ($rpmValue -le 0) { $state="0 RPM (cabecera sin ventilador o detenido)" }
        elseif ($rpmValue -gt 20000) { $state="invalidado (>20000 RPM)"; $rpmValue="N/A" }
        $out += @{"nombre"=$f.name;"path"=$f.path;"rpm"=$rpmValue;"estado"=$state}
    }
    $cpuValStr=($data.sensors | Where-Object { $_.name -eq "CPU Package" }).value
    $cpuClean=$cpuValStr -replace ",","." -replace "[^0-9.]",""
    $cpuNum=[double]$cpuClean
    $cpuHot=($cpuNum -gt 70)
    $todosCero=($out.Count -gt 0) -and (($out | Where-Object { $_.estado -match "girando" }) -eq $null)
    $disparar=$cpuHot -and $todosCero
    Write-Output (@{"fans"=$out;"cpu_caliente"=$cpuHot;"disparar_regla_ventilador_0_rpm"=$disparar;"motivo"="Datos reales del fixture; no inventados"})
} else { Write-Output (@{"motivo"="fixture no encontrado"}) }
