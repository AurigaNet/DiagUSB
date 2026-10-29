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

El colector de temperatura del CPU **no depende del permiso de DiagUSB**, sino de LibreHardwareMonitor (LHM), herramienta externa que se ejecuta aparte:

- DiagUSB consulta `http://127.0.0.1:8085` (solo loopback; configurable con `DIAGUSB_LHM_URL`), sin permisos especiales.
- Si LHM no esta activo (o lo esta sin su servidor web), el paquete `temperatura` queda bloqueado por el preflight de capacidades con el motivo visible; DiagUSB mismo **no necesita** elevacion para este colector.
- Medir el cambio de lecturas con/sin admin de **DiagUSB** no aplica; el cambio relevante esta en ejecutar LHM con o sin Administrador (sin admin + sin PawnIO, LHM no expone sensores CPU).

## Contextos pendientes

Falta medir el contexto "otro administrador" (queda pendiente de medición).
