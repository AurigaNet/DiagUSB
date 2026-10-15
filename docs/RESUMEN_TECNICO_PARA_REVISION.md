# DiagUSB — Documento técnico general para revisión externa

Este documento describe, de forma autocontenida, el sistema **DiagUSB**: qué es, cómo está construido, cómo funciona cada componente, qué decisiones se tomaron y cuáles son sus limitaciones. Está pensado para que un revisor (humano o IA) sin acceso al código pueda entenderlo completo y dar una opinión técnica fundamentada.

- **Repositorio**: proyecto local en git (branch `master`). Endurecimiento web de Ronda 2 y cierre de producción de Ronda 3 (commits `6f4ec55`..`bd61fc0`).
- **Licencia**: GPL-3.0-or-later. Copyright 2026 Daniel Ricardo Novoa.
- **Idioma de todo el producto** (UI, informes, docs, comentarios): español.

---

## 1. Qué es y para qué

DiagUSB es un **kit de diagnóstico para soporte de infraestructura TI en Windows**, pensado para correr desde un pendrive en el equipo del cliente. Un técnico de soporte (o un alumno en formación) lo ejecuta, elige un área a diagnosticar (impresión, red, disco, etc.) o hace una revisión total, el sistema recopila datos de solo lectura, los evalúa contra reglas, le muestra los problemas con su explicación y posibles soluciones, y permite generar un **informe Word/PDF** que documenta qué se encontró y qué acciones implementó el técnico.

Casos de uso previstos:
- Soporte presencial a clientes (informe como evidencia del trabajo).
- Aula/formación de técnicos (los informes quedan como material de práctica; hay una guía `docs/USO_ALUMNOS.md`).
- Auditoría rápida de un equipo Windows antes/después de un cambio (snapshot + comparación).

## 2. Restricciones del proyecto (autoimpuestas)

- Solo biblioteca estándar de Python en todo el producto: **sin dependencias externas** (el PDF se genera con un motor mínimo propio en `core/informe.py`).
- Colectores en **PowerShell 5.1** (el que trae Windows 10/11), devolviendo JSON por stdout.
- **Solo lectura**: los colectores no modifican configuración del equipo analizado.
- Sin telemetría y sin conexiones de red salientes del producto.
- Interfaz, informes y documentación en español.
- Distribución portable (PyInstaller `onedir`), sin instalación en el equipo destino.
- Sin binarios de terceros en el repositorio.

## 3. Arquitectura general

```
┌─────────────────────────────────────────────────────────────────┐
│  Ejecutable portable (dist/diagusb/diagusb.exe, PyInstaller)    │
│  o python -m diagusb (desarrollo)                               │
│                                                                 │
│  ┌──────────────┐    ┌───────────────────────────────────────┐  │
│  │  CLI (menú   │    │  Servidor web local (8080, hilos)     │  │
│  │  interactiv. │    │  + UI HTML/JS embebida (una sola      │  │
│  │  + comandos) │───▶│    página, fetch a /api/*)            │  │
│  └──────┬───────┘    └──────────────────┬────────────────────┘  │
│         │                               │                       │
│         ▼                               ▼                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Motor (src/diagusb/core/)                  │    │
│  │  registry (paquetes) · executor · rules · KB ·          │    │
│  │  informe (Word/PDF) · comparator · elevation (UAC)     │    │
│  │  registro persistente de análisis                       │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│                             │ subprocess                        │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Colectores PowerShell (packages/<pkg>/collectors/*.ps1)│    │
│  │  dot-source collectors/_common.ps1 → JSON por stdout    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Datos locales: config/ (KB editable + registro), reports/      │
│  (snapshot ANTES)                                               │
└─────────────────────────────────────────────────────────────────┘
```

Capas:
1. **Colectores PowerShell** (`src/diagusb/packages/<paquete>/collectors/*.ps1`): recolección de solo lectura, una salida JSON por colector.
2. **Motor Python** (`src/diagusb/core/`): ejecuta colectores, normaliza, aplica reglas, arma informes, gestiona KB/registro/snapshots, elevación UAC.
3. **Dos frontends** sobre el mismo motor: CLI de consola e interfaz web local (página única con JS vanilla embebida en `web_server.py`).
4. **Empaquetado**: PyInstaller `onedir` con los colectores y la KB embebidos en `_internal/`.

