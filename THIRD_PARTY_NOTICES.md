# THIRD_PARTY_NOTICES

## Python embebido

El kit portable incluye Python 3.13.15 (distribución embeddable oficial para Windows amd64) de Python Software Foundation. Los binarios se redistribuyen sin modificaciones bajo la licencia de Python; el kit agrega un archivo `.pth` para ajustar el arranque. El texto de la licencia está en `python\LICENSE.txt` dentro del kit.

- Sitio oficial: https://www.python.org/
- Licencia: https://docs.python.org/3/license.html
- Los binarios PE de `python\` están firmados por Python Software Foundation, salvo los `vcruntime*`, firmados por Microsoft Corporation.
- El ZIP descargado se verifica por SHA-256 antes de usarlo.

## Otros componentes

DiagUSB no incorpora otros componentes de terceros en el producto distribuido. El motor PDF es propio y no se usan dependencias externas de Python. Las herramientas externas de arranque no se distribuyen en este repositorio; su detalle y estado de redistribución se registra en `tools/tools.manifest.json`.

Este archivo queda reservado para avisos de terceros compatibles con `GPL-3.0-or-later` que se incorporen más adelante con aprobación explícita.
