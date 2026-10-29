# LIMITACIONES

Documento de limitaciones y estado actual del proyecto.

## Estado de implementacion

### Completado
- Chasis del proyecto y documentacion legal (F0)
- Sistema de paquetes con manifiestos JSON (F0)
- 20 paquetes de colectores PowerShell; los 13 validados en Windows 10 son impresion, redes, wifi, conectividad, disco, memoria, servicios, seguridad, windows_update, drivers, eventos, contexto e inventario_general. Los paquetes `temperatura` (numero 14) y `bateria` (numero 15) quedan como **EXPERIMENTALES**. Los cinco paquetes de red y perifericos (numero 16 a 20: `puertos_locales`, `escaneo_red`, `captura_sospechosa`, `gateways_dns` y `perifericos`) se ejecutaron con sus colectores reales en el equipo de desarrollo, pero no se validaron en un segundo equipo ni en Windows 11 (vease Funcionalidad)
- Nucleo Python: executor, models, rules, comparator, reporter, registry, knowledge_base (KB embebida de 35 entradas + capa local editable)
- Informes Word (.doc) y PDF (.pdf) en español, con un resumen gráfico de métricas (puntaje, severidad, categorías, medidores y comparación antes/despues), hallazgos, soluciones, acciones del tecnico, mejoras sugeridas y diferencias antes/despues. Los graficos del .doc son imagenes PNG incrustadas (MHTML), no formas ni texto, por lo que se ven igual al abrir o mover el archivo
- Interfaz web local (barra lateral azul marino y tarjetas blancas; diagnosticos rapidos, revision total, snapshot ANTES/DESPUES + comparacion, editor de KB, registro de analisis, entrega opcional y panel de inicio con graficas de metricas)
- Informe .doc con graficos PNG incrustados verificado en Word 16.0 (Windows 10): torta de severidad, dona de discos, barra de memoria y barras por estado se muestran como imagenes
- Arranque sin UAC: la elevacion a Administrador es a pedido (boton "Dar permisos de administrador" en la interfaz web, o flag `--elevar`); por defecto corre en modo estandar
- Kit portable con Python embebido (`DiagUSB-kit-<version>.zip`, armado con `scripts\armar_kit.ps1`), verificado con prueba de humo (`scripts\probar_kit.ps1`: integridad SHA-256, firma PSF del interprete, diagnostico real y PDF)
- Ejecutable portable con PyInstaller (`dist\diagusb\diagusb.exe`) como variante opcional, verificado con diagnose y reportes
- Registro persistente de analisis (`config/registro_analisis.json`): auto-guardado, consulta, borrado individual y borrado total
- Entrega opcional del informe (`core/entrega.py`): correo SMTP y copia en carpeta local como ZIP (PDF, HTML y JSON), apagada por defecto y con consentimiento explicito en cada envio; contrasena del correo en memoria o cifrada con DPAPI de Windows, nunca en texto plano
- Suite de pruebas unitarias (358 pruebas; 357 pasan y 1 manual se omite por defecto)

### Pendiente de validacion
- Windows 11 (validado hasta ahora en Windows 10)
- Importacion del informe `.doc` (MHTML) en Google Docs: no se pudo probar sin cuenta; Google Docs no documenta soporte de MHTML como formato de importacion (use Word o el PDF)
- Comportamiento bajo antivirus/EDR (bloqueo de PowerShell, escaneo de la carpeta del kit, cuarentena de scripts `.ps1`)
- Prueba del boton "Dar permisos de administrador" (UAC) del kit y del exe portable en una segunda cuenta/maquina
- Kit armado con Python embebido: comportamiento bajo EDR (igual que el exe) y copia al pendrive en volumenes formateados en distintos sistemas de archivos
- Diferentes contextos de permisos (equipo sin elevacion disponible)

## Restricciones conocidas

