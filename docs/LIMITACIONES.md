# LIMITACIONES

Documento de limitaciones y estado actual del proyecto.

## Estado de implementacion

### Completado
- Chasis del proyecto y documentacion legal (F0)
- Sistema de paquetes con manifiestos JSON (F0)
- 12 paquetes de colectores PowerShell validados en Windows 10 (impresion, redes, wifi, disco, memoria, servicios, seguridad, windows_update, drivers, eventos, contexto, inventario_general)
- Nucleo Python: executor, models, rules, comparator, reporter, registry, knowledge_base (KB embebida de 19 entradas + capa local editable)
- Informes Word (.doc) y PDF (.pdf) en español, con hallazgos, soluciones, acciones del tecnico, mejoras sugeridas y diferencias antes/despues
- Interfaz web local (UI completa: diagnosticos rapidos, revision total, snapshot ANTES/DESPUES + comparacion, editor de KB, registro de analisis)
- Auto-elevacion a Administrador (UAC) con flag `--no-elevate` / `DIAGUSB_NO_ELEVATE`
- Ejecutable portable con PyInstaller (`dist\diagusb\diagusb.exe`), verificado con diagnose y reportes
- Registro persistente de analisis (`config/registro_analisis.json`): auto-guardado, consulta, borrado individual y borrado total
- Suite de pruebas unitarias (50+ pruebas)

### Pendiente de validacion
- Windows 11 (validado hasta ahora en Windows 10)
- Prueba de UAC del exe portable en una segunda cuenta/maquina
- Diferentes contextos de permisos (equipo sin elevacion disponible)

## Restricciones conocidas

### Arquitectura
- PowerShell 5.1 minimo para colectores
- Python 3.12 para la capa de orquestacion (solo biblioteca estandar + reportlab para PDF, embebida en el exe)
- La base de conocimiento y el registro de analisis se guardan en `config/` local (no sincronizan entre equipos)
- El registro de analisis conserva hasta 200 entradas; se descartan automaticamente las mas viejas

### Funcionalidad
- Los colectores de impresion y algunos inventarios requieren permisos elevados para datos completos (sin elevar se ven parciales o 'denied')
- La verificacion de conectividad de red esta limitada (no hace ping real en el colector)
- `Get-WindowsFeature` (roles de servidor) no existe en Windows 10: `windows_features` queda vacio en estaciones
- Los "program groups" (Win32_ProgramGroup) no existen en Windows 10: se omitieron del inventario

### Legal
- Sin binarios de terceros en el repositorio
- El tecnico debe descargar herramientas externas manualmente (SystemRescue, etc.)
