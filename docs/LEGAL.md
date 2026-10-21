# LEGAL

Copyright (C) 2026 Daniel Ricardo Novoa

Este programa se distribuye con la esperanza de que sea útil, pero SIN NINGUNA GARANTÍA; ni siquiera la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Véase `LICENSE` para más detalles.

## Uso permitido

- El kit debe usarse únicamente sobre equipos propios o con autorización expresa.
- Los informes pueden contener datos sensibles, incluidos nombres de equipo, nombres de usuario, direcciones IP, impresoras, puertos, eventos y otra evidencia técnica del entorno analizado.
- El kit no tiene telemetría ni envía datos a servidores de DiagUSB. El colector de red puede realizar pruebas de conectividad (ping a 8.8.8.8/1.1.1.1, puerta de enlace y DNS google.com) sin transmitir el diagnóstico.

## Datos recopilados y consentimiento

Antes de ejecutar, el lanzador informa qué datos se recogen y pide confirmación. La ejecución debe autorizarse de forma expresa sobre el equipo analizado.

Datos que pueden quedar en los resultados y en los informes:

- Identificación del equipo y del sistema: nombre, fabricante, modelo, tipo, factor de forma, versión y edición de Windows, tiempo de actividad, dominio/grupo de trabajo y nombre de usuario.
- Hardware: procesador, memoria, discos, volúmenes, espacio libre, estado SMART y otros datos técnicos del equipamiento.
- Impresión: impresoras, controladores, puertos, colas y trabajos de impresión.
- Red: adaptadores, direcciones IP y MAC, puerta de enlace, DNS, DHCP, estado y velocidad del enlace, y resultados de pruebas de conectividad.
- Wi-Fi: nombres de redes (SSID), autenticación, cifrado, modo de conexión y conexión automática. **No se recogen contraseñas ni claves Wi-Fi.**
- Software y configuración: programas instalados, servicios, controladores, actualizaciones de Windows, eventos críticos, estado de Defender/firewall e inventario general.
- Resultado del diagnóstico: hallazgos, recomendaciones, acciones del técnico, puntajes y comparaciones antes/después.

Los datos se guardan localmente en `config/` y `reports/`, dentro de la carpeta del kit o en el respaldo local de DiagUSB. No se envían a DiagUSB ni a terceros. El usuario puede eliminarlos desde la interfaz (`Configuración` → `Borrar datos locales`) o borrando esas carpetas.

## Código fuente y licencias

- Quien reciba el kit tiene derecho a acceder al código fuente completo correspondiente.
- Este repositorio constituye la oferta de fuente del código propio distribuido junto con el proyecto.
- Los binarios, ISOs y utilidades de terceros no están incluidos en el repositorio y conservan sus propias licencias y condiciones de uso.
- El detalle de herramientas externas, junto con su estado de redistribución, se registra en `tools/tools.manifest.json`.

## Terceros y redistribución

- No se incorporará código de terceros con licencia incompatible con `GPL-3.0-or-later`.
- Si más adelante se reutiliza código compatible de terceros con aprobación explícita, deberá preservarse el aviso correspondiente en `THIRD_PARTY_NOTICES.md`.