## 4. Flujo completo de un diagnóstico (desde la UI)

1. El técnico hace clic en un botón (p. ej. "Disco") → JS llama `GET /api/diagnose?package=disco` (o `/api/full-scan` para los 12 paquetes en paralelo, 4 hilos).
2. `run_diagnostic()` descubre el paquete (`manifest.json`), ejecuta cada `*.ps1` ordenado alfabéticamente vía `subprocess.run` (PowerShell `-NoProfile -ExecutionPolicy Bypass`, timeout 30 s, stdout UTF-8).
3. Cada colector devuelve un objeto JSON con: `collector_id`, `query` (status: `ok` / `empty` / `error` / `timeout` / `denied` / `not_available` + duración), `context` (nombre de equipo, si corre elevado, SO, etc.), `data` (payload variable: dict o lista), `errors`, `notes`.
4. El motor cuenta OK/errores/vacíos, convierte los resultados en observaciones y ejecuta **todas las reglas del paquete** (`diagnose_symptoms`), no solo la del síntoma elegido: así un diagnóstico de "disco_lleno" también detecta si hay drivers viejos solo si la regla aplica a ese paquete.
5. Cada hallazgo (Finding: severidad `warning`/`error`/`critical`, mensaje, detalles) se **asocia a la base de conocimiento** (estado esperado, por qué importa, cómo verificar, soluciones paso a paso) y se agrupan los repetidos (p. ej. 17 drivers viejos → 2 mensajes consolidados).
6. La respuesta JSON (incluye `registro_id`) se renderiza en la UI: tarjetas por colector, lista de problemas con checkbox de soluciones, estado por acción (`Pendiente/En proceso/Resuelto/No aplica` + detalle de la acción implementada), mejoras sugeridas, y campos de técnico/cliente/observaciones.
7. **El diagnóstico queda automáticamente guardado** en el registro persistente (ver §5.8).
8. El técnico completa sus acciones y descarga el informe Word o PDF (`POST /api/report`): el servidor arma el informe del lado del servidor con las acciones/markings del formulario.
9. Opcional: "Guardar ANTES" → cambios en el equipo → "Comparar DESPUÉS" (ver §5.7).

## 5. Componentes en detalle

### 5.1 Paquetes y manifiestos (`src/diagusb/packages/`)

12 paquetes, cada uno una carpeta con `manifest.json` (nombre, label, descripción, lista de `symptoms`, version) y `collectors/*.ps1`:

| Paquete | Áreas | # colectores (ejemplos) |
|---|---|---|
| impresion | spooler, impresoras, trabajos, drivers/puertos | 7 |
| redes | adaptadores, IP, DNS, conectividad, drivers de red | 5 |
| wifi | redes visibles, perfiles guardados | 2 |
| disco | particiones, discos lógicos/físicos, rendimiento/S.M.A.R.T. | 4 |
| memoria | estado de memoria, rendimiento, procesos con más consumo | 3 |
| servicios | servicios críticos, fallas recientes, servicios corriendo | 3 |
| seguridad | firewall, antivirus, Centro de Seguridad, eventos recientes | 4 |
| windows_update | estado del servicio, actualizaciones pendientes, historial | 3 |
| drivers | drivers viejos o genéricos (fecha + códigos de error PnP) | 1 |
| eventos | pantallazos azules (BSOD) y errores críticos del sistema | 2 |
| contexto | "ficha" del equipo (modelo, dominio, uptime, virtual, etc.) | 1 |
| inventario_general | hardware, SO, parches instalados, software instalado | 4 |

`core/registry.py` descubre los paquetes en tiempo de ejecución (no hay lista hardcodeada): añadir un paquete = crear la carpeta con su manifiesto.

### 5.2 Colectores PowerShell y `collectors/_common.ps1`

