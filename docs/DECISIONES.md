# DECISIONES

## 2026-10-13 - Scripts PowerShell con lanzadores `.cmd`

- Se usan scripts `.ps1` acompañados por un lanzador `.cmd` mínimo por cada script operativo.
- Motivo: en Windows cliente, abrir un `.ps1` con doble clic no ejecuta el script y la política de ejecución por defecto puede bloquearlo.
- El lanzador usa `powershell -NoProfile -ExecutionPolicy Bypass -File ...` solo en la PC del técnico para ejecutar utilidades locales del repositorio.
- Este `Bypass` no se usa para correr nada en el equipo analizado; la herramienta final del kit seguirá sus propios mecanismos de ejecución y solo operará en lectura.

## 2026-10-13 - Codificación de scripts PowerShell

- Los archivos `.ps1` se guardan en UTF-8 con BOM para compatibilidad con PowerShell 5.1 y para evitar problemas con acentos.
- Se fuerza fin de línea CRLF para `*.ps1` y `*.cmd` mediante `.gitattributes`.

## 2026-10-13 - Licencia del código propio

- El código propio del proyecto pasa a `GPL-3.0-or-later`.
- Se incorpora el aviso de copyright `Copyright (C) 2026 Daniel Ricardo Novoa` en la documentación principal y en cada archivo de código propio.
- El proyecto no aceptará ni incorporará código de terceros con licencia incompatible con GPLv3.
- Si en el futuro se incorpora, con aprobación explícita, código MIT de `machine_scanner` o `Apotrope`, habrá que conservar sus avisos en `THIRD_PARTY_NOTICES.md`.
## 2026-10-13 - Colectores de impresión F1

- Se implementan colectores separados para impresoras, puertos TCP/IP, drivers, servicio Spooler, cola de trabajos y eventos de `PrintService`.
- Todos devuelven JSON con `schema_version`, `collector_id`, `query.status`, `context`, `data` y `errors`.
- Para eventos se captura XML estructurado (`EventData`) y metadatos numéricos; no se parsea el mensaje localizado del evento.
- La clasificación inicial de estado se resuelve en el propio colector: `ok` si hay datos, `empty` si la consulta devuelve cero elementos y `not_available`/`denied`/`timeout`/`error` si la ejecución lo reporta de forma explícita.
