# Changelog

Todos los cambios relevantes de DiagUSB se registran en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Entrega opcional del informe, apagada por defecto: envío por correo con SMTP propio (STARTTLS, SSL/TLS o sin cifrado solo para un servidor en este equipo) y copia en una carpeta local como ZIP con el informe en PDF, HTML y JSON. Nada sale del equipo sin marcar la casilla de consentimiento y pulsar el botón; DiagUSB no tiene servidor central ni sube datos por su cuenta.
- La contraseña del correo nunca se guarda en texto plano: se usa en memoria o se cifra con DPAPI de Windows en `config/correo_secreto.bin` (ámbito del usuario actual). La configuración vive en `config/entrega.json` y la bitácora local de entregas en `config/entregas.json` (máximo 50 entradas, sin contraseñas ni contenido de los informes).
- Endpoints `/api/entrega` (GET) y `/api/entrega/{config,probar,secreto,enviar,copia}` (POST), panel «Entrega del informe» en Configuración y tarjeta «Entrega» en Resultados, con consentimiento explícito por entrega.
- `informe_a_json` en `core/informe.py`: informe autocontenido en JSON para adjuntar o archivar, con el mismo contenido que el HTML y sin datos crudos de los colectores.
- Pruebas unitarias `tests/test_entrega.py` (configuración, validaciones, SMTP falso, consenso, copia ZIP, DPAPI y API HTTP).
- Cinco paquetes nuevos de solo lectura (la lista pasa de 15 a 20 paquetes): `puertos_locales` (puertos TCP/UDP a la escucha con proceso, ruta, empresa y si escuchan en todas las interfaces), `escaneo_red` (tabla de vecinos ARP y ping acotado a la puerta de enlace y a los equipos ya conocidos, sin barrido de subred), `captura_sospechosa` (proxy del usuario y del entorno, archivo `hosts` y controladores de captura Npcap/WinPcap), `gateways_dns` (rutas predeterminadas con ping a cada puerta de enlace, servidores DNS configurados y una resolución real cronometrada) y `perifericos` (teclados y dispositivos de puntero con su estado PnP).
- Diez colectores nuevos en PowerShell, todos de solo lectura y con cabecera SPDX: `get_listening_ports`, `get_network_neighbors`, `get_lan_reachability`, `get_proxy_settings`, `get_hosts_entries`, `get_capture_drivers`, `get_gateway_routes`, `get_gateway_dns_servers`, `get_dns_resolution` y `get_input_devices`.
- Siete reglas deterministas y sus entradas de conocimiento: `puerto_expuesto`, `equipos_red_no_visibles`, `trafico_red_alterado`, `gateway_no_responde`, `dns_inestable`, `teclado_no_responde` y `mouse_no_responde`; la base embebida pasa de 28 a 35 entradas. `trafico_red_alterado` informa la combinación objetiva (proxy manual remoto, entradas de `hosts` fuera de loopback, captura activa) y nunca afirma que haya una intrusión; `equipos_red_no_visibles` recuerda que algunos equipos bloquean ICMP.
- Botones nuevos en la interfaz para los cinco paquetes y para `bateria` (que existía pero no tenía botón), con bloqueo por capacidades en los paquetes que necesitan enlace de red.
- Prueba interactiva de teclado y mouse en el navegador (teclas, movimientos, clics, botones y rueda), con su resultado en la interfaz y su propia sección en los informes HTML, DOC y PDF; solo aparece en el informe cuando la prueba se ejecutó.
- Pruebas unitarias `tests/test_paquetes_fase4.py` (manifiestos, colectores de solo lectura, reglas con datos simulados y sin datos, base de conocimiento, secciones del informe y cableado de la interfaz).
- Referencia por equipo: captura del estado de los colectores cuando el equipo funciona bien, guardada en `config/referencias/<machine_id>.json` y comparada solo contra el mismo equipo (identidad estable). Las diferencias se muestran en la interfaz, en la sección de referencia del informe (HTML, DOC y PDF) y, para el paquete de impresión, se suman como hallazgos con la nueva entrada de conocimiento `referencia_impresion` (28 entradas en total).
- Endpoints `/api/referencia` (GET para el estado, POST para guardar o comparar) y botones «Guardar referencia de este equipo» y «Comparar con la referencia» en la interfaz; guardar exige identidad estable y no se permite sin ella.
- Identidad del equipo visible en el informe: fila «ID del equipo» en portada, datos del servicio y PDF, con «sin identificar» cuando no hay identidad.
- Inventario ampliado: monitores (`Win32_DesktopMonitor`), identificadores WMI de monitor (`WmiMonitorID` con nombre, fabricante y serial), dispositivos USB (`Win32_PnPEntity`), versión de TPM y datos de BIOS (fabricante, versión, fecha), y velocidad configurada de la memoria RAM.
- Pruebas unitarias `tests/test_referencia.py` (captura, comparación, diferencias de impresoras/puertos/spooler/trabajos, equipo distinto y hallazgos por paquete).
- Reglas deterministas para los cuatro síntomas que estaban declarados en los `manifest.json` sin ninguna regla: `disco_lento` (latencia media por transferencia y saturación del disco, solo sobre discos con actividad), `proceso_alto_cpu` (consumo por proceso normalizado contra la cantidad de núcleos), `seguridad_comprometida` (antivirus y firewall apagados a la vez, inicios de sesión fallidos repetidos, firmas desactualizadas) y `servicio_no_inicia` (servicio Automático detenido, con código de salida cuando existe).
- Cuatro entradas nuevas en la base de conocimiento para esos síntomas (`disco_lento`, `proceso_alto_cpu`, `seguridad_comprometida`, `servicio_no_inicia`); la base embebida pasa de 23 a 27 entradas.
- Pruebas unitarias `tests/test_reglas_huerfanas.py` sobre las cuatro reglas, incluidos los casos en que el dato no está disponible.
- Paquete de diagnóstico `temperatura` (paquete número 14): lee la temperatura del CPU desde LibreHardwareMonitor (LHM) mediante su servidor web local (`http://127.0.0.1:8085`, configurable con `DIAGUSB_LHM_URL`), sin empacar LHM ni PawnIO en el kit. EXPERIMENTAL: no validado todavía con una lectura real de sensores (ver `docs/LIMITACIONES.md`).
- Regla `cpu_caliente`: aviso a partir de 80 °C y hallazgo crítico a partir de 90 °C, sobre la máxima lectura válida del CPU (package/core), con detección previa de capacidades que bloquea el paquete (con motivo visible) si LHM no está activo, sin afectar al resto del diagnóstico.
- Entrada nueva de base de conocimiento `cpu_caliente` con soluciones (polvo, pasta térmica, ventilación, plan de energía); la base embebida pasa de 19 a 22 entradas.
- Paquete de diagnóstico `bateria` (EXPERIMENTAL, no verificado en hardware real): aparece solo en equipos con batería. Lee carga, estado y ciclos, y calcula el desgaste comparando la carga plena con la capacidad de diseño del reporte de batería (`powercfg /batteryreport`; el XML temporal se borra siempre). Regla `bateria_agotada`: aviso bajo el 60 % de la capacidad de diseño y crítico bajo el 40 %. En equipos sin batería el paquete queda oculto.
- Detección previa de capacidades extendida: además de impresoras, red y CPU, consulta si el equipo tiene batería (por el requisito `battery`).