Cada colector:
- Busca `_common.ps1` con un **bucle de búsqueda hacia arriba** desde su propia carpeta (funciona igual en `src/` y dentro del `_internal/` del exe portable, donde la profundidad de carpetas difiere). Si no lo encuentra, falla con error claro.
- `_common.ps1` define el "runtime" del colector: `Set-StrictMode -Version Latest`, `$ErrorActionPreference='Stop'`, salida estándar forzada a UTF-8, helpers (`New-DiagUsbCollectorResult` que envuelve la lógica en try/catch y completa `query.status`/duración/`context`, `Write-DiagUsbJson` para serializar, `Get-DiagUsbPropertyValue` para acceder a propiedades opcionales sin que StrictMode truene, timestamps en UTC).
- El colector solo tiene que llenar `data`; los errores y timeouts los maneja el runtime.
- Convención: si la consulta no rinde datos (p. ej. no hay impresoras), se lanza `New-DiagUsbEmptyResult` → status `empty` (que la UI cuenta aparte y no es un error).

Trampas de Windows 5.1 / StrictMode que ya están resueltas en los colectores:
- **cp1252**: PowerShell 5.1 lee los `.ps1` como cp1252 si no tienen BOM → los scripts con tildes llevan BOM UTF-8; la salida se emite siempre UTF-8.
- `Get-WindowsOptionalFeature` (Windows 10) devuelve `BasicFeatureObject` **sin** `DisplayName`/`Description` → los mapeos usan la helper defensiva.
- `Win32_Product` (instalar/desinstalar) está prohibido (dispara reconfiguraciones MSI): el inventario de software usa las claves de registro Uninstall (4 ramas: HKLM/HKCU × nativo/WOW6432).
- `Win32_ProgramGroup` no existe en Windows 10 → se omitió.
- `Get-WindowsFeature` es de Server → condicionado a `Get-Command`; en estaciones queda vacío sin error.
- `Set-StrictMode` + propiedades opcionales de registro → acceso solo vía `Get-DiagUsbPropertyValue` o `PSObject.Properties[...]`.

### 5.3 Executor Python (`web_server.py`)

- `run_powershell(script_path, timeout)`: `subprocess.run` capturando stdout/stderr como texto UTF-8 con `errors='replace'`; si el stdout no es JSON válido, `_parse_json_output` busca el primer bloque `{...}`/`[...]` (PowerShell puede emitir warnings antes del JSON); timeout → status `timeout`; cualquier excepción → status `error`.
- `_normalize_results`: la salida de un colector puede ser un objeto o una lista; se normaliza a lista plana de resultados.
- El timeout por colector es 30 s (la UI muestra progreso colector a colector).

### 5.4 Motor de reglas (`core/rules.py`)

- Registro de reglas por síntoma (`RuleEngine.register(symptom, fn)`); cada paquete registra funciones que reciben las observaciones y devuelven `Finding`s (severidad, colector, mensaje, detalles).
- Reglas existentes incluyen: spooler detenido, impresora sin trabajos/offline, señal WiFi débil (<40%), BSOD reciente (error) vs. viejo (warning), actualizaciones pendientes críticas, servicios críticos caídos, firewall/antivirus apagados, drivers con más de 5 años o genéricos (con cruce contra `Win32_PnPEntity.ConfigManagerErrorCode` para distinguir "advertencia" de "genérico"), disco lleno, memoria saturada, etc.
- `_agrupar_findings`: consolida hallazgos repetidos (p. ej. N drivers → 1 finding con N instancias) para que el informe no se llene de líneas idénticas.
- Los mensajes están en español con acentos; el pipeline de informes los maneja bien en UTF-8 (HTML/JSON) y en cp1252 (PDF WordAnsi).

### 5.5 Base de conocimiento (`core/knowledge_base.py`)

