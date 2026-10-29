# AUDITORÍA TÉCNICA — DiagUSB 2.1

**Fecha:** 2026-10-28
**Alcance:** revisión de solo lectura del repositorio `C:\Users\Torta\Desktop\DiagUSB_2.1`.
**Método:** inspección estática de archivos, conteos, verificación de hashes SHA-256, contraste entre código y documentación.
**Restricción de oro:** no se modificó, creó ni borró ningún archivo del proyecto. El único archivo creado es este `AUDITORIA.md`.

---

## 0. Cómo leer esta auditoría

### 0.1 Estados usados

| Estado | Significado |
|---|---|
| **HECHO Y PROBADO** | Existe, el contenido es código/dato real y fue verificado en esta auditoría con evidencia reproducible (conteo, hash, lectura directa). |
| **HECHO SIN PROBAR** | Existe y el código es real y coherente, pero **no se ejecutó** en esta auditoría (no hay runtime disponible o falta el artefacto). |
| **PARCIAL** | Existe, pero cubre solo una parte de lo que promete, o tiene una inconsistencia verificada. |
| **STUB O VACÍO** | El archivo existe pero no contiene una implementación funcional (placeholders, `null`, listas vacías). |
| **NO EXISTE** | Se buscó y no hay archivo, comando, artefacto ni implementación. |
| **NO VERIFICADO** | No fue posible comprobarlo con la evidencia disponible (entorno roto, dependencia externa, etc.). No equivale a "falso". |

### 0.2 Limitaciones del entorno de auditoría

Estas limitaciones condicionan todo lo que sigue y se declaran para no confundir "no probado" con "roto".

1. **No hay intérprete Python real en la máquina.** `python`, `python3` y `py` fallan o son alias de 0 bytes de Microsoft Store. No existe `.\python\python.exe` en el repositorio. Por tanto **no se ejecutaron tests, CLI, servidor web ni generación de informes**.
2. **El repositorio Git está roto.** `.git` es un archivo puntero a `C:/Users/WinterOS/Desktop/DiagUSB/.git/worktrees/DiagUSB_2.1`, ruta que no existe en esta máquina. Todo comando `git` falla. **No hay historial, diff ni estado de rama verificable.**
3. **La consola PowerShell 5.1 corrompe la visualización de acentos** (página de códigos). Los archivos son UTF-8 válidos: se escaneó el árbol y **0 archivos contienen U+FFFD**. Las salidas crudas del anexo muestran `?` por ese motivo, no porque el archivo esté dañado.
4. **No hay artefactos de build**: no existe `dist\`, no existe `build\diagusb\`, no existe `reports\`, no existe `python\`. El kit portable y el `.exe` **no están armados en este árbol**.

### 0.3 Qué NO prueba esta auditoría

- Que los tests pasen hoy.
- Que la interfaz web funcione en un navegador.
- Que los informes HTML/DOC/PDF se abran correctamente en Word/LibreOffice.
- Que los colectores PowerShell funcionen en Windows 10/11 reales.
- Que el kit portable arranque desde un pendrive.

Todo eso queda como **NO VERIFICADO** y se detalla en cada sección.

---

## 1. Resumen ejecutivo

DiagUSB es un proyecto **sustancial y real**, no un esqueleto: hay 15 paquetes de diagnóstico, 41 colectores PowerShell, 38 reglas, servidor web local con endurecimiento de seguridad, generación de informes HTML/DOC/PDF y una batería de 256 funciones de test. La ingeniería defensiva (integridad SHA-256, token de sesión, validación de `Host`/`Origin`, CSP, redacción de secretos) está presente y bien pensada.

Sin embargo, hay **tres problemas de fondo**:

1. **El proyecto no es reproducible ni ejecutable en este estado.** El `.git` está roto, no hay Python, no hay kit armado, no hay informes generados y las pruebas no se pueden correr. Todo el valor está en código fuente sin verificación de ejecución.
2. **La documentación contradice al código en cifras y capacidades.** README dice 206 pruebas y 15 paquetes; el resumen técnico dice 130 pruebas y 12 paquetes; LIMITACIONES dice 13 paquetes y que la conectividad "no hace ping real" (sí lo hace); el CHANGELOG anuncia un comando `report` que no existe.
3. **El "modo live USB" no existe como implementación.** Solo hay un procedimiento manual documentado y un manifiesto de herramientas **100% pendiente** (`url`, `sha256`, `license` en `null`). No hay ISO, GRUB, Ventoy integrado ni artefacto arrancable.

La cobertura funcional es alta; la **verificación de funcionamiento es baja o nula**. La prioridad no es escribir más features, sino **hacer el proyecto ejecutable, reproducible y honesto consigo mismo**.

---

## 2. Tabla resumen

### 2.1 Repositorio y empaquetado

| Ítem | Estado | Evidencia |
|---|---|---|
| Repositorio Git utilizable | **NO VERIFICADO** | `.git` apunta a `C:/Users/WinterOS/...`; `git status` → `fatal: gitfile does not point to a valid repository` (A.2) |
| Estructura de carpetas | **HECHO Y PROBADO** | 12 carpetas + 13 archivos raíz listados (A.1) |
| 15 paquetes de diagnóstico | **HECHO Y PROBADO** | `packages: 15` (A.3) |
| 41 colectores PowerShell | **HECHO Y PROBADO** | `collectors ps1: 41` (A.3) |
| Manifiesto de integridad | **HECHO Y PROBADO** | 43 entradas, 43/43 hashes coinciden (A.4) |
| Manifiesto versionado en Git | **NO EXISTE** | `.gitignore` ignora `/manifiesto_hashes.json` (A.5) |
| Kit portable armado (`dist\kit`) | **NO EXISTE** | `Test-Path dist` → `False` (A.6) |
| Ejecutable PyInstaller (`build\diagusb`) | **NO EXISTE** | `Test-Path build\diagusb` → `False` (A.6) |
| Python embebido en el árbol | **NO EXISTE** | `Test-Path .\python\python.exe` → `False` (A.2) |
| Informes generados en el árbol | **NO EXISTE** | `Test-Path reports` → `False` (A.7) |
| Intérprete Python de desarrollo | **NO VERIFICADO** | `python --version` sin salida útil; solo alias de 0 bytes (A.2) |

### 2.2 Arquitectura y motor

| Ítem | Estado | Evidencia |
|---|---|---|
| CLI con subcomandos | **HECHO SIN PROBAR** | `diagnose`, `snapshot`, `compare`, `list-packages`, `web` en `__main__.py` |
| Comando `report` anunciado en CHANGELOG | **NO EXISTE** | No hay subparser `report` en `construir_parser()` |
| Elevación UAC a pedido | **HECHO SIN PROBAR** | `--elevar` y `elevar_cli` en `__main__.py`; lanzador no pide UAC al arrancar |
| Verificación de integridad SHA-256 | **PARCIAL** | Código en `integridad.py` + hashes correctos, pero el manifiesto no se versiona y no se ejecutó la comprobación |
| Motor de reglas | **HECHO Y PROBADO** | 38 registros en 27 síntomas (A.8) |
| Síntomas declarados sin regla | **PARCIAL** | 4 de 31 declarados no tienen ninguna regla (A.9) |
| Base de conocimiento | **HECHO Y PROBADO** | 23 entradas en `base_conocimiento.json` (A.10) |
| Redacción de secretos | **PARCIAL** | `redactar()` activo; `_enmascarar_mac` y `_enmascarar_ip` definidos pero **sin uso** |
| Solo lectura sobre el equipo | **PARCIAL** | No hay escrituras de configuración; `get_battery.ps1` crea un XML temporal de `powercfg` y lo borra siempre |

### 2.3 Interfaz web

| Ítem | Estado | Evidencia |
|---|---|---|
| Servidor HTTP local | **HECHO SIN PROBAR** | `BIND_HOST = "127.0.0.1"` (A.11) |
| Token de sesión | **HECHO SIN PROBAR** | `secrets.token_urlsafe(32)`, comparación con `compare_digest` (A.11) |
| Validación `Host`/`Origin` | **HECHO SIN PROBAR** | `_host_valido`, `_origen_valido`, 403 (A.11) |
| Cabeceras de seguridad | **HECHO SIN PROBAR** | CSP, `X-Frame-Options: DENY`, `nosniff`, `no-store`, `no-referrer` (A.11) |
| Límite de cuerpo | **HECHO SIN PROBAR** | `MAX_CUERPO = 10 * 1024 * 1024` |
| 5 vistas de UI | **HECHO SIN PROBAR** | `inicio`, `diagnosticos`, `historial`, `configuracion`, `acerca` en `index.html` |
| Botones de paquete | **PARCIAL** | 14 botones; `bateria` está en `NOMBRES_PAQUETE` pero **no tiene botón** (A.12) |
| Tema oscuro | **HECHO Y PROBADO** | Variables `--sidebar: #0C192C`, `--panel: #0F1E33` en `app.css` |
| Pruebas de navegador/DOM | **NO EXISTE** | No hay Playwright/Selenium ni tests de UI; solo tests de funciones Python |
| Accesibilidad/teclado | **NO VERIFICADO** | Sin pruebas ni auditoría específica |

