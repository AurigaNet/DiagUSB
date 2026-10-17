# DiagUSB

Copyright (C) 2026 Daniel Ricardo Novoa

DiagUSB es un kit de diagnóstico para soporte de infraestructura TI pensado para ejecutarse desde un pendrive. Diagnostica Windows 10/11 con 12 paquetes de colectores PowerShell, reglas de detección de problemas, base de conocimiento editable, informes Word/PDF en español y un registro persistente de análisis.

## Características

- **12 paquetes de diagnóstico**: impresión, redes cableadas, WiFi, disco, memoria, servicios, seguridad, Windows Update, drivers, eventos críticos, contexto del sistema e inventario general.
- **Interfaz web local** (`http://localhost:8080`) con barra lateral, tema oscuro, botones de diagnóstico rápido, revisión total, snapshot ANTES/DESPUÉS con comparación de cambios, acciones del técnico y un panel de inicio con gráficas del estado del equipo.
- **Puntaje orientativo**: cada análisis calcula un puntaje de salud (0–100), cobertura de colectores, hallazgos por severidad, estado por categoría y medidores, con tendencia entre análisis del mismo paquete. Se muestra en la interfaz y en los informes (detalles en `docs/PUNTAJE.md`). El puntaje orientativo **no reemplaza** al diagnóstico ni refleja necesariamente el estado general del equipo cuando se ejecuta un único paquete.
- **Registro persistente de análisis**: cada diagnóstico ejecutado queda guardado automáticamente en `config/registro_analisis.json`. Botón "Registro de análisis" para consultar el detalle, eliminar análisis individuales o vaciar el registro completo.
- **Informes Word (.doc) y PDF (.pdf)** en español, con un **resumen gráfico** de métricas (puntaje, severidad, categorías, medidores y comparación antes/después), hallazgos, soluciones de la base de conocimiento, acciones del técnico, mejoras sugeridas y diferencias antes/después.
- **Base de conocimiento local**: 19 entradas embebidas más capa editable en `config/base_conocimiento.json` (alta/edición/baja desde la interfaz, buscador por palabra clave).
- **Arranque sin UAC**: DiagUSB inicia sin pedir permisos (modo estándar). Los permisos de Administrador se solicitan solo a pedido: botón "Dar permisos de administrador" en la interfaz web, o flag `--elevar` en la línea de comandos.
- **Kit portable** (`DiagUSB-kit-<version>.zip`): incluye una distribución embebida oficial de Python (python.org) más el código fuente, sin necesidad de instalar Python en el equipo destino. Es la distribución principal y se arma con `scripts\armar_kit.ps1`.
- **Ejecutable portable opcional** (`dist/diagusb/diagusb.exe`) construido con PyInstaller, como variante sin Python embebido.

## Requisitos

