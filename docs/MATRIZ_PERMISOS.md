# MATRIZ_PERMISOS

Plantilla para completar con pruebas reales en Windows. Esta matriz debe llenarse manualmente ejecutando los colectores en tres contextos distintos: usuario estándar, administrador y otro administrador.

## Instrucciones

- Registrar fecha, edición de Windows, build y PowerShell usados en cada prueba.
- No completar a partir de fixtures sintéticos.
- Para cada colector, anotar el estado observado (`ok`, `empty`, `denied`, `timeout`, `not_available`, `error`) y un resumen breve.
- Si cambia algo entre ejecuciones, conservar ambas observaciones.

## Entornos a probar

- usuario estándar
- administrador
- otro administrador

## Tabla sugerida

| Colector | Usuario estándar | Administrador | Otro administrador | Notas |
| --- | --- | --- | --- | --- |
| `get_printers.ps1` | pendiente | pendiente | pendiente | |
| `get_printer_ports.ps1` | pendiente | pendiente | pendiente | |
| `get_printer_drivers.ps1` | pendiente | pendiente | pendiente | |
| `get_spooler_service.ps1` | pendiente | pendiente | pendiente | |
| `get_print_jobs.ps1` | pendiente | pendiente | pendiente | |
| `get_print_events.ps1` | pendiente | pendiente | pendiente | |