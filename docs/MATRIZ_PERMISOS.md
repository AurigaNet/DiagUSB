# MATRIZ_PERMISOS

Estado **medido** en un equipo real (ya no es plantilla). Datos crudos medidos sobre los 39 colectores; `physical_disks` re-medido tras acotar la consulta de fiabilidad.

## Entorno de medición

- Fecha: 2026-10-16
- Windows: Microsoft Windows 10 Pro 10.0.19045 (build 19045)
- PowerShell: 5.1.19041.6456
- Método: `run_diagnostic` (el mismo que ejecuta `GET /api/full-scan`) sobre los 39 colectores, una vez **sin** administrador (`is_elevated=false`) y dos veces **con** administrador (`is_elevated=true`).
- Los datos se compararon por estado (`query.status`) y por una huella estructural estable (tipos y longitudes, sin valores volátiles).

## Resultado

Total de colectores: **39**. Colectores que difieren entre modo estándar y administrador: **5**.

| Colector | Sin admin | Con admin | ¿Datos distintos? | Nota |
| --- | --- | --- | --- | --- |
| `security_events` | `denied` | `ok` | sí | 0 eventos vs 10 eventos; sin admin el acceso al registro de seguridad se deniega. |
| `installed_software` | `ok` | `ok` | sí | `optional_features`: 0 vs 24; sin admin no se listan las características opcionales de Windows. El colector lo declara con `optional_features_available: false` y el informe agrega "datos limitados: installed_software (requiere administrador)". |
| `physical_disks` | `ok` (~6,7 s) | `ok` (~6,7 s) | sí | Re-medido tras acotar la consulta de fiabilidad a 10 s por disco, que no se hace en unidades USB, así que ya no hay timeout (antes ~93 s elevado). Elevado aparecen `power_on_hours`/`temperature`; la unidad Kingston USB nunca aporta fiabilidad (`reliability_motivo: "no aplica a unidades USB"`). |
| `running_services` | `ok` (107) | `ok` (108) | sí (volátil) | El conteo de servicios en ejecución cambia entre corridas; no es efecto de permisos. |
| `connectivity` | `ok` | `ok` | sí (formato) | `latency_ms` entero vs flotante; no es efecto de permisos. |

Los **34** colectores restantes dan el mismo estado y la misma estructura de datos en ambos modos.

## Colectores que requieren administrador (para el banner)

- `security_events` (eventos de seguridad): `denied` sin admin.
- `installed_software` (inventario de software): sin admin faltan las características opcionales; el colector declara `optional_features_available: false` y el informe lo reporta como "datos limitados: installed_software (requiere administrador)".

## Caso especial: colector `cpu_temperature` (agregado posterior a 0.1.0)

El colector de temperatura del CPU usa `LibreHardwareMonitorLib.dll`, incluida en el instalador:

- La lectura principal es directa por la DLL, dentro del mismo proceso de DiagUSB.
- Algunos sensores solo se exponen cuando DiagUSB se ejecuta como Administrador; sin esos permisos el paquete informa los datos disponibles o queda como no disponible, con el motivo visible.
- Queda un respaldo opcional por el servidor web local de LibreHardwareMonitor en `http://127.0.0.1:8085` (solo loopback; configurable con `DIAGUSB_LHM_URL`).
- Medir el cambio de lecturas con/sin admin es una prueba pendiente en hardware distinto al equipo de desarrollo.

## Contextos pendientes

Falta medir el contexto "otro administrador" (queda pendiente de medición).