### Cambiado

- Rediseño visual de la interfaz: barra lateral azul marino con navegación clara, fondo gris suave, tarjetas y paneles blancos con borde y sombra discretos, tipografía y estados de color con contraste sobre blanco. Los formularios, la base de conocimiento, el registro y la configuración usan el mismo lenguaje visual.
- Panel de resultados unificado: la vista de Diagnósticos, el Historial y el nuevo panel «Último análisis» de Inicio comparten la misma tarjeta de resultado (título, insignia de estado, conteos y puntaje), en lugar de estilos distintos por vista.
- Gráficos del inicio adaptados a fondo claro: el texto del puntaje y de la dona de severidad pasan a color oscuro y las pistas de los anillos a gris claro, para que se lean sobre las tarjetas blancas.
- Pruebas unitarias `tests/test_ui_tema.py` sobre la paleta, las tarjetas blancas, los resultados compartidos y los colores de los gráficos.

### Seguridad

- El colector de temperatura solo consulta `127.0.0.1` (loopback), no envía datos del equipo a ningún servidor externo y funciona sin permisos de Administrador de DiagUSB (LHM debe correr elevado aparte).

### Corregido

- Documentación: el registro de la versión 0.1.0 anunciaba un comando `report` que nunca existió en la CLI. Los comandos reales son `diagnose`, `snapshot`, `compare`, `list-packages` y `web`; los informes HTML/DOC/PDF los genera `diagnose`. Se conserva la entrada histórica y se deja esta corrección explícita.
- Documentación: las cifras de pruebas y de paquetes quedaron unificadas con el código real (20 paquetes y 347 pruebas, de las cuales 346 pasan y 1 es manual y se omite por defecto).
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