### 2.4 Informes y salidas

| Ítem | Estado | Evidencia |
|---|---|---|
| Informe HTML autocontenido | **HECHO SIN PROBAR** | CSS inline, SVG embebido, sin `<link>` ni CDN en `reporter.py`/`informe.py` (A.13) |
| Informe DOC (MHTML + PNG) | **HECHO SIN PROBAR** | `informe_a_doc` genera MHTML; no se abrió en Word |
| Informe PDF | **HECHO SIN PROBAR** | Motor PDF propio; no se generó ni validó un PDF real |
| Registro persistente de análisis | **HECHO SIN PROBAR** | `config\registro_analisis.json` existe (12.028 bytes) y la UI lo consume |
| Datos del registro son reales | **PARCIAL** | Contiene análisis marcados `(SIMULADO)`; no son de hardware real (A.14) |
| Exportación a correo/nube | **NO EXISTE** | Sin endpoints ni librerías de envío |

### 2.5 Modo live USB / arranque

| Ítem | Estado | Evidencia |
|---|---|---|
| ISO arrancable propia | **NO EXISTE** | Sin `.iso` en el árbol |
| Integración GRUB/Ventoy | **NO EXISTE** | Sin configuración de arranque |
| Procedimiento manual documentado | **HECHO Y PROBADO** | `docs/USO_ALUMNOS.md` pasos 1–5 |
| Manifiesto de herramientas externas | **STUB O VACÍO** | 6 herramientas, todas `estado: "pendiente"`, `url`/`sha256`/`license` en `null` (A.15) |
| Binarios de terceros incluidos | **NO EXISTE** | Sin Sysinternals, Npcap, memtest, Ventoy en el árbol |
| Arranque validado en hardware | **NO VERIFICADO** | Solo procedimiento manual, sin evidencia de ejecución |

### 2.6 Pruebas

| Ítem | Estado | Evidencia |
|---|---|---|
| Funciones de test en fuentes | **HECHO Y PROBADO** | 256 `def test_` en 15 archivos (A.16) |
| Ejecución actual de la suite | **NO VERIFICADO** | Sin Python; no se ejecutó nada |
| Cifra del README (206) | **PARCIAL / INCORRECTA** | README línea 74; real 256 (A.16) |
| Cifra del resumen técnico (130) | **PARCIAL / INCORRECTA** | `RESUMEN_TECNICO...` línea 267 (A.17) |
| Runner `tests/run_tests.py` | **PARCIAL** | Importa 6 suites (163 tests), no los 15 archivos (A.18) |
| Fuentes de test presentes | **PARCIAL** | Faltan `test_fan_simulado.py` y `test_perifericos_simulado.py`; sus `.pyc` existen (A.19) |
| Caché de pytest | **NO VERIFICADO** | 255 nodeids; `lastfailed` con 2 fallos históricos (A.20) |
| Tests de UI/navegador | **NO EXISTE** | Sin archivos de test de DOM |
| Tests de colectores reales | **NO EXISTE** | No hay mocks de PowerShell en la suite; depende de Windows real |

### 2.7 Licencias y publicación

| Ítem | Estado | Evidencia |
|---|---|---|
| Licencia GPLv3 | **HECHO Y PROBADO** | `LICENSE`, 34.906 bytes, SHA-256 `CDE3A5C4...A88C` (A.21) |
| Cabeceras SPDX | **PARCIAL** | 112/119 archivos de código con SPDX; 7 sin cabecera (A.22) |
| Avisos de terceros | **HECHO Y PROBADO** | `THIRD_PARTY_NOTICES.md` documenta Python embebido y ausencia de otros componentes |
| Reutilización de `machine_scanner`/`Apotrope` | **NO VERIFICADO** | `DECISIONES.md` solo dice que se avisaría si ocurriera; no hay evidencia de código copiado |
| Secretos o claves privadas | **HECHO Y PROBADO** | Sin claves reales; solo placeholders de test y referencias a secretos de CI |
| Firma Authenticode del kit | **NO EXISTE** | El ZIP no se firma; solo se firma el intérprete de Python |
| Publicación/CI | **HECHO SIN PROBAR** | 2 workflows (`build-kit.yml`, `build-firma.yml`); no se ejecutaron |

### 2.8 Seguridad y privacidad

| Ítem | Estado | Evidencia |
|---|---|---|
| Telemetría / envío a servidores | **HECHO Y PROBADO** | Sin URLs externas en `src/`: solo `localhost`, `127.0.0.1:8085` (LHM) y namespaces SVG (A.23) |
| Endpoints de borrado protegidos | **HECHO SIN PROBAR** | Todos pasan por `_validar_solicitud()` y `_token_valido()` |
| Token en query string | **PARCIAL** | El token viaja en `?t=` para abrir el navegador; puede quedar en historial/logs locales |
| CSP estricta | **PARCIAL** | `script-src 'unsafe-inline'` y `style-src 'unsafe-inline'` por JS/CSS inline |
| Lectura de LHM sin autenticación | **NO VERIFICADO** | Depende de un servidor local externo en `127.0.0.1:8085`; no se probó |
| Fugas de datos locales | **PARCIAL** | MAC/IP reales se conservan a propósito en snapshots; las funciones de enmascarado no se usan |