- **Capa embebida**: `core/base_conocimiento.json`, 19 entradas curadas (WiFi débil, spooler, firewall, DNS, disco, memoria, actualizaciones...). Cada entrada: `id`, `titulo`, `categoria`, `colectores`/`sintomas` asociados, `estado_esperado` ("cómo debe estar"), `por_que_importa`, `soluciones` (paso a paso), `verificacion` ("cómo comprobar que quedó bien").
- **Capa local editable**: `config/base_conocimiento.json` (no versionada); alta/edición/baja desde la UI; si un `id` no existe, se sobrescribe la entrada completa; la capa local pisa a la embebida.
- Asociación automática Finding → entrada KB (por colector o por `knowledge_id` explícito de la regla). Si no hay entrada, las soluciones provienen de un mapa genérico por colector+severidad (`soluciones_para`).
- La UI muestra en cada problema: "Cómo debe estar" / "Por qué importa" / "Cómo verificar" / checklist de soluciones para marcar.

### 5.6 Informes Word/PDF (`core/informe.py`)

- `informe_desde_diagnostico(...)`: a partir del JSON del diagnóstico + acciones del técnico + mejoras + diferencias (si las hay) + datos de técnico/cliente/observaciones, construye un `InformeData` con secciones: 1) encabezado y datos del equipo/cliente/técnico/fecha, 2) resumen ejecutivo (conteos, severidades), 3) hallazgos con severidad y explicación, 4) soluciones aplicadas (lo que el técnico marcó), 5) mejoras sugeridas, 6) inventario/resumen de datos por colector (`_resumen_datos` traduce los payloads a líneas humanas: "Disco físico: Samsung 970 EVO, 500 GB, S.M.A.R.T. OK"), 7) diferencias antes/después (si hay snapshot), 8) observaciones y firma.
- `informe_a_doc`: genera **HTML con los namespaces de Office** (`urn:schemas-microsoft-com:office...`) que Word abre como documento .doc válido (técnica sin dependencias; no es OOXML puro pero funciona en Word/WPS/LibreOffice).
- `informe_a_pdf`: genera el PDF con un **motor mínimo propio sin dependencias** (`_PdfDoc`: texto, reglas y salto de página, con la estructura PDF y su tabla xref escritas a mano), codificación WordAnsi/cp1252 para las tildes.
- El informe se arma **en el servidor** (`POST /api/report` recibe el diagnóstico + acciones del formulario): el cliente solo hace `fetch` y dispara la descarga.

### 5.7 Snapshots y comparador (`core/comparator.py` + UI)

- "Guardar ANTES": la UI manda los `results` del diagnóstico actual → se guardan en `reports/snapshot_antes.json` (formato: `computer_id` + `captured_at` + `observations[]` con `collector_id`/`query`/`data`).
- "Comparar DESPUÉS": la UI manda los `results` actuales → `_snapshot_from_results` arma un Snapshot mínimo y `compare_snapshots` compara **por `collector_id` y campo**: para `data` dict-vs-dict compara clave a clave (solo las que cambiaron); para `data` lista-vs-lista reporta cambio de cantidad de registros; detecta colectores que aparecieron/desaparecieron. Devuelve diferencias con severidad.
- La tabla de diferencias (colector / campo / antes / después) se muestra en la UI y se incluye en el informe.
- CLI: `snapshot` (ejecuta los colectores reales, opcional `--package`) y `compare antes.json despues.json`.

### 5.8 Registro persistente de análisis (nuevo)

- **Auto-guardado**: cada ejecución de `/api/diagnose` o `/api/full-scan` guarda automáticamente una entrada compacta en `config/registro_analisis.json` (máx. 200 entradas, poda de las más viejas; acceso serializado con lock por ser servidor multihilo). La respuesta incluye `registro_id` y la UI lo anuncia.
- **Qué guarda** (y qué no): fecha, tipo (`paquete`/`full-scan`), paquete, síntoma, conteos (colectores OK/error/vacíos/problemas), los hallazgos completos (mensaje, severidad, soluciones KB), recomendaciones y el estado de cada colector. **No** guarda los `data` crudos de los colectores (pesan mucho y el dato se puede recolectar de nuevo; el valor del registro es "qué se analizó, qué se encontró y cuándo").
- **Endpoints**: `GET /api/registro` (lista resumen, más reciente primero), `GET /api/registro?id=` (detalle), `DELETE /api/registro?id=` (borrado individual), `DELETE /api/registro` (vaciar todo).
- **UI**: botón "🗂️ Registro de análisis" (junto a los de diagnóstico, con contador), buscador, expandir detalle (hallazgos con color por severidad + recomendaciones + colectores), botón Eliminar por entrada y "Vaciar registro" (ambos con confirmación).

