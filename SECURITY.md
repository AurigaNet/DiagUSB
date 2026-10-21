# Seguridad

## Versiones soportadas

Solo se da soporte de seguridad a la rama `0.1.x`. Las versiones anteriores no reciben correcciones.

## Reporte de vulnerabilidades

El reporte privado de vulnerabilidades de GitHub está **deshabilitado** en este repositorio (verificado el 2026-10-20). Por eso no hay un canal privado configurado actualmente.

- No publiques detalles explotables, tokens, contraseñas, datos de clientes ni rutas personales en issues públicos.
- El mantenedor debe habilitar **Private vulnerability reporting** en GitHub antes de publicar una versión estable y actualizar este documento con el canal correcto.
- Mientras no exista ese canal, no se debe tratar un issue público como medio para reportar una vulnerabilidad.

## Alcance

- Servidor HTTP local en `127.0.0.1`, con token de sesión y validación de `Host`/`Origin`.
- Colectores PowerShell de solo lectura.
- Redacción de datos sensibles en API, registro, snapshots e informes.
- Integridad SHA-256 de colectores y kit.
- Kit portable sin firma Authenticode; el intérprete Python incluido sí está firmado.

## Buenas prácticas para quien opera el kit

- Ejecutar solo con autorización sobre el equipo analizado.
- Descargar el kit de la fuente oficial y verificar `SHA256SUMS.txt`.
- No desactivar Defender ni agregar exclusiones permanentes.
- Revisar los informes antes de compartirlos: pueden contener nombres de equipo, usuarios, IP, eventos y otra evidencia técnica.
- Borrar los datos locales desde la interfaz cuando termine el trabajo.
