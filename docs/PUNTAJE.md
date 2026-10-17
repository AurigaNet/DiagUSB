# Puntaje orientativo y métricas (DiagUSB)

DiagUSB calcula un **puntaje orientativo** de 0 a 100 a partir de los
hallazgos reales del análisis ejecutado. No reemplaza al diagnóstico: es un
resumen visual para los informes y la interfaz.

## Fórmula (versión 1)

El puntaje comienza en 100 y resta un peso por cada hallazgo según su
severidad:

| Severidad | Resta |
|-----------|-------|
| Crítico (`critical`) | 15 |
| Error (`error`) | 8 |
| Advertencia (`warning`) | 3 |
| OK (`ok`) | 0 |

- El piso es **0** (`max(0, 100 - resta)`); nunca es negativo.
- Los hallazgos con `details.no_evaluado` (por ejemplo, colectores no
  evaluados o datos limitados) **no restan**.
- Si no se ejecutó ningún módulo, el puntaje es **`null`** y la etiqueta es
  **"Sin datos"** (nunca se inventa un valor de éxito).

Ejemplos: 1 crítico + 2 errores = 100 − (15 + 8 + 8) = **69** ("Atención");
10 críticos = **0**.

## Etiquetas

| Condición | Etiqueta |
|-----------|----------|
| Sin módulos ejecutados | Sin datos |
| Cobertura < 60 % | Datos parciales |
| Puntaje ≥ 85 | Bueno |
| Puntaje ≥ 60 | Atención |
| Puntaje < 60 | Crítico |

## Cobertura

La **cobertura** es la proporción de colectores en estado `ok` sobre los
colectores **ejecutados**:

```
cobertura = colectores_ok / colectores_ejecutados * 100
```

Los colectores `empty`, `error`, `timeout`, `denied` y `not_available` no
cuentan como `ok`. Una cobertura baja marca el resultado como
**"Datos parciales"** aunque el puntaje sea alto: con poca información no se
puede afirmar que el equipo esté bien.

## Alcance

El título del panel siempre acompaña al medidor:

- Revisión total → **"Puntaje de salud del equipo"**.
- Análisis de un paquete → **"Puntaje del paquete \<nombre\>"**, con la
  leyenda de que **no refleja el estado general del equipo**.

Se aplica igual en la interfaz y en los tres informes (pantalla, PDF y Word).

## Tendencia

La tendencia usa **solo** entradas del registro del **mismo `tipo` y
`paquete`** que el último análisis; nunca mezcla un paquete con una revisión
total. Se muestran hasta **10** puntos en orden cronológico. Si hay menos de
dos puntos, se indica "Aún no hay historial suficiente".

## Solo lectura

Todos los valores se derivan de lo que ya producen los colectores y las
reglas. El cálculo vive en `src/diagusb/core/metricas.py`, no hace
entradas/salidas y no altera el diagnóstico.
