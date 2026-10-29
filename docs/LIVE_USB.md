# Live USB: arranque con herramientas externas

## Alcance

DiagUSB es una aplicación portable para **Windows ya arrancado**: no incluye
una ISO propia, no particiona ni formatea el pendrive y no hace diagnóstico
pre-boot. Este documento cubre el complemento opcional: un pendrive multiboot
preparado con **Ventoy** que, además de la carpeta del kit DiagUSB, lleva
imágenes de terceros para dos tareas concretas:

- **SystemRescue**: rescate de un equipo que no arranca Windows, revisión de
  discos, copia de datos y herramientas Linux.
- **memtest86+**: prueba de memoria RAM fuera de Windows.

El técnico instala Ventoy y descarga las imágenes **manualmente**. DiagUSB solo
registra qué herramientas tienen datos oficiales y verifica el SHA-256 de los
archivos que el técnico ya descargó.

## Estado de las imágenes externas

Datos consultados en las fuentes oficiales el **2026-10-28**. Las imágenes no
se descargaron en el equipo de desarrollo: el SHA-256 se copió del archivo de
checksums publicado por el proyecto. Vuelva a verificarlo cada vez que
descargue una imagen.

| Herramienta | Versión | Archivo | SHA-256 | Licencia | Fuente oficial |
|---|---|---|---|---|---|
| SystemRescue | 13.02 | `systemrescue-13.02-amd64.iso` | `ad4d670b72859d887c7960142a9a9d36a3e50446694a035e254442f65d6e7572` | GPL-3.0 | <https://www.system-rescue.org/Download/> |
| memtest86+ | 9.00 | `mt86plus_9.00_x86_64.iso.zip` | `55d378c0d7d2e1a99edb6a1ff4bd5c78c179801b1f7cfe5893786c397bc19702` | GPL-2.0 | <https://www.memtest.org/> |

Checksums oficiales usados:

- <https://www.system-rescue.org/releases/13.02/systemrescue-13.02-amd64.iso.sha256>
- <https://www.memtest.org/download/v9.00/sha256sum.txt>

El manifiesto legible por la aplicación es `tools/tools.manifest.json`. La
interfaz muestra su estado en **Configuración → Pendrive de arranque** y la
línea de comandos lo resume con `python -m diagusb live-usb`.

## Requisitos

- Pendrive de 16 GB o más (SystemRescue ocupa 1318 MiB y conviene espacio para
  el kit y otras imágenes).
- Ventoy instalado manualmente desde su sitio oficial.
- Red y permiso para descargar las imágenes **una sola vez**, en el equipo del
  técnico. DiagUSB no descarga nada en tiempo de ejecución.
- Un equipo de prueba controlado antes de usar el pendrive en un cliente.

## Procedimiento

### 1. Respaldar el pendrive

Ventoy va a reparticionar el dispositivo. Copie antes cualquier dato que
necesite conservar. DiagUSB no hace este paso por usted.

### 2. Instalar Ventoy (manual)

1. Descargue Ventoy desde <https://www.ventoy.net/en/download.html>. La página
   oficial remite a SourceForge; no publica un SHA-256 único en el manifiesto
   de DiagUSB.
2. Verifique el archivo con el hash que publique la fuente oficial y consulte
   su licencia.
3. Ejecute `Ventoy2Disk.exe` y instale Ventoy en el pendrive. Esta herramienta
   es la que escribe el sector de arranque y crea la partición; no use un
   script de DiagUSB para formatear ni particionar.
4. Anote la versión de Ventoy usada. Si el arranque falla, actualice Ventoy
   antes de cambiar otras cosas.

### 3. Descargar las imágenes verificadas

Descargue los dos archivos de la tabla anterior a una carpeta local, por
ejemplo `tools\downloads`:

- `systemrescue-13.02-amd64.iso`
- `mt86plus_9.00_x86_64.iso.zip`

