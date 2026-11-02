# Publicación de DiagUSB

## Alcance

Este documento describe cómo se prepara y se publica una versión de DiagUSB a
partir del código del repositorio. La entrega principal es el **instalador**
(`Ejecutar DiagUSB.exe`): un solo archivo con el asistente de Inno Setup que
contiene la aplicación empaquetada en modo carpeta (`dist\DiagUSB`). El **kit
portable** (`DiagUSB-kit-<version>.zip`) queda como alternativa con Python
embebido oficial más código fuente.

El instalador no descarga nada de internet: todos los archivos viajan dentro
del `.exe`. Esa decisión es deliberada: un instalador que baja el programa al
ejecutarse es el patrón que los antivirus clasifican como descargador, y
además no sirve en un equipo sin red, que es justo donde se usa DiagUSB.

Nada de este proceso firma binarios, sube datos del cliente ni descarga
imágenes del live USB. La integridad se comprueba con SHA-256. La publicación
en GitHub la hace el workflow `.github/workflows/build-kit.yml` cuando se
empuja un tag `v*`, o el técnico con `gh` de forma manual.

## Artefactos

| Artefacto | Obligatorio | Descripción |
|---|---|---|
| `Ejecutar DiagUSB.exe` | Sí | Instalador con la aplicación en modo carpeta; instalación por usuario o copia portable a un pendrive. No descarga nada |
| `DiagUSB-kit-<version>.zip` | No | Kit portable alternativo con `python\`, `src\`, `SHA256SUMS.txt`, manifiesto de live USB y documentos legales |
| `NOTAS-<version>.md` | Sí | Notas generadas desde el CHANGELOG y los hashes reales |
| `release.json` | Sí | Versión, tag, fecha, sección del CHANGELOG y hashes de los artefactos |
| `SHA256SUMS.txt` | Sí | Hashes de todos los archivos publicados, en formato `<hash>  <archivo>` |

El instalador se reconstruye con `scripts\build_instalador.cmd`; deja
`Ejecutar DiagUSB.exe` en la raíz del repositorio. Requiere PyInstaller e Inno
Setup 6 (`winget install --id JRSoftware.InnoSetup -e`).

Las notas y el `release.json` se generan con `python -m diagusb notas-release`.
No se escriben a mano y no contienen versiones, URLs ni hashes inventados: la
versión sale de `src/diagusb/_version.py`, los hashes de los archivos reales y
el texto de cambios del `CHANGELOG.md`.

## Reglas de versión, tag y CHANGELOG

1. `src/diagusb/_version.py` es la única fuente de la versión.
2. El tag debe ser `v<version>` o `v<version>-rcN`. Cualquier otra cosa falla
   cerrado en el workflow y en `scripts\publicar_release.ps1`.
3. `CHANGELOG.md` debe tener `## [Sin publicar]` (cambios que se publican
   ahora) o, si ya se cerró, `## [<version>]`. Las notas usan primero
   `Sin publicar`; en ese caso lo dicen de forma explícita y piden renombrar la
   sección a `[<version>]` al etiquetar.
4. La sección del CHANGELOG que se use no puede estar vacía.

## Flujo local reproducible

Requisitos: Windows, PowerShell 5.1 o superior, Python 3.13 con `pytest`
instalado para la suite, y conexión a python.org la primera vez (o el ZIP
embebido ya descargado).

```powershell
# Solo el instalador (entrega principal)
scripts\build_instalador.cmd

# Publicación completa: instalador + kit + notas + SHA256SUMS
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publicar_release.ps1 -ConInstalador

# Con tag explícito y ZIP de Python ya descargado (sin red)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publicar_release.ps1 `
  -Tag v0.1.0 -ConInstalador -PythonZip C:\ruta\python-3.13.15-embed-amd64.zip
