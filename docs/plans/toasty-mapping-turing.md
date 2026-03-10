# Plan: Calendario basado en fechas reales y ritmo de entrenamiento

## Contexto

El commit anterior fusionó Calendario + Vista Anual en una sola pestaña con contexto Forever. Pero el calendario tiene un problema fundamental: **asume que el programa empezó el 1 de enero y que cada semana de entrenamiento dura exactamente 7 días**.

Realidad:
- El programa empezó el **2026-02-20** (`PROGRAM_START_531` existe en config pero no se usa)
- Juan entrena cuando puede — una "semana" de 4 sesiones puede durar 5, 6, 8+ días
- El calendario muestra enero-febrero con dots de entrenamiento que no existen
- Las proyecciones futuras derivan de la realidad conforme pasan las semanas

## Solución

Anclar cada semana de entrenamiento a fechas reales (pasadas) o proyectadas (futuras), usando el ritmo real observado.

---

## Cambios

### 1. `src/analytics_531.py` — Nueva función `attach_calendar_dates(calendar)`

Función pura que anota cada week dict con `start_date` / `end_date`:

| Tipo de semana | `start_date` | `end_date` |
|---|---|---|
| **Completed** (tiene sesiones) | Fecha de primera sesión | Fecha de última sesión |
| **Current/Partial** | Fecha de primera sesión (o `today()`) | `today()` |
| **Future** | `end_date` anterior + 1 día | `start_date + avg_days_per_week - 1` |

**Cálculo de ritmo:**
```python
if len(completed_weeks) >= 2:
    total_days = (last_week.end_date - first_week.start_date).days
    avg_days_per_week = total_days / (len(completed_weeks) - 1)
else:
    avg_days_per_week = 7.0  # fallback
```

Si no hay sesiones (0 completadas), se ancla semana 1 a `PROGRAM_START_531` con ritmo 7.0.

**Retorna:** `(calendar_con_fechas, pace_info)` donde `pace_info` contiene:
- `avg_days_per_week`: ritmo real (ej. 6.2 días)
- `projected_end_date`: fecha estimada de fin del último bloque
- `is_fallback_pace`: True si usa el 7.0 por defecto

**Ubicación:** Justo después de `training_calendar()` (~línea 1760), antes de `build_annual_calendar()`.

### 2. `src/analytics_531.py` — Actualizar `build_enriched_annual_calendar()`

Cambios en la función existente:
- Después de obtener `raw_cal`, llamar `attach_calendar_dates(raw_cal)`
- Propagar `start_date`/`end_date` del raw_cal a `base["weeks"]` (match por `abs_week`)
- **Reemplazar el mapeo de meses**: usar `w["start_date"].month` en vez de `date(year,1,1) + timedelta(abs_week*7)`
- Añadir `base["pace"] = pace_info` al dict retornado

### 3. `app.py` — Actualizar `render_monthly_calendar()`

**Eliminar:** `program_start = date(year, 1, 1)` y el cálculo `abs_week = (days_since_start // 7) + 1`

**Añadir:** lookup `date → abs_week` construido desde los rangos `start_date`/`end_date` de cada semana:
```python
date_to_week = {}
for w in weeks:
    if "start_date" in w and "end_date" in w:
        d = w["start_date"]
        while d <= w["end_date"]:
            date_to_week[d] = w["abs_week"]
            d += timedelta(days=1)
```

Días no mapeados (enero, gaps entre semanas) → celdas grises sin dots. Esto es correcto: no había entrenamiento.

**Fallback:** Si no hay `start_date` en los datos, caer al cálculo viejo (backward-compatible).

### 4. `app.py` — Ritmo en tarjeta de posición actual

Añadir línea de ritmo al card existente:
```
Ritmo: 6.2 días/semana · Fin estimado: 15 Dic 2026
```

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `src/analytics_531.py` | Nueva `attach_calendar_dates()` (~45 líneas) |
| `src/analytics_531.py` | Actualizar `build_enriched_annual_calendar()` — llamar attach, fix month mapping |
| `app.py` `render_monthly_calendar()` | Reemplazar mapeo date→abs_week con lookup basado en fechas reales |
| `app.py` tarjeta de posición | Añadir línea de ritmo y fecha fin estimada |

## Funciones/constantes a reutilizar

- `PROGRAM_START_531 = "2026-02-20"` — `config_531.py:20` (por fin se usa)
- `training_calendar()` — `analytics_531.py:~1660` (ya retorna sessions con dates reales)
- `build_enriched_annual_calendar()` — `analytics_531.py:~1819` (la actualizamos)
- `render_monthly_calendar()` — `app.py:154` (la actualizamos)

## Edge cases

| Escenario | Manejo |
|---|---|
| 0 sesiones (programa nuevo) | Anclar W1 a `PROGRAM_START_531`, ritmo 7.0 |
| 1 semana completada | Ritmo 7.0 (no se puede calcular intervalo de 1 punto) |
| 2-3 semanas | Ritmo ruidoso pero mejor que hardcoded 7 |
| Vacaciones (gap largo) | Infla el ritmo medio — reflejo real de la cadencia |
| Semana cruza límite de mes | Se asigna al mes de `start_date` |
| Fechas antes de PROGRAM_START | Sin dots, celdas grises (correcto) |

## Verificación

1. `ast.parse()` en `app.py` y `analytics_531.py`
2. Test unitario: `build_enriched_annual_calendar(df_empty)` — verificar que W1 empieza en 2026-02-20
3. Test con datos reales: verificar que las semanas pasadas tienen fechas coherentes con sesiones
4. Verificar en el calendario que enero aparece vacío (sin dots) y febrero empieza el ~20
5. Verificar que la tarjeta muestra ritmo y fecha estimada de fin
6. Navegar a un mes futuro y confirmar que las semanas se proyectan con el ritmo real
