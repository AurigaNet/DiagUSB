# PENDIENTES

- Probar el kit armado en un Windows 10 y un Windows 11 reales; este entorno no tiene acceso a hardware de destino.
- Validar `temperatura` y `ventilador` con LibreHardwareMonitor en hardware real (sensores expuestos).
- Validar `bateria` en un portatil real con bateria (el equipo de desarrollo es de escritorio).
- Probar el arranque real del pendrive live USB en hardware (Ventoy + SystemRescue + memtest86+).
- Validar la comparación contra la referencia en dos equipos reales distintos: la captura y la lectura de hardware se probaron en este equipo, pero falta confirmar que una referencia de otro equipo nunca se compara y que las diferencias de impresora aparecen de punta a punta en la interfaz y el informe.
- Validar los cinco paquetes de la fase 4 en un segundo equipo y en Windows 11: `puertos_locales`, `escaneo_red`, `captura_sospechosa`, `gateways_dns` y `perifericos` corrieron con sus colectores reales en el equipo de desarrollo, pero falta comprobar redes con aislamiento de clientes, equipos que bloquean ICMP y un proxy de organización real.
- Probar la prueba interactiva de teclado y mouse en un equipo con teclado o mouse con falla real; solo se validó con el hardware de este equipo.
- Decidir si se empaca LibreHardwareMonitor en el kit: no se hizo porque en este entorno no se pudo verificar URL oficial, versión, hash ni licencia de redistribución. Sin esos datos no se agrega ningún binario de terceros (ver `tools/tools.manifest.json` y `docs/DECISIONES.md`).