```

Parámetros:

- `-Salida`: carpeta raíz de publicación (por defecto `dist\release`). Los
  artefactos quedan en `<Salida>\<version>\`.
- `-Tag`: tag a validar (por defecto `v<version>`).
- `-PythonZip`: usa un ZIP local del Python embebido y no descarga nada.
- `-ConInstalador`: construye el instalador junto con el kit; exige
  PyInstaller e Inno Setup 6. Sin este parámetro solo se publica el kit, que
  ya no es la entrega principal.
- `-OmitirPruebas`: omite la suite **solo** para una prueba local del
  empaquetado. Nunca se usa en CI.

El script, en orden:

1. Lee y valida la versión y el tag.
2. Ejecuta `tests\run_tests.py`.
3. Arma el kit con `scripts\armar_kit.ps1` (verifica el SHA-256 del Python
   embebido y las firmas de todos sus binarios PE).
4. Verifica el ZIP con `python -m diagusb verificar-kit <zip> --estricto`:
   cada archivo listado debe existir y coincidir, no puede haber archivos
   ajenos al manifiesto (salvo `config/`, `reports/` y `tools/downloads/`) ni
   `__pycache__`.
5. Corre `scripts\probar_kit.ps1` sobre el kit descomprimido: integridad,
   firma del intérprete, versión, `list-packages`, diagnóstico real de solo
   lectura, PDF, documentos legales, manifiesto de live USB y
   `verificar-kit --estricto`.
6. Si se pidió, construye el instalador en modo carpeta y lo deja como
   `Ejecutar DiagUSB.exe` en la raíz.
7. Copia los artefactos a `dist\release\<version>\`.
8. Genera `NOTAS-<version>.md` y `release.json`.
9. Escribe `SHA256SUMS.txt` con todos los artefactos publicados.
10. Muestra el resumen con hashes y tamaños.

Si cualquier paso falla, el script termina con error y no se debe publicar la
carpeta resultante.

## Flujo en GitHub Actions

El workflow `build-kit.yml` se dispara con un tag `v*` o manualmente. Hoy el
workflow publica el kit; el instalador se construye en un equipo Windows con
Inno Setup y se sube a mano (o se adjunta al Release cuando exista `gh`):

1. Verifica que el tag coincida con `__version__`.
2. Ejecuta la suite completa.
3. Arma el kit y lo prueba.
4. Verifica el ZIP en modo estricto y genera notas, `release.json` y
   `SHA256SUMS.txt`.
5. Sube el kit, las notas, el manifiesto y las sumas como artefacto.
6. En el job de release, **recalcula** el SHA-256 de cada archivo y lo compara
   con `SHA256SUMS.txt` antes de llamar a `gh release create --notes-file`.
   Si falta un archivo o un hash no coincide, no publica nada.

Los tags que contienen `-rc` se publican como *prerelease*.

## Verificar una descarga

Con el ZIP y los demás archivos en una carpeta:

```powershell
# 1) Hash de cada archivo
Get-FileHash -Algorithm SHA256 ".\Ejecutar DiagUSB.exe"
Get-FileHash -Algorithm SHA256 .\DiagUSB-kit-0.1.0.zip

# 2) Comparar con SHA256SUMS.txt (y con la tabla de NOTAS-0.1.0.md)

# 3) Opcional: escanear el instalador antes de abrirlo
& "$env:ProgramFiles\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 `
  -File ".\Ejecutar DiagUSB.exe" -DisableRemediation

# 4) Estructura interna del kit (si se descargó el kit)
python -m diagusb verificar-kit .\DiagUSB-kit-0.1.0.zip --estricto
```

`verificar-kit` no escribe nada. Sin `--estricto` informa los archivos extra
pero no falla; con `--estricto` falla ante cualquier archivo que no figure en
`SHA256SUMS.txt`, salvo las carpetas de datos locales del kit. Termina con
código 0 solo si todo coincide.

Si no hay Python disponible, `scripts\probar_kit.ps1` hace la comprobación de
integridad con `Get-FileHash` y, para un ZIP, se puede descomprimir y comparar
a mano contra `SHA256SUMS.txt`.

## Firma

- El instalador no lleva firma Authenticode. La confianza se apoya en el
  SHA-256 publicado, en que el contenido viaja dentro del `.exe` (no descarga
  código) y en el escaneo con Windows Defender antes de publicar.
- El kit tampoco lleva firma Authenticode. La confianza se apoya en el SHA-256
  y en la firma de `python\python.exe` (Python Software Foundation).
- El workflow `build-firma.yml` puede solicitar firma a SignPath si el secreto
  `SIGNPATH_API_TOKEN` está configurado; si no lo está, publica un artefacto
  marcado como `SIN-FIRMAR`. El onefile que construye ese workflow queda solo
  para pruebas: no es la entrega publicada.
- No se debe afirmar que un artefacto está firmado si
  `Get-AuthenticodeSignature` no muestra `Status: Valid`.

## Cuándo no publicar

- La suite tiene algún fallo.
- El tag no coincide con la versión declarada.
- El CHANGELOG no tiene sección para la versión ni `Sin publicar`.
- `verificar-kit --estricto` informa una diferencia, un archivo faltante o
  `__pycache__`.
- Falta el manifiesto de live USB (`tools/tools.manifest.json`) o la guía
  `LIVE_USB.md` dentro del kit.
- El instalador se pidió pero no se generó, o Windows Defender lo marca.

## Estado de este repositorio

El flujo se validó en este equipo con un kit armado localmente, con pruebas
unitarias sobre kits sintéticos (carpeta y ZIP) y con el viaje completo del
instalador: se construyó, se publicó en `main`, se descargó desde GitHub, el
SHA-256 coincidió, Windows Defender lo escaneó sin detecciones, se instaló y
la revisión total terminó con 19 paquetes, 48 colectores, 42 correctos, 0
errores y 0 timeouts.

El tamaño y el SHA-256 concretos se informan junto con cada entrega y quedan
en `SHA256SUMS.txt`; no se escriben en este documento porque cambian con cada
compilación. **No se creó un GitHub Release** porque este equipo no tiene
`gh`; la descarga se hizo desde `raw.githubusercontent.com`. Ver
`PENDIENTES.md`.