### 5.9 Servidor web e interfaz (`web_server.py`)

- `http.server` + `ThreadingMixIn` (stdlib), puerto 8080, escuchando **solo en loopback** (`BIND_HOST = "127.0.0.1"`): no es alcanzable desde la red local.
- **Endurecimiento (Ronda 2)**: la clase del handler hereda de `http.server.BaseHTTPRequestHandler` (se eliminó la herencia de `SimpleHTTPRequestHandler`, junto con su listado de directorios y su soporte de `HEAD`); las rutas GET desconocidas devuelven 404; se validan las cabeceras `Host` y `Origin` (ajenas → 403); `POST` exige `Content-Type: application/json` (→ 415) y un `Content-Length` válido con cuerpo ≤ 10 MB (→ 400/413); no se envían cabeceras CORS.
- **Token de sesión**: al arrancar se genera `secrets.token_urlsafe(32)`. La UI se abre en `/?t=<token>`, que responde 302 y fija la cookie `diagusb_token` con `HttpOnly; SameSite=Strict; Path=/`. Todo `/api/*` exige el token (401 sin él) y `/` sin token devuelve 403. La consola imprime la URL con token y el log de cada request lo **redacta** (`t=[oculto]`).
- **Una sola página HTML embebida** en el propio módulo (`HTML_TEMPLATE`, ~1400 líneas: CSS + HTML + JS vanilla). El JS habla con `/api/*` vía `fetch`. No hay framework ni build de frontend (coherente con la restricción de solo stdlib).
- UI: banner de estado/elevación, banner de integridad de colectores y banner de respaldo de rutas, grilla de botones (12 paquetes + Revisión Total + KB + Registro), tarjetas de resultados con JSON expandible por colector, sección de acciones del técnico (con persistencia en `localStorage` para no perder el formulario al recargar), snapshot/comparación, editor y buscador de KB, y el registro de análisis.
- La consola del servidor imprime cada request redactando el token (`[DiagUSB] GET /api/...`).

### 5.10 Auto-elevación a Administrador (`core/elevation.py`)

- Muchos datos (firewall, features de Windows, inventario completo, eventos) requieren Administrator. Al arrancar el CLI (`None`/`diagnose`/`snapshot`) o el servidor web, si no está elevado se relanza a sí mismo con **`ShellExecuteExW("runas")`** (es decir, el diálogo UAC nativo de Windows) usando la misma línea de comandos reconstruida (`comando_relanzable`), y espera a que el hijo eleve el puerto.
- Desactivación: flag global `--no-elevate` o variable de entorno `DIAGUSB_NO_ELEVATE=1`. Si el usuario rechaza el UAC, el programa sigue con permisos limitados y la UI lo avisa (banner).
- El servidor expone `GET /api/elevation` para que la UI sepa si corre elevado.
- Detalle operativo: los procesos elevados no se pueden matar desde un proceso no elevado; para reinicios desde scripts de mantenimiento se usa el propio mecanismo de elevar un script auxiliar.

### 5.11 CLI (`__main__.py`)

- Sin argumentos → menú interactivo (lista paquetes/síntomas, ejecuta diagnóstico, genera informes).
- Subcomandos: `diagnose --package X --symptom Y --output-dir DIR`, `snapshot [-p paquete] -o archivo`, `compare antes.json despues.json`, `list-packages`, `web [--port]`.
- Flags globales: `--yes` (no preguntar), `--open` (abrir navegador), `--no-elevate`.
- El CLI eleva automáticamente para los comandos que ejecutan colectores.

### 5.12 Empaquetado portable (`build/` + `scripts/build_exe.cmd`)