---

## 3. Estado del repositorio

### 3.1 Árbol raíz

```
Mode   Length Name
d-----        .github
d-----        .pytest_cache
d-----        assets
d-----        build
d-----        collectors
d-----        config
d-----        docs
d-----        installer
d-----        scripts
d-----        src
d-----        tests
d-----        tools
-a-h-- 69     .git
-a---- 40     .gitattributes
-a---- 651    .gitignore
-a---- 4237   CHANGELOG.md
-a---- 974    diagusb.cmd
-a---- 34906  LICENSE
-a---- 321    main.py
-a---- 4310   manifiesto_hashes.json
-a---- 11907  README.md
-a---- 1569   SECURITY.md
-a---- 1161   THIRD_PARTY_NOTICES.md
```

**Lectura:** el árbol es coherente con un proyecto Python empaquetado a mano (sin `pyproject.toml` ni `setup.py`). No hay `requirements.txt`, `pytest.ini`, `tox.ini` ni `pyproject.toml`; el proyecto se ejecuta por `PYTHONPATH`/`sys.path` y el build es PowerShell.

### 3.2 Git

```
gitdir: C:/Users/WinterOS/Desktop/DiagUSB/.git/worktrees/DiagUSB_2.1
git : fatal: gitfile does not point to a valid repository: C:/Users/Torta/Desktop/DiagUSB_2.1/.git
```

**Consecuencia:** no se puede saber qué está commiteado, qué está modificado, ni reconstruir el historial. Cualquier afirmación de "versión 2.1 publicada" no es verificable desde este árbol. **NO VERIFICADO.**

### 3.3 `.gitignore` y archivos presentes que ignora

`.gitignore` contiene:

```
/config/
/reports/
/manifiesto_hashes.json
```

Pero en disco existen:

- `manifiesto_hashes.json` (4.310 bytes)
- `config/registro_analisis.json` (12.028 bytes)

**Riesgo:** el manifiesto de integridad que el motor usa para validar colectores **no se versiona**. Un clon limpio no tendría manifiesto, y `integridad.py` entra en "modo desarrollo" (avisa y ejecuta igual). La garantía de integridad depende de un archivo que el propio repositorio decide no publicar. Es una decisión defendible para binarios generados, pero **contradice la promesa de integridad verificable** si no se documenta que el manifiesto se genera en build.

### 3.4 Cachés y artefactos residuales

- `.pytest_cache/` en la raíz, con `nodeids` (18.024 bytes) y `lastfailed` (198 bytes).
- `tests/__pycache__/` con 16 `.pyc` de pytest 9.1.1 / CPython 3.13, incluidos dos módulos **cuyo fuente no existe**.
- No hay `dist/`, `build/diagusb/`, `reports/` ni `python/`.

Los `.pyc` embeben rutas antiguas (`C:\Users\WinterOS\Desktop\DiagUSB_2.1`). Es una fuga menor de información del entorno de desarrollo, no un secreto.

---

## 4. Arquitectura y empaquetado

### 4.1 Punto de entrada y CLI

`src/diagusb/__main__.py` define:

- `diagnose` (requiere `--symptom`; paquete por defecto `impresion`)
- `snapshot`
- `compare`
- `list-packages`
- `web` (`--port`, por defecto 8080)
- flags globales: `--version`, `--verbose`, `--yes`, `--open`, `--log`, `--elevar`, `--no-elevate`

**No existe** un subcomando `report`, aunque `CHANGELOG.md` (sección 0.1.0) afirma:

> "CLI interactiva, comandos `diagnose`, `report`, `web`, `list-packages` y `--version`."

Esto es una **afirmación falsa** verificable. El comando que genera informes es `diagnose`, que escribe HTML, DOC y PDF.

### 4.2 Elevación

- Por defecto **no** se pide UAC.
- `--elevar` relanza con `elevar_cli(comando_relanzable("diagusb"))`.
- El lanzador web del kit no pide UAC; la UI ofrece un botón para solicitarlo.
- Si el usuario rechaza UAC, se continúa en modo estándar y se avisa que faltarán datos.

**Estado:** diseño correcto y coherente con README/LIMITACIONES. **HECHO SIN PROBAR** (no se ejecutó UAC).

### 4.3 Integridad de colectores

`core/integridad.py`:

- Carga `manifiesto_hashes.json` desde `sys._MEIPASS`, junto al `.exe` o desde la raíz del repo.
- Compara SHA-256 antes de ejecutar cada `.ps1`.
- Si no hay manifiesto, avisa una vez y **ejecuta igual** (modo desarrollo).

Verificación realizada: **43/43 hashes coinciden** con los archivos en disco (`collectors/_common.ps1`, `collectors/capacidades.ps1` y los 41 colectores de paquete). Esto es evidencia fuerte de que el manifiesto fue generado con el árbol actual.

**Pero:** el manifiesto está gitignorado; no se probó la ruta congelada (`_MEIPASS`) ni el fallo por hash alterado.

### 4.4 Empaquetado

- `scripts/armar_kit.ps1`: descarga Python embeddable 3.13.15 amd64 desde `python.org`, verifica SHA-256 `d1f04d99...a2cf`, verifica firmas, copia código y lanzadores.
- `scripts/build_exe.cmd` + `build/diagusb.spec`: PyInstaller `onedir`.
- `installer/DiagUSB.iss`: Inno Setup.
- `.github/workflows/build-kit.yml` y `build-firma.yml`: CI de kit y firma.

Ninguno de esos artefactos está presente ni fue ejecutado. **HECHO SIN PROBAR / NO EXISTE (artefacto).**

---

## 5. Módulos de diagnóstico

### 5.1 Inventario

| Paquete | Colectores | Síntomas | Reglas registradas | Estado |
|---|---:|---:|---:|---|
| `impresion` | 6 | 1 | 6 | HECHO SIN PROBAR |
| `redes` | 2 | 2 | 1 | HECHO SIN PROBAR |
| `conectividad` | 3 | 2 | 4 | HECHO SIN PROBAR |
| `wifi` | 2 | 3 | 3 | HECHO SIN PROBAR |
| `disco` | 4 | 3 | 3 | HECHO SIN PROBAR |
| `memoria` | 3 | 3 | 3 | HECHO SIN PROBAR |
| `temperatura` | 2 | 2 | 2 | PARCIAL (experimental, LHM) |
| `bateria` | 1 | 1 | 1 | PARCIAL (experimental, no en UI) |
| `servicios` | 3 | 3 | 2 | HECHO SIN PROBAR |
| `seguridad` | 4 | 3 | 2 | HECHO SIN PROBAR |
| `windows_update` | 3 | 3 | 3 | HECHO SIN PROBAR |
| `drivers` | 1 | 2 | 2 | HECHO SIN PROBAR |
| `eventos` | 2 | 3 | 3 | HECHO SIN PROBAR |
| `contexto` | 1 | 0 | 0 | HECHO SIN PROBAR |
| `inventario_general` | 4 | 0 | 0 | HECHO SIN PROBAR |
| **Total** | **41** | **31** | **38** | — |

