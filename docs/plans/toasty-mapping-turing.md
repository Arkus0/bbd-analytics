# Plan: Fusionar Calendario + Vista Anual con contexto Forever

## Contexto

Actualmente hay 3 pestañas separadas para consultar el plan 5/3/1:
- **📅 Calendario**: timeline lineal de ~16 semanas con expanders
- **🗓️ Vista Anual**: cuadrícula de 12 meses (dots color-coded por tipo de semana)
- **🗺️ Plan Forever**: bloques del plan anual con progress bars y templates

El problema: para saber "qué me toca en mayo" hay que saltar entre pestañas. El calendario no muestra qué bloque/template/pesos corresponden, y hay dos calendarios redundantes.

## Solución

Fusionar **Calendario** + **Vista Anual** en una sola pestaña `📅 Calendario` que integre el contexto del plan Forever. Mantener **🗺️ Plan Forever** como pestaña separada (vista estructural de bloques).

---

## Cambios

### 1. `src/analytics_531.py` — Nueva función `build_enriched_annual_calendar()`

Enriquecer cada semana del calendario anual con datos del plan Forever:

```python
def build_enriched_annual_calendar(df, year=2026) -> dict:
```

- Llama a `build_annual_calendar(df, year)` internamente
- Para cada semana, calcula `get_plan_position(session_offset)` donde `session_offset = (abs_week - 1) * SESSIONS_PER_WEEK`
- Añade a cada week dict: `block_num`, `block_name`, `phase`, `phase_label`, `supplemental_name`, `main_work_name`, `tm_pct`
- Añade al resultado un dict `months`: para cada mes, el bloque predominante y si hay transición de bloque
- Para semanas upcoming, añade `expected_weights` por lift usando `expected_weights(lift, week_type, tm)`

Funciones existentes `build_annual_calendar` y `training_calendar` no se modifican (otros consumidores las usan).

### 2. `app.py` — Pestaña `📅 Calendario` (reemplaza las dos)

**Eliminar:** pestaña `🗓️ Vista Anual` del radio y su bloque `elif` (líneas 1553-1595).

**Nuevo layout de `📅 Calendario`:**

**A) Tarjeta de posición actual** (reusar estilo gradient de Plan Forever)
- Semana actual, macro, tipo (5s/3s/531/deload)
- Bloque Forever + fase (Leader/Anchor) + template suplementario + main work mode
- TMs actuales de los 4 lifts

**B) Selector de mes** + cuadrícula mensual
- `st.selectbox("Mes", ...)` siempre visible (no solo en mobile)
- Toggle "Ver año completo" para mostrar los 12 meses
- Cada mes tiene un subtítulo: `"Mayo 2026 — Bloque 2: Fuerza-Volumen (BBS) · Leader"`
- La cuadrícula de dots existente se mantiene (colores por tipo de semana)

**C) Detalle semanal del mes seleccionado**
- Por cada semana del mes, un expander con:
  - Header: `W{n} — {week_name} ({sessions_done}/4) · Bloque {N}: {name} · {phase} · {template}`
  - TMs de los 4 lifts
  - Si completed/partial: sesiones reales (fecha, lift, AMRAP)
  - Si upcoming: **pesos esperados** por lift (las 3 series de trabajo + suplementario)
  - Auto-expand semana actual

**D) Progresión de TMs** (en expander colapsable al fondo)
- Tabla de bump points con TMs (una sola copia, no duplicada)

### 3. `app.py` — `render_monthly_calendar()` (líneas 154-265)

Evolucionar para aceptar datos enriquecidos:
- Añadir subtítulo de bloque sobre cada mes
- Aceptar parámetro `focus_month` para renderizar solo un mes o todos
- Mantener colores y dots existentes

### 4. `app.py` — Sidebar radio (línea 886-901)

Eliminar `"🗓️ Vista Anual"` de la lista.

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `src/analytics_531.py` | Nueva `build_enriched_annual_calendar()` (~50 líneas) |
| `app.py` líneas 154-265 | Actualizar `render_monthly_calendar()` para subtítulos de bloque y `focus_month` |
| `app.py` líneas 886-901 | Eliminar `"🗓️ Vista Anual"` del radio |
| `app.py` líneas 1440-1549 | Reescribir pestaña Calendario con nuevo layout |
| `app.py` líneas 1553-1595 | Eliminar bloque Vista Anual |

## Funciones existentes a reutilizar

- `training_calendar()` — `analytics_531.py:1649`
- `build_annual_calendar()` — `analytics_531.py:1762`
- `get_plan_position()` — `config_531.py`
- `get_effective_tm()` — `config_531.py`
- `expected_weights()` — `config_531.py`
- `YEARLY_PLAN`, `SUPPLEMENTAL_TEMPLATES`, `MAIN_WORK_MODES` — `config_531.py`
- `render_monthly_calendar()` — `app.py:154`

## Verificación

1. `python -c "import ast; ast.parse(open('app.py').read()); ast.parse(open('src/analytics_531.py').read())"` — sin errores de sintaxis
2. Abrir dashboard localmente: `streamlit run app.py`
3. Comprobar que el selector de mes muestra el subtítulo del bloque Forever
4. Navegar a un mes futuro (ej. mayo) y verificar que muestra pesos esperados
5. Verificar que la pestaña Plan Forever sigue funcionando independiente
6. Comprobar que no hay pestaña Vista Anual separada
