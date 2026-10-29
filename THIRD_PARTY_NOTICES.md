# THIRD_PARTY_NOTICES

## Python embebido

El kit portable incluye Python 3.13.15 (distribución embeddable oficial para Windows amd64) de Python Software Foundation. Los binarios se redistribuyen sin modificaciones bajo la licencia de Python; el kit agrega un archivo `.pth` para ajustar el arranque. El texto de la licencia está en `python\LICENSE.txt` dentro del kit.

- Sitio oficial: https://www.python.org/
- Licencia: https://docs.python.org/3/license.html
- Los binarios PE de `python\` están firmados por Python Software Foundation, salvo los `vcruntime*`, firmados por Microsoft Corporation.
- El ZIP descargado se verifica por SHA-256 antes de usarlo.

## Imágenes externas del live USB (no incluidas)

DiagUSB no redistribuye imágenes de arranque. La guía `docs/LIVE_USB.md` permite al técnico descargar SystemRescue 13.02 (GPL-3.0) y memtest86+ 9.00 (GPL-2.0) desde sus fuentes oficiales y verificar su SHA-256 con `scripts\verificar_live_usb.ps1`. Esos binarios no forman parte de este repositorio ni del kit distribuido; sus licencias y textos completos están en cada proyecto. Ventoy, WinPE, Sysinternals y Npcap quedan excluidos de la verificación automática y se documentan con su motivo en `tools/tools.manifest.json`.

## LibreHardwareMonitor (LHM) incluido en el kit (verificado 2026-10-29)

- Versión: v0.9.6 (última publicada 2026-02-14, tag v0.9.6)
- Origen: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/tag/v0.9.6
- Asset usado: LibreHardwareMonitor.zip (build para .NET Framework, sin runtime adicional)
- SHA-256 verificado: 086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001 (coincide con digest de GitHub API)
- Licencia: MPL-2.0 (compatible con GPL-3.0-or-later); texto completo disponible en el repo oficial
- Redistribuible: sí, dentro del kit, con su licencia acompañada
- Ubicación en kit: tools/lhm/ (extraído al armar el kit por scripts/armar_kit.ps1)
- Configuración generada: LibreHardwareMonitor.config (servidor web 127.0.0.1, puerto 8085, sólo lectura)
- Nota de seguridad: LHM requiere elevación para sensores; el kit no pide UAC al arrancar; el paquete ofrece el botón existente de elevar. Si hay otro LHM corriendo en 8085 que no lanzó DiagUSB, se reutiliza sin cerrarlo.

## PawnIO incluido en el kit como agregacion (verificado 2026-10-29)

- Versión: 2.2.0 (publicado 2026-03-15, tag v2.2.0 en https://github.com/namazso/PawnIO.Setup)
- Origen: https://github.com/namazso/PawnIO (codigo); https://pawnio.eu/ (sitio oficial)
- Instalador: PawnIO_setup.exe (3,4 MB)
- SHA-256 verificado: 1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032 (coincide con digest de GitHub)
- Firma Authenticode: Valid (SignerCertificate F380DCC9F706E2756A5047B832FFE719E1BC35F5; Status Valid)
- Licencia: GPL-2.0 (repositorio oficial namazso/PawnIO y namazso/PawnIO.Modules). El texto completo se incluye en tools/pawnio/LICENSE (copiado del repositorio) y se indica en THIRD_PARTY_NOTICES.md.
- Redistribuible como agregacion: sí. El instalador es un programa independiente (binario firmado, no enlazado con DiagUSB). Se distribuye junto al kit; la obligación de la licencia se cumple incluyendo el texto y citando la fuente exacta.
- Ubicación en kit: tools/downloads/PawnIO_setup.exe (tambien disponible en tools/pawnio/ tras install); se lanza como servicio temporal solo con consentimiento del técnico.
- Nota: no se instala automaticamente; el paquete ofrece el botón "Instalar controlador (requiere administrador)" y, tras medir, ofrece desinstalarlo (opción por defecto marcada, documentada).

## Antivirus y falsos positivos

LibreHardwareMonitor y PawnIO son herramientas de acceso a hardware con drivers de kernel firmados digitalmente (LHM por el autor, PawnIO por Authenticode). Algunos antivirus (Defender, otros) pueden marcar los binarios como posibles amenazas por ser herramientas de bajo nivel. Si ocurre: excluir la carpeta del kit (por ejemplo, agregar `tools\lhm\` y `tools\downloads\` a exclusiones de Windows Defender) y verificar la firma del archivo antes de instalarlo. Nunca desactivar la protección global por una herramienta del kit.

## Otros componentes

DiagUSB no incorpora otros componentes de terceros en el producto distribuido. El motor PDF es propio y no se usan dependencias externas de Python. Las herramientas externas de arranque no se distribuyen en este repositorio; su detalle y estado de redistribución se registra en `tools/tools.manifest.json`.

Este archivo queda reservado para avisos de terceros compatibles con `GPL-3.0-or-later` que se incorporen más adelante con aprobación explícita.