### 5.2 Cobertura de reglas

De 31 síntomas declarados en los `manifest.json`, **27 tienen reglas** y **4 no tienen ninguna**:

```
disco_lento
proceso_alto_cpu
seguridad_comprometida
servicio_no_inicia
```

Estos cuatro se evaluarían en una revisión total (`web_server.py` recorre `p.symptoms`) pero no producirían ningún hallazgo propio: solo los hallazgos genéricos de "no evaluado" o "datos limitados". **Es cobertura muerta**: el usuario ve el síntoma en el modelo de datos, pero el motor no lo diagnostica.

Además, ninguno de esos cuatro aparece en `app.js`, `web_server.py` ni `knowledge_base.py`, lo que sugiere que son restos de un diseño anterior o nombres renombrados.

### 5.3 Colectores verificados por lectura

- **Conectividad:** `get_connectivity.ps1` hace ICMP real a `8.8.8.8`, `1.1.1.1` y la puerta de enlace, y `Resolve-DnsName google.com`. **Contradice** `LIMITACIONES.md` línea 50 ("no hace ping real").
- **Batería:** `get_battery.ps1` ejecuta `powercfg /batteryreport`, escribe un XML temporal y **siempre lo borra**. No deja residuos.
- **Temperatura:** `get_cpu_temperature.ps1` consulta `http://127.0.0.1:8085` (LibreHardwareMonitor). No empaqueta LHM.
- **Impresión:** 6 colectores (impresoras, drivers, puertos, trabajos, eventos, spooler).
- **Seguridad:** 4 colectores (antivirus, firewall, Security Center, eventos de seguridad).

Todos los colectores son de solo lectura sobre el sistema. No se encontró ninguno que cambie configuración, servicios, registro o drivers.

### 5.4 Paquetes experimentales

- `temperatura`: el propio CHANGELOG lo marca **EXPERIMENTAL** y "no validado con una lectura real de sensores".
- `bateria`: **EXPERIMENTAL**, "no verificado en hardware real".

Ambos son funcionalidad real, pero **NO VERIFICADA en hardware**. No deben presentarse como capacidades confiables en material de cara al usuario sin esa validación.

---

## 6. Informes y salidas

### 6.1 Formatos

| Formato | Implementación | Verificación |
|---|---|---|
| Consola | `core/reporter.py` (`ConsoleReporter`) | HECHO SIN PROBAR |
| HTML | `core/reporter.py` (`HtmlReporter`) | HECHO SIN PROBAR |
| DOC (MHTML) | `core/informe.py` (`informe_a_doc`) | HECHO SIN PROBAR |
| PDF | `core/informe.py` (`informe_a_pdf`) | HECHO SIN PROBAR |

### 6.2 Autocontención

El HTML usa CSS inline y SVG embebido. No hay `<link rel="stylesheet">`, `<script src="http...">` ni referencias a CDN en `reporter.py`/`informe.py`. El DOC es MHTML con PNG embebidos. **Correcto por diseño**, pero **no se abrió ningún informe real**.

`LIMITACIONES.md` advierte que **LibreOffice 26.2.6 no importa el MHTML**, y que solo se verificó en Word 16.0. Es una limitación real y honesta; conviene repetirla en README y en la UI.

### 6.3 Ausencia de artefactos

No existe `reports/` en el árbol. No hay ningún `.html`, `.doc` o `.pdf` de ejemplo versionado. Por tanto no hay evidencia visual ni de contenido de un informe real. **NO VERIFICADO.**

### 6.4 Registro de análisis

`config/registro_analisis.json` contiene 2 análisis con fecha 2026-10-27:

- `temperatura` / `cpu_caliente`, con `Intel Core i3-4160 (SIMULADO)` y 85 °C.
- Un segundo análisis del mismo día.

Los datos están marcados como simulados. **No son resultados de hardware real.** El archivo está gitignorado, así que no se publicaría, pero su presencia en el árbol puede confundir a quien audite el proyecto.

---

## 7. Interfaz web

### 7.1 Estructura

- `static/index.html`: 5 vistas (`inicio`, `diagnosticos`, `historial`, `configuracion`, `acerca`), panel de resultados, botones de revisión total, KB y registro.
- `static/app.js`: lógica de fetch, manejo de errores, `localStorage` para datos del técnico/cliente, `NOMBRES_PAQUETE`.
- `static/app.css`: tema oscuro (azul marino), variables CSS.

### 7.2 Cobertura de paquetes en la UI

`index.html` tiene **14 botones** con `runDiagnostic(...)`:

```
impresion, redes, conectividad, wifi, disco, memoria, temperatura,
servicios, seguridad, windows_update, drivers, eventos, contexto,
inventario_general
```

`NOMBRES_PAQUETE` en `app.js` tiene **15 entradas**, incluida `bateria: 'Batería'`. Pero **no hay botón para `bateria`**. El paquete solo se ejecuta en "Revisión Total" o por CLI.

**Estado: PARCIAL.** La afirmación del README de "15 paquetes" es cierta a nivel de motor, pero la UI expone 14. Un usuario de la interfaz no puede lanzar batería individualmente.

### 7.3 Seguridad del servidor

Verificado por lectura:

- `BIND_HOST = "127.0.0.1"` — solo loopback.
- Token de sesión `secrets.token_urlsafe(32)`, comparado con `secrets.compare_digest`.
- `Host` válido: `127.0.0.1`, `localhost`, `[::1]`.
- `Origin` válido: mismo conjunto; `Origin: null` se rechaza.
- `MAX_CUERPO = 10 MB`.
- CSP: `default-src 'none'`, `connect-src 'self'`, `frame-ancestors 'none'`, `base-uri 'none'`, `form-action 'none'`.
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
- Todas las rutas `/api/` y los POST validan token; los borrados también.

**Debilidades menores:**

- El token viaja en la query string (`/?t=...`) para abrir el navegador; puede quedar en el historial local o en logs de proxy local.
- CSP permite `unsafe-inline` para JS y CSS porque el HTML inyecta ambos inline. Es una concesión razonable, no ideal.
- No hay TLS; en loopback es aceptable.

**Estado: HECHO SIN PROBAR.** No se levantó el servidor ni se hizo una petición real.

### 7.4 Manejo de errores

`app.js` envuelve los `fetch` y muestra mensajes de error; hay rutas para fallo de red, respuesta no OK y JSON inválido. No se probó en navegador. **NO VERIFICADO.**

---

## 8. Modo live USB / arranque

### 8.1 Lo que existe

`docs/USO_ALUMNOS.md` describe un procedimiento **manual**:

1. Descargar herramientas externas cuando el manifiesto tenga versiones/URLs/hashes.
2. Verificar cada archivo con `scripts\calcular_hash.cmd`.
3. Instalar Ventoy manualmente, fuera del repositorio.
4. Copiar archivos autorizados al pendrive.
5. Incorporar manualmente imágenes de arranque aprobadas, respetando licencias.

### 8.2 Lo que no existe

- Ninguna ISO propia.
- Ninguna configuración GRUB, Ventoy o WinPE.
- Ningún script que partitione/formatee el pendrive.
- Ningún binario de terceros (Sysinternals, Npcap, memtest86+, SystemRescue, Ventoy, WinPE).
- Ninguna prueba de arranque en hardware.