- Windows 10/11 (PowerShell 5.1 incluido).
- Para el kit: nada más (trae su propio intérprete en `python\`). Para el ejecutable: nada más. Para desarrollo: Python 3.13 (o 3.12+).

## Uso rápido

Kit portable (recomendado):

1. Descargue `DiagUSB-kit-<version>.zip` y descomprímalo (queda una carpeta `DiagUSB`).
2. Copie la carpeta `DiagUSB` al pendrive.
3. En el equipo a diagnosticar, ejecute `Iniciar_DiagUSB.cmd` (interfaz web) o `Iniciar_DiagUSB_consola.cmd` (menú de consola).

El kit no requiere Python instalado: usa el intérprete embebido en `python\` (firmado por Python Software Foundation).

Ejecutable portable (variante opcional):

```
dist\diagusb\diagusb.exe            # menú interactivo (modo estándar)
dist\diagusb\diagusb.exe web        # servidor web + navegador (modo estándar)
dist\diagusb\diagusb.exe --elevar web        # pedir permisos de Administrador
```

Desde el código (desarrollo):

```
python -m diagusb                    # menú interactivo
python -m diagusb web                # interfaz web en http://localhost:8080
python -m diagusb diagnose --package impresion --symptom la_impresora_no_imprime
python -m diagusb snapshot -o antes.json        # instantánea con colectores reales
python -m diagusb snapshot -p disco -o disco_antes.json
python -m diagusb compare antes.json despues.json
python -m diagusb list-packages
```

### Interfaz web

1. La interfaz arranca en modo estándar; use el botón "Dar permisos de administrador" si necesita datos completos.
2. Haga clic en un botón de diagnóstico o en "Revisión Total".
3. Revise los hallazgos; marque estado y acciones implementadas por problema.
4. "Guardar ANTES" → realice los cambios en el equipo → "Comparar DESPUÉS".
5. Descargue el informe Word o PDF.
6. Abra "Registro de análisis" para consultar el historial guardado.

### Registro de análisis

- Cada ejecución de diagnóstico (individual o revisión total) se guarda automáticamente en `config/registro_analisis.json` (máximo 200 entradas, se descartan las más viejas).
- El botón "Registro de análisis" muestra el historial con buscador: ver detalle (hallazgos, soluciones, recomendaciones, colectores), eliminar análisis individual o vaciar el registro completo.

## Pruebas y build

```
python tests\run_tests.py                        # suite completa (110 pruebas, sin dependencias externas)
scripts\armar_kit.cmd -Salida dist\kit           # arma el kit (Python embebido + fuente) y lo comprime
scripts\probar_kit.ps1 -Kit dist\kit\DiagUSB     # prueba de humo del kit
scripts\build_exe.cmd                            # reconstruye dist\diagusb\diagusb.exe (variante opcional)
```

## Estructura

- `src/diagusb/`: paquete principal (`core/` motor, `packages/` los 12 paquetes de diagnóstico, `web_server.py` interfaz local).
- `collectors/`: utilidades PowerShell compartidas (`_common.ps1`).
- `config/`: datos locales (base de conocimiento editable y registro de análisis) — no versionados.
- `docs/`: decisiones, legal, limitaciones, matriz de permisos y guía para alumnos.
- `tests/`: pruebas unitarias (modelos, reglas, registry, KB, informes, elevación, registro).
- `reports/`: snapshots y salidas locales — no versionado.
- `build/`, `dist/`: salidas de PyInstaller — no versionadas.
- `tools/`: manifiesto de herramientas externas.
- `scripts/`: utilidades locales para el técnico (`armar_kit.*`, `probar_kit.ps1`, `armar_pendrive.*`, `build_exe.cmd`).
- `scripts/kit/`: plantillas de los lanzadores del kit (`Iniciar_DiagUSB.cmd`, `Iniciar_DiagUSB_consola.cmd`).

## Restricciones del proyecto

- Interfaz, informes y documentación en español.
- Código propio bajo `GPL-3.0-or-later`.
- Solo biblioteca estándar de Python; el PDF se genera con un motor propio sin dependencias (`src/diagusb/core/informe.py`).
- Sin telemetría, sin conexiones salientes del producto final y sin modificación de la configuración del equipo analizado (los colectores son de solo lectura).
- No se incluyen binarios o ISOs de terceros; ver `tools/tools.manifest.json`.

## Firma de código e integridad

- Firma de código gratuita provista por SignPath.io, certificado de SignPath Foundation.
- Roles: Autor, Committer y Revisor/Aprobador: Daniel Ricardo Novoa (https://github.com/AurigaNet).
- Política de privacidad: "Este programa no transmite información a otros sistemas de red a menos que lo solicite expresamente el usuario o quien lo opera".

### Kit portable (distribución principal)

El kit no es un ejecutable propio: es código fuente Python que corre con el intérprete embebido de Python (python.org). La confianza se apoya en:

- **Firma del intérprete**: los binarios de `python\` están firmados por Python Software Foundation (y por Microsoft para `vcruntime*`). Verifique con `Get-AuthenticodeSignature python\python.exe` (debe mostrar `Status: Valid`); el lanzador `Iniciar_DiagUSB.cmd` ya comprueba esa firma antes de arrancar.
- **Integridad de archivos**: `SHA256SUMS.txt` (dentro del kit) usa el formato `<hash>  <ruta>` con `/` y rutas relativas a la raíz del zip (`DiagUSB/...`). Verifique con:
  - `scripts\probar_kit.ps1 -Kit <carpeta del kit>` (verifica todo el kit, la firma, un diagnóstico real y el PDF).
  - `sha256sum -c SHA256SUMS.txt`, desde la carpeta del kit (Linux/macOS/Git Bash).

### Ejecutable portable (variante opcional)

- Firma digital: clic derecho sobre `diagusb.exe` → Propiedades → Firmas digitales, o en PowerShell `Get-AuthenticodeSignature dist\diagusb\diagusb.exe` (debe mostrar `Status: Valid`).
- Integridad: el `SHA256SUMS.txt` del release usa el formato `<hash>  <ruta>` con `/`, con las rutas tal como quedan al descomprimir el zip (`diagusb/diagusb.exe`, `diagusb/_internal/manifiesto_hashes.json`) y el nombre del zip en una línea aparte. Verifique con el zip y la carpeta `diagusb` en el mismo directorio:
  - PowerShell: `Get-FileHash -Algorithm SHA256 diagusb\diagusb.exe, diagusb\_internal\manifiesto_hashes.json, diagusb-SIN-FIRMAR.zip`
  - `sha256sum -c SHA256SUMS.txt` (Linux/macOS/Git Bash)

## Antivirus y EDR

- En equipos con EDR gestionado, tanto el kit como el ejecutable pueden requerir autorización por firmante o por hash antes de ejecutarse.
- El kit usa el intérprete firmado por Python Software Foundation; los scripts `.ps1` no están firmados y algunos EDR pueden inspeccionarlos o bloquearlos.
- La regla ASR de Microsoft Defender "Bloquear procesos no confiables y sin firmar que se ejecutan desde USB" afecta al ejecutable sin firma (`diagusb-SIN-FIRMAR.zip`), que es solo para pruebas; no se recomienda su uso en equipos de clientes.

Este programa se distribuye con la esperanza de que sea útil, pero SIN NINGUNA GARANTÍA; ni siquiera la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Véase `LICENSE` para más detalles.
