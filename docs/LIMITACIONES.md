# LIMITACIONES

Documento de limitaciones y estado actual del proyecto.

## Estado de implementacion

### Completado
- Chasis del proyecto y documentacion legal (F0)
- Sistema de paquetes con manifiestos JSON (F0)
- 13 paquetes de colectores PowerShell validados en Windows 10 (impresion, redes, wifi, conectividad, disco, memoria, servicios, seguridad, windows_update, drivers, eventos, contexto, inventario_general); los paquetes `temperatura` (numero 14) y `bateria` (numero 15) quedan como **EXPERIMENTALES** (vease Funcionalidad)
- Nucleo Python: executor, models, rules, comparator, reporter, registry, knowledge_base (KB embebida de 22 entradas + capa local editable)
- Informes Word (.doc) y PDF (.pdf) en español, con un resumen gráfico de métricas (puntaje, severidad, categorías, medidores y comparación antes/despues), hallazgos, soluciones, acciones del tecnico, mejoras sugeridas y diferencias antes/despues. Los graficos del .doc son imagenes PNG incrustadas (MHTML), no formas ni texto, por lo que se ven igual al abrir o mover el archivo
- Interfaz web local (barra lateral y tema oscuro; diagnosticos rapidos, revision total, snapshot ANTES/DESPUES + comparacion, editor de KB, registro de analisis y panel de inicio con graficas de metricas)
- Informe .doc con graficos PNG incrustados verificado en Word 16.0 (Windows 10): torta de severidad, dona de discos, barra de memoria y barras por estado se muestran como imagenes
- Arranque sin UAC: la elevacion a Administrador es a pedido (boton "Dar permisos de administrador" en la interfaz web, o flag `--elevar`); por defecto corre en modo estandar
- Kit portable con Python embebido (`DiagUSB-kit-<version>.zip`, armado con `scripts\armar_kit.ps1`), verificado con prueba de humo (`scripts\probar_kit.ps1`: integridad SHA-256, firma PSF del interprete, diagnostico real y PDF)
- Ejecutable portable con PyInstaller (`dist\diagusb\diagusb.exe`) como variante opcional, verificado con diagnose y reportes
- Registro persistente de analisis (`config/registro_analisis.json`): auto-guardado, consulta, borrado individual y borrado total
- Suite de pruebas unitarias (278 pruebas; 277 pasan y 1 manual se omite por defecto)

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
- `Get-WindowsFeature` (roles de servidor) no existe en Windows 10: `windows_features` queda vacio en estaciones
- Los "program groups" (Win32_ProgramGroup) no existen en Windows 10: se omitieron del inventario

### Legal
- Sin binarios de terceros en el repositorio
- El tecnico debe descargar herramientas externas manualmente (SystemRescue, etc.)