`tools/tools.manifest.json` es un **stub honesto**: declara 6 herramientas, todas con `estado: "pendiente"` y `official_domain`, `url`, `version`, `sha256`, `license` en `null`. Las notas del propio archivo dicen "No inventar versiones, hashes ni URLs" y "Toda entrada con sha256 null ... debe fallar cerrado".

**Conclusión:** DiagUSB **no es hoy una herramienta de arranque**. Es una herramienta portable para ejecutar desde un Windows ya arrancado, más una guía para que un técnico arme manualmente un pendrive multiboot con herramientas de terceros. Cualquier comunicación que lo presente como "live USB" o "diagnóstico pre-boot" es incorrecta.

---

## 9. Pruebas

### 9.1 Volumen real

```
test_capacidades.py              14
test_codificacion.py              1
test_codigo_inalcanzable.py       1
test_identidad.py                37
test_identidad_corta.py          12
test_identidad_sesion.py         15
test_improvements.py             99
test_knowledge.py                 9
test_metricas.py                 20
test_models.py                    5
test_parseo_rpm.py                1
test_registro_reglas.py           2
test_registry.py                  4
test_regla_ventilador.py         10
test_rules.py                    26
------------------------------------
Total                           256
```

### 9.2 Contradicciones documentales

| Fuente | Cifra | Real |
|---|---|---|
| `README.md` línea 74 | "206 pruebas" | 256 |
| `docs/LIMITACIONES.md` línea 19 | "206 pruebas" | 256 |
| `docs/RESUMEN_TECNICO_PARA_REVISION.md` línea 267 | "130 pruebas ... todas pasando" | 256, no ejecutadas |
| `.pytest_cache` | 255 nodeids | 256 defs (una prueba añadida después) |

Ninguna de las tres cifras coincide con el código. Además, "todas pasando" no es verificable: no hay registro de una corrida completa y la caché contiene 2 fallos.

### 9.3 Runner incompleto

`tests/run_tests.py` importa solo:

```
test_models, test_rules, test_registry, test_knowledge,
test_improvements, test_metricas
```

Eso cubre **163 de 256** tests. Quedan fuera, entre otros:

- `test_capacidades.py` (14)
- `test_identidad.py` (37)
- `test_identidad_corta.py` (12)
- `test_identidad_sesion.py` (15)
- `test_regla_ventilador.py` (10)
- `test_registro_reglas.py` (2)
- `test_codificacion.py`, `test_codigo_inalcanzable.py`, `test_parseo_rpm.py` (3)

El README llama a `python tests\run_tests.py` "suite completa". **Es falso**: es una suite parcial. La suite completa requiere `pytest`, que no está declarado en el repo (no hay `requirements.txt` ni `pyproject.toml`).

### 9.4 Fuentes ausentes y caché obsoleta

En `tests/__pycache__` existen:

- `test_fan_simulado.cpython-313-pytest-9.1.1.pyc`
- `test_perifericos_simulado.cpython-313-pytest-9.1.1.pyc`

Pero **no existen** `tests/test_fan_simulado.py` ni `tests/test_perifericos_simulado.py`. La caché `lastfailed` referencia:

```
tests/test_perifericos_simulado.py::test_registro_perifericos_informativo_por_input_muliples
tests/test_registro_reglas.py::test_registro_coincide_con_lista_de_referencia
```

Es decir: hubo una corrida con pytest 9.1.1 el 26–27/10/2026, con al menos 2 fallos, y luego se borraron/renombraron dos archivos de test sin limpiar la caché. **No se puede saber si los fallos se corrigieron.**

### 9.5 Lo que no hay

- Tests de UI/navegador.
- Tests de integración con PowerShell real.
- Tests del kit armado.
- Tests de los informes DOC/PDF abiertos en un lector real.
- Tests de los 4 síntomas sin regla.
- Tests de seguridad del servidor con peticiones maliciosas (aunque hay funciones auxiliares que se testean indirectamente).

---

## 10. Licencias y publicación

### 10.1 Licencia

`LICENSE` es el texto completo de **GPLv3** (34.906 bytes). SHA-256:

```
CDE3A5C4C116F8CDE7BA83EE7A4A885BC591164195B6123BFCBCDC3A52F9A88C
```

`THIRD_PARTY_NOTICES.md` documenta:

- Python 3.13.15 embeddable (PSF), redistribuido sin modificaciones, con `.pth` añadido.
- Ausencia de otros componentes de terceros en el producto distribuido.
- Motor PDF propio, sin dependencias externas de Python.

### 10.2 Cabeceras SPDX

De **119** archivos de código/estilo (`.py`, `.ps1`, `.js`, `.css`, `.html`, `.cmd`, `.yml`), **112 tienen SPDX** y **7 no**:

```
.github/workflows/build-firma.yml
.github/workflows/build-kit.yml
scripts/kit/Iniciar_DiagUSB.cmd
scripts/kit/Iniciar_DiagUSB_consola.cmd
src/diagusb/static/app.css
src/diagusb/static/app.js
src/diagusb/static/index.html
```

No es un problema legal grave (la licencia del repo cubre todo), pero sí una inconsistencia con la práctica declarada en `DECISIONES.md` ("en cada archivo").

### 10.3 Terceros y reutilización

- No hay binarios de terceros en el árbol.
- No hay evidencia de código copiado de `machine_scanner` o `Apotrope`; `DECISIONES.md` solo menciona que, si en el futuro se reutilizara, se conservarían avisos MIT.
- **NO VERIFICADO**: no se puede probar una ausencia de copia solo con este árbol; haría falta comparar con los repositorios originales.

### 10.4 Firma y distribución

- El ZIP del kit **no tiene firma Authenticode** (declarado en `USO_ALUMNOS.md`).
- Solo `python\python.exe` está firmado por PSF.
- El `.exe` de PyInstaller tampoco se firma en el árbol actual.
- Hay un workflow `build-firma.yml` (6.839 bytes) que sugiere un proceso de firma, pero no se ejecutó y no hay artefacto firmado.

**Riesgo:** SmartScreen/Defender pueden bloquear el kit; la documentación lo admite y da instrucciones, pero la experiencia de usuario seguirá siendo deficiente hasta que haya firma.

---

## 11. Seguridad y privacidad

### 11.1 Superficie de red

Búsqueda de URLs en `src/`:

```
web_server.py:1726  http://localhost:{port}/?t={token}
__main__.py:491     http://localhost:8080 (solo texto de ayuda)
capacidades.py:215  http://127.0.0.1:8085 (LHM)
graficos.py / informe.py  http://www.w3.org/2000/svg (namespace XML, no red)
```

**No hay telemetría, ni envío a servidores del autor, ni actualizaciones automáticas.** La única salida de red es la consulta a LibreHardwareMonitor en loopback y las pruebas ICMP/DNS del colector de conectividad. **HECHO Y PROBADO** por inspección estática.

### 11.2 Secretos

No se encontraron claves privadas, tokens reales ni contraseñas. Solo:

- Placeholders en tests.
- Referencias a secretos de CI (`${{ secrets.* }}`) en workflows.
- El token de sesión se genera en memoria por proceso.