- PyInstaller en modo `onedir` desde `build/diagusb.spec` con entry point `build/entry_console.py`.
- `datas` embebidos: los 12 paquetes (manifiestos + colectores), `collectors/_common.ps1` y la KB embebida → quedan en `dist/diagusb/_internal/...`; en runtime se resuelven con `Path(__file__)` o el bucle de búsqueda hacia arriba de los colectores.
- Resultado verificado en Windows real: `diagusb.exe` (CLI con banner), `diagusb.exe web` (servidor + navegador), diagnósticos con colectores `[OK]` e informes Word/PDF generados desde el exe.

## 6. Formatos de datos principales

**Salida de un colector (JSON por stdout):**
```json
{
  "collector_id": "physical_disks",
  "captured_at_utc": "2026-10-15T12:00:00Z",
  "query": {"status": "ok", "duration_ms": 420, "timeout_seconds": 15},
  "context": {"computer_name": "PC-01", "user": "tecnico", "is_elevated": true,
               "windows": {"version": "10", "build": "19045", "edition": "Pro", "architecture": "64-bit"},
               "regional_settings": {"locale": "es-MX", "timezone": "Central Standard Time"},
               "powershell": {"version": "5.1", "execution_policy": "Bypass"}},
  "data": {"disks": [{"model": "...", "size_gb": 500, "health": "OK"}]},
  "errors": [],
  "notes": []
}
```

**Entrada del registro (`config/registro_analisis.json`, lista; resumen por entrada):**
```json
{
  "id": "20261015_093245_88aa4586",
  "fecha": "2026-10-15T09:32:45",
  "tipo": "paquete",
  "paquete": "disco",
  "paquete_label": "Estado del Disco",
  "sintoma": "disco_lleno",
  "conteos": {"collectors": 4, "ok": 4, "error": 0, "empty": 0, "findings": 1},
  "findings": [{"severity": "warning", "collector_id": "...", "message": "...",
                 "details": {}, "knowledge": {"id": "...", "estado_esperado": "..."},
                 "solutions": ["..."]}],
  "recommendations": ["..."],
  "colectores": [{"id": "physical_disks", "status": "ok", "duration_ms": 380}]
}
```

**Snapshot (`reports/snapshot_antes.json`):** `computer_id` (UUID SMBIOS, serie BIOS, GUID de registro, MACs — marca débil) + `captured_at_utc` + `observations[]` (`collector_id`, `query`, `context` completo, `metadata`, `data`, `errors`, `notes`).

**Entrada de KB:** `id`, `titulo`, `categoria`, `colectores[]`, `sintomas[]`, `estado_esperado`, `por_que_importa`, `soluciones[]`, `verificacion`.

## 7. API HTTP (servidor local)

| Método | Ruta | Función |
|---|---|---|
| GET | `/` | Página de la UI (HTML embebido) |
| GET | `/api/diagnose?package=X` | Diagnóstico de un paquete (auto-guarda en registro; devuelve `registro_id`) |
| GET | `/api/full-scan` | Los 12 paquetes en paralelo (auto-guarda; devuelve `registro_id`) |
| GET | `/api/elevation` | `{"is_elevated": bool}` |
| GET | `/api/knowledge` | KB completa (embebida + local) |
| POST | `/api/knowledge` | Guardar o eliminar entrada de la KB (`accion: guardar\|eliminar`) |
| GET | `/api/registro` | Lista resumen del registro |
| GET | `/api/registro?id=` | Detalle de una entrada |
| DELETE | `/api/registro?id=` | Borrar análisis individual |
| DELETE | `/api/registro` | Vaciar registro |
| POST | `/api/snapshot` | Guardar snapshot ANTES (recibe `results`) |
| POST | `/api/compare` | Comparar actuales contra el snapshot guardado |
| POST | `/api/report?format=doc\|pdf` | Generar informe Word/PDF con acciones del técnico |

> Salvo la apertura inicial `GET /?t=<token>` (que fija la cookie), **todas** las rutas `/api/*` exigen el token de sesión y responden 401 sin él; `GET /` sin token responde 403. `GET /api/elevation` devuelve además `respaldo` (si se están usando rutas en `%LOCALAPPDATA%`) y `ruta_base`.