También puede usar el descargador del repositorio, que empieza en simulación y
solo descarga con `-Ejecutar`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch_tools.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch_tools.ps1 -Ejecutar -DownloadDir tools\downloads
```

La segunda orden descarga SystemRescue (1318 MiB) y el ZIP de memtest86+. Si
un hash no coincide, el descargador borra el archivo y falla.

### 4. Verificar los archivos

Con Python (código fuente o kit):

```powershell
python -m diagusb live-usb --verificar tools\downloads
```

Con PowerShell, sin necesidad de Python:

```powershell
scripts\verificar_live_usb.cmd tools\downloads
```

Ambos comandos son de **solo lectura**: calculan el SHA-256, comparan contra el
manifiesto y terminan con código 1 si falta un archivo o el hash no coincide.

### 5. Copiar las imágenes al pendrive

1. Descomprima `mt86plus_9.00_x86_64.iso.zip` y conserve la ISO resultante.
2. Copie `systemrescue-13.02-amd64.iso` y la ISO de memtest86+ a la partición
   de datos de Ventoy (la que Windows ve como unidad normal).
3. No copie los ZIP ni renombre las ISO: Ventoy las detecta por la extensión
   `.iso`.

### 6. Copiar el kit DiagUSB

Copie la carpeta `DiagUSB` del kit portable a la misma partición de datos. El
kit se ejecuta después de arrancar Windows, no desde Ventoy:

1. Arranque Windows desde el disco interno del equipo a diagnosticar.
2. Abra la carpeta `DiagUSB` del pendrive.
3. Ejecute `Iniciar_DiagUSB.cmd` o `Iniciar_DiagUSB_consola.cmd`.

### 7. Arrancar las herramientas externas

1. Reinicie el equipo y abra el menú de arranque (F8, F12, F11 o ESC según el
   fabricante).
2. Elija el pendrive. Ventoy muestra la lista de imágenes.
3. Elija **SystemRescue** para rescate o **memtest86+** para memoria.
4. Para volver a Windows, reinicie y elija el disco interno.

## Herramientas excluidas

El manifiesto falla cerrado: si falta URL, versión, SHA-256, licencia o dominio
oficial, la herramienta no se integra y queda registrada con su motivo.

| Herramienta | Estado | Motivo |
|---|---|---|
| Ventoy | Excluida de la verificación automática | La página oficial no publica URL directa, versión ni SHA-256; remite a SourceForge. Se instala manualmente. |
| WinPE | Excluida | Requiere Windows ADK y licencia de Microsoft; no hay un binario único redistribuible con hash verificable. |
| Sysinternals | Excluida | La licencia de Microsoft no permite redistribuir los binarios en un kit de terceros. |
| Npcap | Excluida | La redistribución requiere licencia OEM. DiagUSB solo detecta controladores ya instalados. |

## Seguridad, licencias y límites

- **No se redistribuye ningún binario de terceros** en este repositorio ni en
  el kit. El técnico descarga las imágenes desde su fuente oficial.
- **SystemRescue** se distribuye bajo GPL-3.0 según su sitio oficial.
  **memtest86+** se distribuye bajo GPL-2.0. Consulte los textos completos en
  cada proyecto antes de redistribuir un pendrive.
- **Secure Boot**: memtest86+ 9.00 todavía no está firmado por Microsoft; el
  fabricante indica que hay que agregar su certificado o desactivar Secure
  Boot temporalmente. SystemRescue y Ventoy tienen sus propias instrucciones;
  siga la documentación oficial y no desactive Secure Boot de forma permanente.
- **Sin prueba de hardware en este equipo**: el procedimiento y los hashes
  están verificados por lectura, pero el arranque real en BIOS/UEFI, con
  Secure Boot y en distintos fabricantes queda pendiente. Ver `PENDIENTES.md`.
- **Sin automatización de formateo o particionado**: Ventoy2Disk es la única
  herramienta que escribe la estructura del pendrive, y la ejecuta el técnico.
  `scripts\armar_pendrive.ps1` solo copia el kit a una unidad ya preparada y
  verifica hashes; no formatea.
- **Datos del cliente**: las imágenes externas no reciben datos de DiagUSB. Los
  informes se generan y quedan en el equipo o en la carpeta que el técnico
  elija, según la configuración de entrega.

## Problemas frecuentes

- **El equipo no muestra el pendrive en el menú de arranque**: revise que
  Ventoy esté instalado en modo UEFI o Legacy según el firmware, y que el
  arranque seguro esté configurado como indica Ventoy.
- **Ventoy no lista una ISO**: confirme que el archivo termina en `.iso` y que
  está en la partición de datos, no dentro de una carpeta comprimida.
- **El hash no coincide**: no use el archivo. Vuelva a descargarlo desde la
  fuente oficial y repita la verificación.
- **memtest86+ no arranca con Secure Boot activo**: es la limitación de firma
  descrita arriba; use el certificado del proyecto o desactive Secure Boot
  solo durante la prueba.
- **SystemRescue no encuentra el disco**: verifique el modo SATA/NVMe en el
  firmware y consulte el manual de SystemRescue; no modifique discos sin
  respaldo.