### 11.3 Privacidad de datos

- `saneamiento.py` redacta claves/líneas que coinciden con `password`, `token`, `secret`, etc.
- **Pero** `_enmascarar_mac` y `_enmascarar_ip` están definidas y **no se usan**. Los snapshots conservan MAC e IP reales.
- El lanzador advierte que se guardan IP, MAC, SSID y perfiles WiFi (sin contraseñas).
- El registro y los informes quedan en el equipo/pendrive; no se envían.

**Estado: PARCIAL.** La redacción de secretos es real; la minimización de datos de red no se aplica. Es una decisión de diseño (el técnico necesita MAC/IP para diagnosticar), pero debe documentarse explícitamente para no parecer una promesa incumplida.

### 11.4 Escrituras en el sistema

- No se modifica configuración de Windows.
- `get_battery.ps1` crea un XML temporal de `powercfg` y lo borra en `finally`.
- El kit escribe en `config/` y `reports/` (datos propios).
- La UI permite borrar análisis individuales y todos los datos locales, con confirmación.

**Estado: PARCIAL** (solo por el XML temporal), pero en la práctica es de solo lectura.

### 11.5 Riesgos residuales

| Riesgo | Severidad | Comentario |
|---|---|---|
| Token en query string | Baja | Puede quedar en historial local; el token es por proceso y de un solo uso práctico |
| CSP con `unsafe-inline` | Baja | Necesario por el HTML inyectado; un XSS en el propio código sería explotable |
| LHM en `127.0.0.1:8085` sin auth | Media | Cualquier proceso local puede leer los sensores; es una dependencia externa, no de DiagUSB |
| Sin firma del kit | Media | Bloqueos de SmartScreen/EDR; ya documentado |
| Datos simulados en `config/` | Baja | Pueden confundirse con reales si alguien audita el árbol |
| Manifiesto no versionado | Media | La integridad no es reproducible desde un clon |

---

## 12. Lista priorizada de trabajo faltante

### 12.1 Bloqueante (impide considerar el proyecto "entregable/verificado")

| # | Tarea | Esfuerzo | Por qué |
|---|---|---|---|
| B1 | **Reparar el repositorio Git** (recrear `.git` o restaurar el worktree) | S | Sin historial no hay trazabilidad, revisión ni publicación |
| B2 | **Ejecutar la suite completa en un entorno con Python 3.13** y publicar el resultado real | S | Hoy no hay ninguna evidencia de que los 256 tests pasen |
| B3 | **Armar el kit (`dist/kit`) y probar `Iniciar_DiagUSB.cmd` de punta a punta** en Windows 10 | M | El producto distribuible no existe en el árbol |
| B4 | **Resolver las 2 fuentes de test ausentes y el fallo de `test_registro_reglas`** | S | Hay `.pyc` de módulos que ya no existen y un fallo histórico sin explicar |
| B5 | **Unificar las cifras** (206/130/256; 12/13/15 paquetes) en README, LIMITACIONES y RESUMEN | S | La documentación se contradice con el código |
| B6 | **Definir el alcance real del "live USB"**: implementarlo o renombrar la promesa | M/L | Hoy no hay nada arrancable; el manifiesto de herramientas está vacío |

### 12.2 Importante (afecta a la calidad o a la confianza)

| # | Tarea | Esfuerzo | Por qué |
|---|---|---|---|
| I1 | **Exponer `bateria` en la UI** (botón) o justificar por qué no | S | 14 botones para 15 paquetes |
| I2 | **Añadir reglas para `disco_lento`, `proceso_alto_cpu`, `seguridad_comprometida`, `servicio_no_inicia`** o eliminarlos de los manifests | M | 4 síntomas declarados no diagnostican nada |
| I3 | **Completar SPDX** en los 7 archivos que faltan | S | Consistencia con la práctica declarada |
| I4 | **Generar y abrir informes HTML/DOC/PDF reales** en Word y LibreOffice; documentar el resultado | M | No hay evidencia de que los informes funcionen |
| I5 | **Añadir smoke tests de UI/navegador** (Playwright o similar) | M | Toda la UI está sin probar |
| I6 | **Validar `temperatura` (LHM) y `bateria` en hardware real** | M | Ambas están marcadas experimentales y no verificadas |
| I7 | **Declarar `pytest` y un `pytest.ini`/`pyproject.toml`**; hacer que CI corra los 15 archivos | S | Hoy el runner oficial corre 6 suites y no hay dependencias declaradas |
| I8 | **Decidir y documentar el manifiesto de hashes**: versionarlo o generarlo en build con un paso explícito | S | Hoy está gitignorado y la integridad no es reproducible |
| I9 | **Documentar que MAC/IP no se enmascaran** o activar el enmascarado en informes compartibles | S | Hay funciones muertas que sugieren una promesa incumplida |
| I10 | **Limpiar `.pytest_cache` y `__pycache__` del árbol de trabajo** | S | Ruido y fuga de rutas antiguas |

### 12.3 Deseable (mejora continua)

| # | Tarea | Esfuerzo | Por qué |
|---|---|---|---|
| D1 | Firmar Authenticode el `.exe` y el ZIP del kit | M | Reduce bloqueos de SmartScreen/EDR |
| D2 | Sustituir `unsafe-inline` por nonces/hashes en CSP | M | Endurecimiento real del servidor local |
| D3 | Revisión de accesibilidad (teclado, foco, contraste, lectores de pantalla) | M | La UI no tiene auditoría |
| D4 | Internacionalización (español/inglés) | L | Todo está en español hardcodeado |
| D5 | Documentar el contrato JSON de colectores y validarlo con un esquema | M | Hoy el contrato está implícito |
| D6 | Añadir un modo `--dry-run` o `--json` a la CLI para automatización | S | Útil para soporte y CI |
| D7 | Tests de seguridad del servidor (Host/Origin/token/body limit) | M | Hoy solo hay pruebas indirectas |

---

## 13. Riesgos conocidos y afirmaciones falsas

### 13.1 Afirmaciones falsas o inexactas (verificadas)

| Afirmación | Dónde | Realidad |
|---|---|---|
| "206 pruebas" | README línea 74; LIMITACIONES línea 19 | 256 `def test_` |
| "130 pruebas, todas pasando" | RESUMEN línea 267 | 256; no hay corrida completa verificable |
| "suite completa" para `run_tests.py` | README línea 74 | Corre 6 de 15 archivos (163/256) |
| "15 paquetes" en la UI | README línea 9 | Motor: 15; UI: 14 botones (falta batería) |
| "13 paquetes validados" | LIMITACIONES línea 10 | 15 paquetes existen; 13 es una cifra obsoleta |
| "12 paquetes" | RESUMEN líneas 84, 166, 237, 269 | 15 |
| "El colector de conectividad no hace ping real" | LIMITACIONES línea 50 | `get_connectivity.ps1` hace ICMP real a 8.8.8.8, 1.1.1.1, gateway y DNS |
| "Comando `report`" | CHANGELOG 0.1.0 | No existe; los informes los genera `diagnose` |
| "Live USB" / "arranque" | Nombre y narrativa del proyecto | Solo procedimiento manual; sin ISO/GRUB/Ventoy; manifiesto vacío |