## 8. Decisiones de diseño y problemas resueltos

1. **JSON por stdout en vez de módulos PowerShell importados**: los colectores son procesos independientes — un crash o timeout de uno no afecta al resto; el mismo script corre idéntico desde el exe o desde el código.
2. **Página única embebida en Python**: sin build de frontend ni node en el equipo del técnico; el JS se extrae del template y se valida con `node --check` en desarrollo.
3. **StrictMode + helpers defensivos**: muchos fallos reales de PowerShell 5.1 son "propiedad que no existe en este Windows"; el runtime los convierte en `empty`/`error` controlados con mensajes útiles, y las excepciones conocidas (DISM sin DisplayName, Win32_Product, Win32_ProgramGroup, Get-WindowsFeature) ya están esquivadas.
4. **cp1252 vs UTF-8**: los `.ps1` se leen como cp1252 sin BOM y la consola de Windows imprime en cp1252 → los scripts acentuados llevan BOM UTF-8 y toda la salida se emite UTF-8; el servidor lee los payloads con fallback cp1252 ante `UnicodeDecodeError`. El PDF usa WordAnsi para las tildes.
5. **Registro compacto sin `data` crudos**: el valor del registro es el historial de análisis (qué, cuándo, qué se encontró), no un respaldo de datos que se pueden recolectar de nuevo; así el archivo no se descontrola.
6. **Informes armados en servidor**: el formulario del técnico (checkbox de soluciones, estados, comentarios) viaja completo al generar el informe; no depende de que el navegador conserve estado.
7. **Elevación opt-out**: UAC automático con fallback elegante a modo limitado (banner + status), porque en aula/sin admin el programa igual tiene que servir.
8. **Descubrimiento de paquetes por carpetas**: añadir un área de diagnóstico = agregar una carpeta con manifiesto + scripts, sin tocar Python.
9. **Servidor solo local y con token de sesión**: el servidor escucha únicamente en `127.0.0.1` y el acceso requiere un token aleatorio generado al arrancar (cookie `HttpOnly; SameSite=Strict`); además se validan `Host`/`Origin`, `Content-Type` y el tamaño del cuerpo, y las rutas desconocidas devuelven 404. Es el endurecimiento de Ronda 2 para un kit que expone HTTP en la máquina del cliente.
10. **Escritura atómica de JSON**: el registro, el snapshot y la KB local se escriben con `tmp` + `fsync` + `os.replace`, y si un JSON queda corrupto se preserva renombrado (`*.corrupto-<fecha>`) en lugar de sobrescribirse en silencio.

## 9. Estrategia de pruebas

- **Sin frameworks**: `python tests\run_tests.py` ejecuta suites escritas a mano (modelos, reglas, registry, KB, informes, elevación, registro) con un runner propio que imprime `[OK]`/`[FALLO]`.
- **73 pruebas** actualmente, todas pasando. Cubren, entre otros: creación de modelos; reglas con fixtures (spooler caído, WiFi débil, BSOD, drivers); descubrimiento de paquetes; KB (guardar/editar/eliminar en archivo temporal, embebida intacta); informes (PDF bytes, HTML, sección de diferencias, `_resumen_datos`, código de verificación); elevación (comandos, rechazo UAC simulado, hijo que sirve puerto); registro persistente (guardado, poda, full-scan, y **endpoints HTTP reales** con servidor en hilo sobre puerto efímero); endurecimiento web de Ronda 2 (bind local, token de sesión, `Host`/`Origin`, `Content-Type`, límite de cuerpo, rutas 404); escritura atómica y preservación de JSON corrupto; identidad del equipo en la comparación (mismo equipo / distinto / forzado); integridad de colectores (hash correcto, archivo alterado, manifiesto ausente); y resolución de rutas portables (congelado vs desarrollo vs respaldo `%LOCALAPPDATA%`).
- Los colectores se validan contra Windows real (no hay mocks de PowerShell en la suite); las pruebas unitarias simulan `run_powershell` solo donde se prueba el conteo de estados.
- Verificación manual periódica: full-scan completo (12 paquetes, 0 errores), `node --check` del JS embebido, smoke test del exe reconstruido.

