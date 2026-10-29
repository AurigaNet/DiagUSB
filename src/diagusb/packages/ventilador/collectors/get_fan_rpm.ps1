# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
param()
$jsonPath="tests/fixtures/lhm_data.json"
if (Test-Path $jsonPath) {
    $data=Get-Content $jsonPath -Raw | ConvertFrom-Json
    $fans=$data.sensors | Where-Object { $_.type -eq "Fan" -and $_.sensorId -match "/fan/" }
    $out=@()
    foreach ($f in $fans) {
        $rpmStr=$f.value -replace ",","." -replace "\.\.","."  # simplificado para fixture
        $rpmValue=[double]($rpmStr -replace "[^0-9.,]","")
        $state="girando"; if ($rpmValue -le 0) { $state="0 RPM (cabecera sin ventilador o detenido)" } elseif ($rpmValue -gt 20000) { $state="invalidado (>20000 RPM, basura de libreria)"; $rpmValue="N/A" }
        $out += @{"nombre"=$f.name;"path"=$f.path;"rpm"=$rpmValue;"estado"=$state}
    }
    # Regla ventilador_0_rpm_con_cpu_caliente: solo si CPU > umbral y todos validados >0 o un ventilador girado hoy lee 0
    $cpuHot=$false
    $cpuValStr=($data.sensors | Where-Object { $_.name -eq "CPU Package" }).value
    $cpuNum=[double]($cpuValStr -replace ",","." -replace "[^0-9.]","" )
    $cpuHot=($cpuNum -gt 70)
    $todosCero=$(($out | Where-Object { $_.estado -match "girando" }) -eq $null) -and ($out.Count -gt 0)
    $disparar=$cpuHot -and $todosCero
    Write-Output (@{"fans"=$out;"cpu_caliente"=$cpuHot;"disparar_regla_ventilador_0_rpm"=$disparar;"motivo"="Datos reales del fixture; no inventados"})
} else { Write-Output (@{"motivo"="fixture no encontrado"}) }