### 13.2 Riesgos técnicos

1. **No reproducibilidad:** sin Git, sin Python, sin kit, sin informes. Cualquier entrega depende de que el entorno del autor funcione.
2. **Integridad aparente:** el manifiesto de hashes existe y coincide, pero está gitignorado. Un clon limpio no lo tiene y el motor ejecuta colectores sin verificar.
3. **Cobertura de síntomas incompleta:** 4 síntomas declarados no tienen reglas; en una revisión total producen silencio diagnóstico.
4. **Experimental presentado como disponible:** temperatura y batería son funcionalidad real pero no validadas en hardware.
5. **Informes no verificados:** HTML/DOC/PDF existen por código, pero no se abrió ninguno; LibreOffice ya se sabe que falla con el MHTML.
6. **UI sin pruebas:** el servidor y el JS no tienen tests de navegador; un error de integración podría pasar desapercibido.
7. **Datos simulados en el árbol:** `config/registro_analisis.json` contiene análisis `(SIMULADO)` que podrían confundirse con evidencia real.
8. **Documentación como fuente de verdad rota:** las cifras y capacidades cambian entre documentos; un lector no puede confiar en ninguno sin leer el código.

### 13.3 Lo que sí es sólido

Para no ser injustos: el diseño de seguridad del servidor local es mejor que el de muchos proyectos similares (token + Host + Origin + CSP + body limit + borrado protegido). La separación `core`/`packages`/`static` es clara. Los colectores son de solo lectura y están cubiertos por un manifiesto de integridad. La redacción de secretos y la conciencia de privacidad están presentes. La documentación de limitaciones es inusualmente honesta en algunos puntos (Windows 11, LibreOffice, LHM, batería). El problema no es la ingeniería; es la **falta de ejecución verificada y la deriva documental**.

---

## 14. Anexo A — Salidas crudas de comandos

> Nota: los acentos aparecen como `?` por la página de códigos de PowerShell 5.1. Los archivos son UTF-8 válidos; el escaneo de U+FFFD dio 0 (A.24).

### A.1 Árbol raíz

```
Mode   Length Name
d-----        .github
d-----        .pytest_cache
d-----        assets
d-----        build
d-----        collectors
d-----        config
d-----        docs
d-----        installer
d-----        scripts
d-----        src
d-----        tests
d-----        tools
-a-h-- 69     .git
-a---- 40     .gitattributes
-a---- 651    .gitignore
-a---- 4237   CHANGELOG.md
-a---- 974    diagusb.cmd
-a---- 34906  LICENSE
-a---- 321    main.py
-a---- 4310   manifiesto_hashes.json
-a---- 11907  README.md
-a---- 1569   SECURITY.md
-a---- 1161   THIRD_PARTY_NOTICES.md
```

### A.2 Git y Python

```
gitdir: C:/Users/WinterOS/Desktop/DiagUSB/.git/worktrees/DiagUSB_2.1
git : fatal: gitfile does not point to a valid repository: C:/Users/Torta/Desktop/DiagUSB_2.1/.git

python : no se encontró Python; ejecutar sin argumentos para instalar desde el Microsoft Store...
python3 : no se encontró Python; ejecutar sin argumentos para instalar desde el Microsoft Store...
py : El término 'py' no se reconoce como nombre de un cmdlet...
False
```

### A.3 Conteos de paquetes, colectores, tests y UI

```
packages: 15
collectors ps1: 41
manifest entries: 3          # propiedades raíz: archivos, total, version
test defs: 256
test files: 18
data-paquete: 5              # atributos en index.html; los botones se generan por JS
runDiagnostic: 1             # definición de la función; las llamadas están en onclick
py files: 117
```

Conteo correcto del manifiesto:

```
archivos: 43
total: 43
version: 1
```

### A.4 Verificación de hashes

```
coinciden: 43 / 43
faltantes: 0
distintos: 0
```

### A.5 `.gitignore`

```
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/

# Build (se versionan solo los fuentes; el resto es generado por PyInstaller)
build/*
!build/diagusb.spec
!build/diagusb_gui.spec
!build/entry_console.py
!build/entry_gui.py
!build/README.md
build/version_info.txt
build/version_info_gui.txt
dist/
*.spec.tmp
*.pyz

# Datos locales (no versionar)
/config/
/reports/

# Tools descargadas localmente
/tools/downloads/
/tools/cache/
/tools/staging/
/tools/*.tmp
/tools/*.part

# Reports and hashes
SHA256SUMS
/manifiesto_hashes.json

# Windows
Thumbs.db
desktop.ini
```

### A.6 Ausencia de artefactos

```
Test-Path dist              -> False
Test-Path build\diagusb     -> False
Test-Path .\python\python.exe -> False
```

Contenido de `build/`:

```
build\diagusb.spec
build\diagusb_gui.spec
build\entry_console.py
build\entry_gui.py
build\README.md
```

### A.7 Ausencia de informes

```
reports dir: False
config files:
registro_analisis.json  12028
```

### A.8 Reglas registradas

```
self.register: 38
```

Distribución por síntoma:

```
la_impresora_no_imprime               6
adaptador_red_no_funciona             1
no_hay_internet                       3
red_lenta                             1
dns_no_responde                       1
disco_lleno                           1
disco_salud                           2
cpu_caliente                          1
ventilador_0_rpm_con_cpu_caliente     1
bateria_agotada                       1
servicio_detenido                     1
servicios_fallando                    1
antivirus_apagado                     1
firewall_apagado                      1
memoria_llena                         1
sistema_lento                         2
updates_pendientes                    1
updates_fallidos                      1
windows_update_roto                   1
driver_antiguo                        1
driver_generico                       1
wifi_no_conecta                       1
wifi_lento                            1
wifi_perdida                          1
blue_screen                           1
error_del_sistema                     2
apagado_inesperado                    2
```

### A.9 Síntomas declarados sin regla

```
total sintomas declarados: 31
con reglas: 27
declarados sin regla:
disco_lento
proceso_alto_cpu
seguridad_comprometida
servicio_no_inicia
```

### A.10 Base de conocimiento

```
src\diagusb\core\base_conocimiento.json  30961 bytes
entradas: 23
```

### A.11 Seguridad del servidor web

```
BIND_HOST = "127.0.0.1"
MAX_CUERPO = 10 * 1024 * 1024
CSP = ("default-src 'none'; script-src 'unsafe-inline'; "
       "style-src 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")
_CABECERAS_SEGURIDAD = (
    ("Content-Security-Policy", CSP),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Cache-Control", "no-store"),
    ("Referrer-Policy", "no-referrer"),
)
```

Validación:

```
def _host_valido(self):
    host = (self.headers.get("Host") or "").strip().lower()
    ...
    return nombre in ("127.0.0.1", "localhost", "[::1]")

def _origen_valido(self):
    origen = self.headers.get("Origin")
    if not origen:
        return True
    ...
    return host in ("127.0.0.1", "localhost", "::1")

def _token_valido(self):
    return secrets.compare_digest(self._token_recibido() or "", _token_sesion())
```

### A.12 Botones de la UI

