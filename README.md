# DiagUSB

Copyright (C) 2026 Daniel Ricardo Novoa

DiagUSB es un kit de diagnóstico para soporte de infraestructura TI pensado para ejecutarse desde un pendrive. Diagnostica Windows 10/11 con 12 paquetes de colectores PowerShell, reglas de detección de problemas, base de conocimiento editable, informes Word/PDF en español y un registro persistente de análisis.

## Características

- **12 paquetes de diagnóstico**: impresión, redes cableadas, WiFi, disco, memoria, servicios, seguridad, Windows Update, drivers, eventos críticos, contexto del sistema e inventario general.
- **Interfaz web local** (`http://localhost:8080`) con botones de diagnóstico rápido, revisión total, snapshot ANTES/DESPUÉS con comparación de cambios, y acciones del técnico.
- **Registro persistente de análisis**: cada diagnóstico ejecutado queda guardado automáticamente en `config/registro_analisis.json`. Botón "Registro de análisis" para consultar el detalle, eliminar análisis individuales o vaciar el registro completo.
- **Informes Word (.doc) y PDF (.pdf)** en español, con hallazgos, soluciones de la base de conocimiento, acciones del técnico, mejoras sugeridas y diferencias antes/después.
- **Base de conocimiento local**: 19 entradas embebidas más capa editable en `config/base_conocimiento.json` (alta/edición/baja desde la interfaz, buscador por palabra clave).
- **Auto-elevación a Administrador** (UAC): al iniciar solicita permisos; flag `--no-elevate` o variable `DIAGUSB_NO_ELEVATE=1` para desactivarla.
- **Ejecutable portable** (`dist/diagusb/diagusb.exe`) construido con PyInstaller, sin necesidad de Python en el equipo destino.

## Requisitos

- Windows 10/11 (PowerShell 5.1 incluido).
- Para la versión portable: nada más. Para desarrollo: Python 3.12.

## Uso rápido

Versión portable (pendrive):

```
dist\diagusb\diagusb.exe            # menú interactivo (pide Administrador)
dist\diagusb\diagusb.exe web        # servidor web + navegador (pide Administrador)
dist\diagusb\diagusb.exe --no-elevate web   # sin elevar
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

1. Acepte el diálogo de Administrador (necesario para datos completos).
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
python tests\run_tests.py           # suite completa (sin dependencias externas)
scripts\build_exe.cmd               # reconstruye dist\diagusb\diagusb.exe
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
- `scripts/`: utilidades locales para el técnico.

## Restricciones del proyecto

- Interfaz, informes y documentación en español.
- Código propio bajo `GPL-3.0-or-later`.
- Solo biblioteca estándar de Python; el PDF se genera con un motor propio sin dependencias (`src/diagusb/core/informe.py`).
- Sin telemetría, sin conexiones salientes del producto final y sin modificación de la configuración del equipo analizado (los colectores son de solo lectura).
- No se incluyen binarios o ISOs de terceros; ver `tools/tools.manifest.json`.

## Política de firma de código

- Firma de código gratuita provista por SignPath.io, certificado de SignPath Foundation.
- Roles: Autor, Committer y Revisor/Aprobador: Daniel Ricardo Novoa (https://github.com/AurigaNet).
- Política de privacidad: "Este programa no transmite información a otros sistemas de red a menos que lo solicite expresamente el usuario o quien lo opera".
- Cómo verificar el ejecutable:
  - Firma digital: clic derecho sobre `diagusb.exe` → Propiedades → Firmas digitales, o en PowerShell `Get-AuthenticodeSignature dist\diagusb\diagusb.exe` (debe mostrar `Status: Valid`).
  - Integridad de archivos: comparar los hashes listados en `SHA256SUMS.txt` con `Get-FileHash -Algorithm SHA256` de cada archivo.

## Antivirus y EDR

- En equipos con EDR gestionado, el ejecutable puede requerir autorización por firmante o por hash antes de ejecutarse.
- La regla ASR de Microsoft Defender "Bloquear procesos no confiables y sin firmar que se ejecutan desde USB" bloquea las versiones sin firma.
- Las versiones SIN-FIRMAR (`diagusb-SIN-FIRMAR.zip`) son solo para pruebas; no se recomienda su uso en equipos de clientes.

Este programa se distribuye con la esperanza de que sea útil, pero SIN NINGUNA GARANTÍA; ni siquiera la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Véase `LICENSE` para más detalles.
