# Changelog

Todos los cambios relevantes de DiagUSB se registran en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado [SemVer](https://semver.org/lang/es/).

## [0.1.0] - 2026-10-20

Primera versión portable para Windows 10.

### Agregado

- 12 paquetes de diagnóstico de solo lectura: impresión, redes cableadas, Wi-Fi, disco, memoria, servicios, seguridad, Windows Update, drivers, eventos críticos, contexto del sistema e inventario.
- Interfaz web local con diagnóstico rápido, revisión total, puntaje orientativo, acciones del técnico y comparación de snapshots ANTES/DESPUÉS.
- Informes Word (`.doc`) y PDF en español, con métricas, hallazgos, soluciones de la base de conocimiento y diferencias entre snapshots.
- Base de conocimiento local editable y registro persistente de análisis con búsqueda, borrado individual y borrado total.
- CLI interactiva, comandos `diagnose`, `report`, `web`, `list-packages` y `--version`.
- Kit portable con Python embebido y verificación SHA-256, más ejecutable opcional con PyInstaller.
- Elevación a Administrador a pedido, sin UAC al arrancar.
- Borrado de datos locales desde la interfaz, con confirmación y conteos.

### Seguridad

- Servidor limitado a `127.0.0.1`, token de sesión, validación de `Host`/`Origin`, `Content-Type` y tamaño del cuerpo.
- Cabeceras CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Cache-Control` y `Referrer-Policy` en todas las respuestas.
- Redacción de contraseñas y claves sensibles en API, registro, snapshots, informes y salida CLI.
- El colector Wi-Fi ya no solicita ni conserva la clave en claro de los perfiles.
- Verificación de integridad SHA-256 de los colectores y del kit.

### Corregido

- Falso positivo de driver faltante cuando el nombre incluía un sufijo de versión.
- Falso positivo de equipo virtual por `HypervisorPresent`; la detección ahora usa fabricante y modelo.
- Perfiles Wi-Fi y datos sensibles expuestos en respuestas o informes.
- Borrado local sin confirmación ni conteos previos.

### Limitaciones conocidas

- Validado en Windows 10. Windows 11 todavía no está probado.
- El kit no tiene firma Authenticode; la integridad se verifica con SHA-256 y el intérprete `python.exe` está firmado por Python Software Foundation.
- El comportamiento bajo antivirus/EDR no está validado. No se deben agregar exclusiones permanentes.
- El informe `.doc` usa MHTML; para máxima portabilidad se recomienda el PDF.
