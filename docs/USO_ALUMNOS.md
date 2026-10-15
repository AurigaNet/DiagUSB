# USO_ALUMNOS

## Estado

DiagUSB incluye una version portable (`dist\diagusb\diagusb.exe`) que corre directamente desde el pendrive en Windows 10/11 sin instalar nada. Esta guia cubre ambas partes: el uso del kit portable y el procedimiento manual para armar el pendrive de arranque con herramientas externas (que sigue siendo manual: en este repositorio no se incluyen binarios de terceros ni se automatiza el particionado o formateo del dispositivo).

## Uso del kit portable (Windows)

1. Copiar la carpeta `dist\diagusb\` al pendrive.
2. En el equipo a diagnosticar, ejecutar `diagusb.exe` y aceptar el diálogo de Administrador (necesario para datos completos).
3. Elegir `web` para la interfaz interactiva en `http://localhost:8080`, o seguir el menú de consola.
4. En la interfaz: botón de diagnóstico o "Revisión Total" → revisar hallazgos → marcar acciones del técnico → "Guardar ANTES" / "Comparar DESPUÉS" → descargar informe Word/PDF.
5. El historial de análisis queda en "Registro de análisis" (persistente en `config/registro_analisis.json`); allí puede consultar, eliminar individualmente o vaciar el registro.
6. Para diagnósticos sin elevación: `diagusb.exe --no-elevate web` (algunos datos aparecerán parciales).

## Procedimiento manual para armar el pendrive de arranque

1. Descargar manualmente las herramientas externas desde sus sitios oficiales, una vez que `tools/tools.manifest.json` tenga versiones, URLs y hashes confirmados.
2. Verificar cada archivo descargado con `scripts\calcular_hash.cmd` o `scripts\calcular_hash.ps1`.
3. Instalar Ventoy manualmente con su herramienta oficial, fuera de este repositorio.
4. Copiar al pendrive los archivos autorizados y preparados por el técnico.
5. Incorporar manualmente las imágenes de arranque aprobadas, respetando sus licencias.
6. Probar el arranque en un entorno controlado antes de entregar el kit.

## Salvaguardas

- No automatizar formateo, particionado ni borrado de discos o pendrives.
- Cualquier copia asistida desde este repositorio debe empezar en modo simulación.
- La ejecución real debe exigir letra de unidad explícita, negarse sobre la unidad del sistema y pedir confirmación interactiva.
