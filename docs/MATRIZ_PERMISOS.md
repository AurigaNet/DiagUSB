# MATRIZ_PERMISOS

Estado **medido** en un equipo real (ya no es plantilla). Datos crudos de la Ronda 11.

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
| `physical_disks` | `ok` (2,4 s) | `timeout` (93 s) | n/a | Elevado, `Get-PhysicalDisk`/`Get-StorageReliabilityCounter` tarda ~93 s y supera el timeout de 30 s. Reproducible. |
| `running_services` | `ok` (107) | `ok` (108) | sí (volátil) | El conteo de servicios en ejecución cambia entre corridas; no es efecto de permisos. |
| `connectivity` | `ok` | `ok` | sí (formato) | `latency_ms` entero vs flotante; no es efecto de permisos. |

Los **34** colectores restantes dan el mismo estado y la misma estructura de datos en ambos modos.

## Colectores que requieren administrador (para el banner)

- `security_events` (eventos de seguridad): `denied` sin admin.
- `installed_software` (inventario de software): sin admin faltan las características opcionales; el colector declara `optional_features_available: false` y el informe lo reporta como "datos limitados: installed_software (requiere administrador)".

## Contextos pendientes

Falta medir el contexto "otro administrador" (no se hizo en esta ronda).
