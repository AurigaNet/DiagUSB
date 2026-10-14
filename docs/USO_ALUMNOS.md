# USO_ALUMNOS

## Estado

Esta guía describe el procedimiento manual previsto para armar el pendrive de arranque del kit. En F0 no se incluyen binarios de terceros ni se automatiza el particionado o formateo del dispositivo.

## Procedimiento manual previsto

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