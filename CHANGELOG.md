# Changelog

Todos los cambios relevantes de DiagUSB se registran en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Paquete de diagnóstico `temperatura` (paquete número 14): lee la temperatura del CPU desde LibreHardwareMonitor (LHM) mediante su servidor web local (`http://127.0.0.1:8085`, configurable con `DIAGUSB_LHM_URL`), sin empacar LHM ni PawnIO en el kit. EXPERIMENTAL: no validado todavía con una lectura real de sensores (ver `docs/LIMITACIONES.md`).
- Regla `cpu_caliente`: aviso a partir de 80 °C y hallazgo crítico a partir de 90 °C, sobre la máxima lectura válida del CPU (package/core), con detección previa de capacidades que bloquea el paquete (con motivo visible) si LHM no está activo, sin afectar al resto del diagnóstico.
- Entrada nueva de base de conocimiento `cpu_caliente` con soluciones (polvo, pasta térmica, ventilación, plan de energía); la base embebida pasa de 19 a 22 entradas.
- Paquete de diagnóstico `bateria` (EXPERIMENTAL, no verificado en hardware real): aparece solo en equipos con batería. Lee carga, estado y ciclos, y calcula el desgaste comparando la carga plena con la capacidad de diseño del reporte de batería (`powercfg /batteryreport`; el XML temporal se borra siempre). Regla `bateria_agotada`: aviso bajo el 60 % de la capacidad de diseño y crítico bajo el 40 %. En equipos sin batería el paquete queda oculto.
- Detección previa de capacidades extendida: además de impresoras, red y CPU, consulta si el equipo tiene batería (por el requisito `battery`).

### Seguridad

- El colector de temperatura solo consulta `127.0.0.1` (loopback), no envía datos del equipo a ningún servidor externo y funciona sin permisos de Administrador de DiagUSB (LHM debe correr elevado aparte).

### Corregido

- Documentación: el registro de la versión 0.1.0 anunciaba un comando `report` que nunca existió en la CLI. Los comandos reales son `diagnose`, `snapshot`, `compare`, `list-packages` y `web`; los informes HTML/DOC/PDF los genera `diagnose`. Se conserva la entrada histórica y se deja esta corrección explícita.
- Documentación: las cifras de pruebas y de paquetes quedaron unificadas con el código real (15 paquetes y 278 pruebas, de las cuales 277 pasan y 1 es manual y se omite por defecto).
- Documentación: `docs/LIMITACIONES.md` decía que la conectividad no hacía ping real; el colector ejecuta ICMP y DNS reales desde hace varias versiones. Se corrigió la limitación.
- Pruebas: `tests/run_tests.py` ahora descubre y ejecuta todos los `tests/test_*.py` con pytest, en lugar de importar una lista fija de seis suites.

## [0.1.0] - 2026-10-20

Primera versión portable para Windows 10.

### Agregado

- 12 paquetes de diagnóstico de solo lectura: impresión, redes cableadas, Wi-Fi, disco, memoria, servicios, seguridad, Windows Update, drivers, eventos críticos, contexto del sistema e inventario.
- Interfaz web local con diagnóstico rápido, revisión total, puntaje orientativo, acciones del técnico y comparación de snapshots ANTES/DESPUÉS.
- Informes Word (`.doc`) y PDF en español, con métricas, hallazgos, soluciones de la base de conocimiento y diferencias entre snapshots.
- Base de conocimiento local editable y registro persistente de análisis con búsqueda, borrado individual y borrado total.
- CLI interactiva, comandos `diagnose`, `report`, `web`, `list-packages` y `--version`. *(Corregido: el comando `report` nunca existió; ver la sección «Sin publicar».)*
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
