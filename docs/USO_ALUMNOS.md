# USO_ALUMNOS

## Estado

DiagUSB se distribuye como kit portable (`DiagUSB-kit-<version>.zip`): incluye una distribución embebida oficial de Python (python.org) más el código fuente, y corre directamente desde el pendrive en Windows 10 (validado; Windows 11 aún no probado) sin instalar nada. También existe un ejecutable opcional (`dist\diagusb\diagusb.exe`, PyInstaller). Esta guía cubre el uso del kit y el procedimiento manual para armar el pendrive de arranque con herramientas externas (que sigue siendo manual: en este repositorio no se incluyen binarios de terceros ni se automatiza el particionado o formateo del dispositivo).

## Uso del kit portable (Windows)

1. Copiar la carpeta `DiagUSB` (descomprimida del zip del kit) al pendrive.
2. En el equipo a diagnosticar, ejecutar `Iniciar_DiagUSB.cmd` (interfaz web) o `Iniciar_DiagUSB_consola.cmd` (menú de consola). Arranca en modo estándar, sin pedir permisos; para datos completos use el botón "Dar permisos de administrador" (interfaz web) o el flag `--elevar` (consola).
3. El lanzador web abre la interfaz en `http://localhost:8080`; en consola, seguir el menú.
4. En la interfaz: botón de diagnóstico o "Revisión Total" → revisar hallazgos → marcar acciones del técnico → "Guardar ANTES" / "Comparar DESPUÉS" → descargar informe Word/PDF.
5. El historial de análisis queda en "Registro de análisis" (persistente en `config/registro_analisis.json`); allí puede consultar, eliminar individualmente o vaciar el registro.
6. La elevación es a pedido: DiagUSB no pide permisos al arrancar. Si no otorga permisos de Administrador, algunos datos aparecerán parciales o como "no evaluado (requiere administrador)".

## SmartScreen y Defender

- Descargue el kit únicamente de la fuente oficial y verifique el SHA-256 antes de ejecutarlo:
  `Get-FileHash -Algorithm SHA256 .\DiagUSB-kit-<version>.zip`.
  Compare el resultado con la línea publicada en `SHA256SUMS.txt`.
- El ZIP no tiene firma Authenticode. Si SmartScreen muestra una advertencia, no continúe si el origen o el hash no coinciden. Si verificó ambos, use "Más información" → "Ejecutar de todas formas".
- El intérprete `python\python.exe` sí está firmado por Python Software Foundation. Puede comprobarlo con `Get-AuthenticodeSignature python\python.exe`.
- Si Windows marcó el ZIP como bloqueado, revise Propiedades → Desbloquear después de verificar el hash. No desactive Defender ni agregue exclusiones permanentes.
- Si Defender pone en cuarentena un archivo, restáurelo solo si el hash del kit es correcto, vuelva a verificar la integridad y reporte el caso. No agregue exclusiones permanentes para evitarlo.
- Windows 11 y los entornos con antivirus/EDR no están validados; pruebe primero en un equipo controlado.

## Uso del ejecutable opcional (Windows)

1. Copiar la carpeta `dist\diagusb\` al pendrive.
2. Ejecutar `diagusb.exe` (arranca sin pedir permisos).
3. Elegir `web` para la interfaz interactiva en `http://localhost:8080`, o seguir el menú de consola.
4. Para datos completos: `diagusb.exe --elevar web` (o el botón "Dar permisos de administrador" en la interfaz).

## Procedimiento manual para armar el pendrive de arranque

La guía completa, con versiones, SHA-256 y licencias verificadas, está en
[`docs/LIVE_USB.md`](LIVE_USB.md). Resumen:

1. Respaldar el pendrive: Ventoy lo reparticiona y DiagUSB no hace ese paso.
2. Instalar Ventoy manualmente desde su sitio oficial (<https://www.ventoy.net/>)
   con `Ventoy2Disk.exe`, fuera de este repositorio.
3. Descargar SystemRescue y memtest86+ desde sus sitios oficiales, según la
   tabla de `docs/LIVE_USB.md`.
4. Verificar cada archivo con `scripts\verificar_live_usb.cmd CARPETA` (solo
   lectura) o con `python -m diagusb live-usb --verificar CARPETA`.
5. Copiar las ISO a la partición de datos de Ventoy y la carpeta del kit
   DiagUSB al mismo pendrive.
6. Probar el arranque en un entorno controlado antes de entregar el kit.

DiagUSB no formatea, no particiona y no descarga imágenes en tiempo de
ejecución. Las herramientas sin URL, versión, SHA-256 y licencia oficiales
quedan excluidas y documentadas en `tools/tools.manifest.json`.

## Salvaguardas

- No automatizar formateo, particionado ni borrado de discos o pendrives.
- Cualquier copia asistida desde este repositorio debe empezar en modo simulación.
- La ejecución real debe exigir letra de unidad explícita, negarse sobre la unidad del sistema y pedir confirmación interactiva.