## 10. Limitaciones conocidas

- Validado en **Windows 10**. **Windows 11 no está validado**: los cmdlets usados existen en ambos, pero no hay prueba formal sobre 11.
- El **comportamiento bajo antivirus/EDR** no está validado: el bloqueo o la limitación de PowerShell, el escaneo de la carpeta del kit y la eventual cuarentena de los scripts `.ps1` no se han probado en un entorno con protección activa. La verificación de integridad por SHA-256 detecta la alteración de colectores, no los falsos positivos de seguridad.
- Los colectores corren con `subprocess` y timeout fijo de 30 s por colector (en equipos muy lentos un colector puede quedar `timeout`).
- El registro usa un archivo JSON local (no hay multi-usuario ni sincronización entre equipos; cada PC tiene su historial).
- El informe .doc es HTML con namespaces Office (no OOXML nativo); se abre bien en Word/WPS/LibreOffice, pero no es un `.docx` de firma digital.
- La comparación de snapshots compara `data` completo por campo (listas grandes se resumen como "registros: N"); no compara dentro de listas elemento a elemento.
- El pendrive de arranque (Ventoy/WinPE) es procedimiento manual documentado; este repo solo entrega la capa Windows portable.
- Sin tests de UI (el JS se valida sintácticamente, no con tests de navegador).

## 11. Estado del repositorio

- Historial (17 commits): base `bf58af8` (F0), `121b227` (F1), `e9f4a0b` (F2: registro, snapshot CLI, auto-elevación, exe); **Ronda 2** (endurecimiento web): `6f4ec55`..`b91dd19` (9 commits); **Ronda 3** (cierre de producción): `1b436a5` (persistencia atómica de JSON), `0aab58f` (identidad del equipo en la comparación), `4805a8d` (integridad SHA-256 de colectores), `b8d0062` (rutas portables junto al exe), `bd61fc0` (código de verificación en el informe).
- Árbol limpio; `config/`, `reports/`, `build/` y `dist/` no versionados (datos locales y salidas). `manifiesto_hashes.json` se genera durante la build y tampoco se versiona.
- Servidor verificado end-to-end en esta máquina: elevado, full-scan 12/12 sin errores (~29 s), registro (guardar/listar/detalle/borrar/vaciar), informes Word/PDF, snapshot+comparación.

## 12. Preguntas donde se busca opinión

1. **Arquitectura**: ¿algún punto frágil del diseño (subprocess por colector, página única embebida, JSON local como persistencia) que recomendarías cambiar antes de escalar el proyecto?
2. **Calidad de los datos**: los colectores son de solo lectura con timeouts y statuses controlados — ¿qué añadirías para hacer el diagnóstico más confiable (p. ej. reintentos, chequeo de salud del colector, sanity checks cruzados)?
3. **UX del técnico**: ¿el flujo diagnóstico → marcar acciones → informe → registro cubre el trabajo real de soporte, o falta algo (p. ej. edición de notas en entradas del registro, exportar/importar el registro, comparar dos registros en el tiempo)?
4. **Seguridad**: servidor local sin autenticación (solo localhost), elevación UAC, PowerShell como subproceso — ¿ves riesgos o malas prácticas para un kit que corre en máquinas de clientes?
5. **Informes**: ¿el formato (HTML→.doc + PDF propio, secciones 1-8) es adecuado para evidencia profesional de soporte?
6. **Escalado**: si en el futuro se quisiera soporte multi-equipo o sincronización del historial, ¿qué caminos sugerirías sin romper la restricción de "sin conexiones salientes"?
7. **Código**: cualquier observación de estilo, modularidad o deuda técnica que salte al revisar las descripciones de la §5.

---

*Documento generado para revisión externa. El sistema vive en el repositorio descrito; los componentes mencionados están implementados y cubiertos por la suite (73 pruebas), con las limitaciones declaradas en la §10 — entre ellas, la ausencia de validación en Windows 11 y bajo antivirus/EDR. Tener cobertura de pruebas no equivale a validación en todos los entornos de producción.*
