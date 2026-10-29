# PENDIENTES

- Probar el kit armado en un Windows 10 y un Windows 11 reales; este entorno no tiene acceso a hardware de destino.
- Validar `temperatura` y `ventilador` con LibreHardwareMonitor en hardware real (sensores expuestos).
- Validar `bateria` en un portatil real con bateria (el equipo de desarrollo es de escritorio).
- Probar el arranque real del pendrive live USB en hardware (Ventoy + SystemRescue 13.02 + memtest86+ 9.00), en UEFI y Legacy, con Secure Boot activo y desactivado, y en al menos dos fabricantes; el procedimiento solo se validó por lectura y con archivos de prueba.
- Confirmar manualmente la versión de Ventoy usada y su hash en la fuente oficial: DiagUSB no la fija porque la página oficial no publica un SHA-256 directo; queda excluida de la verificación automática.
- Descargar las ISO reales de SystemRescue 13.02 y memtest86+ 9.00 y comprobar que el SHA-256 coincide con el manifiesto; en este entorno solo se copió el checksum oficial, no se descargaron las imágenes.
- Probar el panel «Pendrive de arranque» y `python -m diagusb live-usb` desde el kit armado y desde el ejecutable PyInstaller, no solo desde el código fuente.
- Validar la comparación contra la referencia en dos equipos reales distintos: la captura y la lectura de hardware se probaron en este equipo, pero falta confirmar que una referencia de otro equipo nunca se compara y que las diferencias de impresora aparecen de punta a punta en la interfaz y el informe.
- Validar los cinco paquetes de la fase 4 en un segundo equipo y en Windows 11: `puertos_locales`, `escaneo_red`, `captura_sospechosa`, `gateways_dns` y `perifericos` corrieron con sus colectores reales en el equipo de desarrollo, pero falta comprobar redes con aislamiento de clientes, equipos que bloquean ICMP y un proxy de organización real.
- Probar la prueba interactiva de teclado y mouse en un equipo con teclado o mouse con falla real; solo se validó con el hardware de este equipo.
- Validar la entrega por correo con un servidor SMTP real (STARTTLS y SSL): el envío se probó con un servidor SMTP falso y la copia ZIP con una carpeta real, pero falta un proveedor real (Gmail, Microsoft 365 u organización) y confirmar el comportamiento con contraseñas de aplicación y bloqueos de red.
- Validar DPAPI en una segunda cuenta de Windows y tras mover el kit a otro equipo: el cifrado y descifrado de la contraseña del correo se probaron en este usuario, pero falta confirmar que el archivo `config/correo_secreto.bin` no se puede descifrar fuera de ese contexto y que la interfaz pide la contraseña de nuevo.
- Probar la entrega desde el kit armado (Python embebido) y desde el ejecutable PyInstaller, no solo desde el código fuente: el envío depende de `smtplib` y de `ctypes`/DPAPI, que ya son parte de la biblioteca estándar, pero falta la corrida de humo.
- Decidir si se empaca LibreHardwareMonitor en el kit: no se hizo porque en este entorno no se pudo verificar URL oficial, versión, hash ni licencia de redistribución. Sin esos datos no se agrega ningún binario de terceros (ver `tools/tools.manifest.json` y `docs/DECISIONES.md`).