```
index.html:
146  data-paquete="impresion"       onclick="runDiagnostic('impresion')"
152  data-paquete="redes"           onclick="runDiagnostic('redes')"
158  data-paquete="conectividad"    onclick="runDiagnostic('conectividad')"
164  data-paquete="wifi"            onclick="runDiagnostic('wifi')"
170  (sin data-paquete)             onclick="runDiagnostic('disco')"
175  (sin data-paquete)             onclick="runDiagnostic('memoria')"
180  data-paquete="temperatura"     onclick="runDiagnostic('temperatura')"
186  (sin data-paquete)             onclick="runDiagnostic('servicios')"
191  (sin data-paquete)             onclick="runDiagnostic('seguridad')"
196  (sin data-paquete)             onclick="runDiagnostic('windows_update')"
201  (sin data-paquete)             onclick="runDiagnostic('drivers')"
206  (sin data-paquete)             onclick="runDiagnostic('eventos')"
211  (sin data-paquete)             onclick="runDiagnostic('contexto')"
216  (sin data-paquete)             onclick="runDiagnostic('inventario_general')"

app.js NOMBRES_PAQUETE: 15 entradas, incluida `bateria: 'Batería'`
bateria en index.html: 0 ocurrencias
```

### A.13 Autocontención de informes

```
Select-String reporter.py,informe.py -Pattern 'cdn|https://|<link|src="http|<script'
-> sin coincidencias
```

### A.14 Registro de análisis

```
[
 {
  "id": "20261027_171257_e5afa4ac",
  "fecha": "2026-10-27T17:12:57.685490",
  "tipo": "paquete",
  "paquete": "temperatura",
  "paquete_label": "Temperatura CPU",
  "sintoma": "cpu_caliente",
  "puntaje": 94,
  ...
  "message": "Temperatura elevada del CPU (Intel Core i3-4160 (SIMULADO)): 85 °C",
  ...
 ]
]
```

### A.15 Manifiesto de herramientas

```
{
  "schema_version": 1,
  "generated_at": null,
  "notes": [
    "No inventar versiones, hashes ni URLs.",
    "Toda entrada con sha256 null o URL no confirmada debe fallar cerrado en fetch_tools.",
    "Los binarios de terceros no se redistribuyen en este repositorio."
  ],
  "tools": [
    { "name": "Ventoy",       "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" },
    { "name": "SystemRescue", "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" },
    { "name": "WinPE",        "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" },
    { "name": "memtest86+",   "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" },
    { "name": "Sysinternals", "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" },
    { "name": "Npcap",        "url": null, "version": null, "sha256": null, "license": null, "estado": "pendiente" }
  ]
}
```

### A.16 Tests por archivo

```
test_capacidades.py              14
test_codificacion.py              1
test_codigo_inalcanzable.py       1
test_identidad.py                37
test_identidad_corta.py          12
test_identidad_sesion.py         15
test_improvements.py             99
test_knowledge.py                 9
test_metricas.py                 20
test_models.py                    5
test_parseo_rpm.py                1
test_registro_reglas.py           2
test_registry.py                  4
test_regla_ventilador.py         10
test_rules.py                    26
```

### A.17 Cifras en documentación

```
README.md:74   python tests\run_tests.py  # suite completa (206 pruebas, sin dependencias externas)
README.md:9    **15 paquetes de diagnóstico**
LIMITACIONES.md:10  13 paquetes de colectores PowerShell validados...
LIMITACIONES.md:19  Suite de pruebas unitarias (206 pruebas)
LIMITACIONES.md:50  La verificacion de conectividad de red esta limitada (no hace ping real en el colector)
RESUMEN...md:84     12 paquetes...
RESUMEN...md:267    **130 pruebas** actualmente, todas pasando.
```

### A.18 Runner de tests

```
tests/run_tests.py importa:
  test_models, test_rules, test_registry, test_knowledge,
  test_improvements, test_metricas
```

### A.19 Fuentes ausentes con `.pyc`

```
tests/__pycache__:
test_fan_simulado.cpython-313-pytest-9.1.1.pyc          2604   26/10/2026 23:09:41
test_perifericos_simulado.cpython-313-pytest-9.1.1.pyc  4711   27/10/2026 15:47:24

tests/*.py:
(no existen test_fan_simulado.py ni test_perifericos_simulado.py)
```

### A.20 Caché de pytest

```
nodeids: 255
lastfailed:
{
  "tests/test_perifericos_simulado.py::test_registro_perifericos_informativo_por_input_muliples": true,
  "tests/test_registro_reglas.py::test_registro_coincide_con_lista_de_referencia": true
}
```

### A.21 Licencia

```
LICENSE  34906 bytes
SHA-256  CDE3A5C4C116F8CDE7BA83EE7A4A885BC591164195B6123BFCBCDC3A52F9A88C
```

### A.22 Cobertura SPDX

```
total code/style files: 119
sin SPDX: 7
.github\workflows\build-firma.yml
.github\workflows\build-kit.yml
scripts\kit\Iniciar_DiagUSB.cmd
scripts\kit\Iniciar_DiagUSB_consola.cmd
src\diagusb\static\app.css
src\diagusb\static\app.js
src\diagusb\static\index.html
```

### A.23 URLs en `src/`

```
web_server.py:1726   http://localhost:{port}/?t={token}
__main__.py:491      http://localhost:8080
capacidades.py:215   http://127.0.0.1:8085
graficos.py:176,200,221   http://www.w3.org/2000/svg
informe.py:1257      http://www.w3.org/2000/svg
```

### A.24 Validación UTF-8

```
archivos con U+FFFD: 0
```

### A.25 Colectores por paquete

```
bateria              colectores=1 sintomas=1
conectividad         colectores=3 sintomas=2
contexto             colectores=1 sintomas=0
disco                colectores=4 sintomas=3
drivers              colectores=1 sintomas=2
eventos              colectores=2 sintomas=3
impresion            colectores=6 sintomas=1
inventario_general   colectores=4 sintomas=0
memoria              colectores=3 sintomas=3
redes                colectores=2 sintomas=2
seguridad            colectores=4 sintomas=3
servicios            colectores=3 sintomas=3
temperatura          colectores=2 sintomas=2
wifi                 colectores=2 sintomas=3
windows_update       colectores=3 sintomas=3
```

---

## 15. Conclusión

DiagUSB 2.1 es un proyecto **real, ambicioso y con buena ingeniería defensiva**, pero en el estado auditado es **código fuente no verificado**: no se puede ejecutar aquí, no se puede reconstruir su historial, no se puede armar su kit y no se puede comprobar que sus tests pasen. La documentación, además, ha derivado y promete cosas que el código no cumple (206/130 pruebas, 15/13/12 paquetes, comando `report`, "no hace ping", "live USB").

La recomendación es **congelar features nuevas** hasta completar los seis bloqueantes de la sección 12.1: reparar Git, ejecutar la suite, armar y probar el kit, resolver los tests ausentes, unificar cifras y decidir el alcance del arranque. Con eso, el proyecto pasaría de "código prometedor" a "producto verificable". Sin eso, cualquier afirmación de calidad sigue siendo una promesa, no un hecho.