### Integridad
- El manifiesto de hashes (`manifiesto_hashes.json`) detecta corrupcion y modificaciones accidentales de los colectores, pero NO protege contra un atacante con acceso de escritura al pendrive: puede modificar el manifiesto junto con los colectores.
- El kit se apoya en `SHA256SUMS.txt` (integridad de todos los archivos) y en la firma del interprete embebido (Python Software Foundation). El kit como conjunto NO lleva firma digital propia; la proteccion contra un atacante con acceso de escritura es la firma digital del ejecutable (variante opcional, fuera del alcance actual).

### Arquitectura
- PowerShell 5.1 minimo para colectores
- Python 3.13 para la capa de orquestacion (solo biblioteca estandar; el PDF se genera con un motor propio en `src/diagusb/core/informe.py`, sin dependencias externas)
- La base de conocimiento y el registro de analisis se guardan en `config/` local (no sincronizan entre equipos)
- El registro de analisis conserva hasta 200 entradas; se descartan automaticamente las mas viejas

### Funcionalidad
- El paquete `temperatura` depende de LibreHardwareMonitor (LHM), una herramienta externa que DiagUSB **no empaca ni instala**: el tecnico debe descargarla, instalar PawnIO si el hardware lo requiere y ejecutar LHM como Administrador con el servidor web local activo (`http://127.0.0.1:8085`, configurable con la variable de entorno `DIAGUSB_LHM_URL`, solo loopback). Sin LHM activo el paquete queda bloqueado y el resto del diagnostico funciona normalmente. El paquete queda marcado EXPERIMENTAL: LHM no estuvo disponible en el equipo de prueba, por lo que no se valido con una lectura real de sensores; se validaron con pruebas unitarias la regla, los umbrales (80/90 °C), los vacios y el bloqueo por capacidades.
- La temperatura del CPU en equipos virtualizados tipicamente no se expone a LHM (no se ajusta al hardware fisico): se trata como paquete no disponible, no como falla.
- El paquete `bateria` esta marcado NO VERIFICADO EN HARDWARE REAL: el equipo de prueba es una computadora de escritorio sin bateria, de modo que el reporte de `powercfg /batteryreport` y el calculo de desgaste se validaron con datos simulados y con el bloqueo real del paquete en equipos sin bateria (queda oculto, no es error). El desgaste puede no coincidir con la lectura que muestra el propio fabricante porque powercfg informa la carga plena conservada por el controlador.
- En equipos sin bateria el paquete se oculta por la deteccion previa de capacidades; `Win32_Battery` tambien cubre UPS: si el equipo detecta un UPS como bateria, la lectura describe el UPS, no una bateria interna.
- La tendencia (evolucion del puntaje entre analisis) se muestra solo en la interfaz web (pestana Historial); todavia NO se incluye en los informes Word/PDF.
- El informe `.doc` usa MHTML con imagenes PNG y VML. Se verifico en Word 16.0. **LibreOffice 26.2.6 NO importa este MHTML**: al abrir el `.doc` (o el mismo archivo renombrado a `.mht`) muestra el texto del MIME/base64 en lugar del documento. Para equipos sin Word, use el PDF, que es autocontenido y se abre en cualquier visor.
- El PDF usa fuentes estandar con codificacion WinAnsi (Latin-1). Los caracteres fuera de ese rango se reemplazan por `?`; los informes estan redactados en español para evitar el problema.
- Los colectores de seguridad (eventos) y algunos inventarios requieren permisos de Administrador para datos completos (en modo estandar se ven parciales o como 'No evaluado (requiere administrador)')
- La verificacion de conectividad ejecuta ping ICMP real y consulta DNS; el resultado depende del firewall y del segmento de red del equipo
- `escaneo_red` no hace un barrido de subred: lee la tabla de vecinos (ARP/neighbor) del adaptador activo y hace ping acotado a la puerta de enlace y a un maximo de 8 equipos ya conocidos. Un equipo que bloquee ICMP puede estar conectado y no responder; el texto del hallazgo lo aclara y no se presenta como equipo ausente
- `puertos_locales` marca como expuestos los procesos de terceros (fuera de `%SystemRoot%`) que escuchan en `0.0.0.0` o `::`; los servicios propios de Windows no se cuentan. Un mismo proceso puede aparecer dos veces (IPv4 e IPv6) para el mismo puerto
- `captura_sospechosa` informa combinaciones objetivas (proxy manual remoto, entradas del archivo `hosts` fuera de loopback, variables de proxy, controladores Npcap/WinPcap activos) y nunca afirma que haya una intrusion: la decision queda en el tecnico
- `perifericos` se apoya en el estado PnP que reporta Windows y en una prueba interactiva del navegador (teclas, movimiento, clics y rueda). Esa prueba confirma que Windows entrega la entrada al navegador, pero no mide la calidad ni el desgaste del teclado o del mouse
- La prueba DNS de `gateways_dns` resuelve un unico nombre (`%USERDNSDOMAIN` si existe, si no `www.msftconnecttest.com`) y lo cronometra; una resolucion lenta puede deberse al servidor DNS, al enlace o al propio nombre de prueba
- La entrega por correo usa el servidor SMTP que configure el tecnico: DiagUSB no incluye servidor, credenciales ni servicio de correo. Muchos proveedores exigen contrasena de aplicacion o bloquean el envio desde redes ajenas; el error del servidor se muestra tal cual y queda en la bitacora local
- La opcion «sin cifrado» solo se acepta para un servidor SMTP en el propio equipo (`127.0.0.1`, `localhost` o `::1`). Con un servidor remoto la configuracion se rechaza para no enviar credenciales en claro
- El cifrado de la contrasena usa DPAPI de Windows y queda ligado al usuario y al equipo actuales: al copiar el kit a otro equipo hay que volver a escribirla. En sistemas sin DPAPI la contrasena solo se usa en memoria durante el envio
- La copia en carpeta no es una nube propia: escribe un ZIP en la carpeta que el tecnico elija (por ejemplo, una carpeta que ya sincronice con su nube personal). DiagUSB no sube nada ni conserva copias fuera de esa carpeta
- La bitacora de entregas (`config/entregas.json`) guarda fecha, tipo, destinatarios o carpeta, adjuntos y resultado; no guarda contrasenas ni el contenido de los informes, y se limita a 50 entradas
- El live USB no se probo en hardware real: el procedimiento, los hashes y la deteccion de archivos se validaron por lectura y con archivos de prueba, pero falta arrancar SystemRescue y memtest86+ en equipos BIOS/UEFI reales y con Secure Boot activo
- DiagUSB no formatea, no particiona y no instala Ventoy: el tecnico usa `Ventoy2Disk.exe` por su cuenta. `scripts\armar_pendrive.ps1` solo copia el kit a una unidad ya preparada y verifica hashes
- Las imagenes de SystemRescue 13.02 y memtest86+ 9.00 no se descargaron en este equipo: el SHA-256 se copio del checksum oficial el 2026-10-28. Vuelva a verificarlo despues de descargar y antes de usar el pendrive
- Ventoy, WinPE, Sysinternals y Npcap estan excluidos de la verificacion automatica: Ventoy no publica URL directa, version ni SHA-256 en su pagina oficial; WinPE requiere ADK y licencia de Microsoft; Sysinternals no permite redistribucion; Npcap requiere licencia OEM
- memtest86+ 9.00 aun no esta firmado por Microsoft para Secure Boot; el arranque puede requerir agregar el certificado del proyecto o desactivar Secure Boot de forma temporal, segun la documentacion oficial
- La version de Ventoy no queda fijada por DiagUSB: si el arranque falla, actualicela desde su sitio oficial y revise la configuracion de Secure Boot antes de cambiar otros parametros
- `Get-WindowsFeature` (roles de servidor) no existe en Windows 10: `windows_features` queda vacio en estaciones
- Los "program groups" (Win32_ProgramGroup) no existen en Windows 10: se omitieron del inventario

### Legal
- Sin binarios de terceros en el repositorio
- El tecnico debe descargar herramientas externas manualmente (SystemRescue, etc.)
