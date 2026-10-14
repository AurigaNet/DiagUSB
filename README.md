# DiagUSB

Copyright (C) 2026 Daniel Ricardo Novoa (AurigaNet)

MVP en construcción, no probado en Windows real.

DiagUSB es un kit de diagnóstico para soporte de infraestructura TI pensado para ejecutarse desde un pendrive. El foco inicial del MVP es el diagnóstico guiado del síntoma `la impresora no imprime` en Windows 10 y 11, con recolección en solo lectura y reportes en español.

La capa A será una herramienta de consola en Python 3.12, con colectores en PowerShell 5.1 que devuelven JSON y empaquetado `onedir` con PyInstaller. La capa B será un pendrive de arranque armado manualmente con Ventoy, SystemRescue, WinPE y memtest86+, sin redistribuir binarios de terceros en este repositorio.

Este programa se distribuye con la esperanza de que sea útil, pero SIN NINGUNA GARANTÍA; ni siquiera la garantía implícita de COMERCIABILIDAD o IDONEIDAD PARA UN PROPÓSITO PARTICULAR. Véase `LICENSE` para más detalles.

## Estado del repositorio

- F0 completada: chasis, documentación legal, manifiesto de herramientas y scripts base.
- F1 en curso: colectores PowerShell de impresión y plantilla de permisos.
- Sigue sin validación formal sobre Windows real controlado.
- Los reportes, reglas y el comparador todavía no están implementados.

## Alcance inicial

- Inventario y contexto de captura desde Windows.
- Guardado de referencias por equipo.
- Comparación determinista entre capturas.
- Diagnóstico guiado del módulo `la impresora no imprime`.
- Procedimiento manual para armar el pendrive de arranque.

## Restricciones del proyecto

- Interfaz, informes y documentación en español (`es-AR`).
- Código propio bajo `GPL-3.0-or-later`.
- Solo biblioteca estándar de Python en la capa A.
- Sin telemetría, sin conexiones salientes del producto final y sin modificación de la configuración del equipo analizado.
- No se incluyen binarios o ISOs de terceros; ver `tools/tools.manifest.json`.

## Estructura inicial

- `docs/`: decisiones, legal, limitaciones, matriz de permisos y guía para alumnos.
- `src/diagusb/`: paquete principal del proyecto.
- `collectors/`: scripts de recolección PowerShell.
- `tests/`: fixtures y pruebas unitarias.
- `tools/`: manifiesto de herramientas externas.
- `scripts/`: utilidades locales para el técnico.
- `build/`: documentación de empaquetado.