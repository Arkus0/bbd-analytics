# 🔥 BBD Analytics

Dashboard interactivo y sync automático para el programa **Backed by Deadlifts**.

**Hevy → Pandas → Notion + Streamlit**

## Arquitectura

```
Hevy API ──→ Python/Pandas ──→ Notion Database
                │
                └──→ Streamlit Dashboard (Plotly)
                
GitHub Actions: cron diario a las 00:30 (España)
```

## Stack

| Componente | Tecnología |
|---|---|
| API de datos | Hevy REST API v1 |
| Procesamiento | pandas + numpy |
| Visualización | Streamlit + Plotly |
| Base de datos | Notion (via REST API) |
| Automatización | GitHub Actions (cron) |
| Deploy dashboard | Streamlit Cloud (gratis) |

## Quickstart

### 1. Clonar e instalar

```bash
git clone https://github.com/tu-usuario/bbd-analytics.git
cd bbd-analytics
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus API keys
```

**Necesitas:**
- `HEVY_API_KEY`: Ve a Hevy App → Settings → API → Generate key
- `NOTION_TOKEN`: Crea una integración en https://www.notion.so/my-integrations
  - Dale permisos de lectura/escritura a tu workspace
  - Conecta la integración a la página "BBD" en Notion

### 3. Ejecutar sync manual

```bash
# Dry run (ver qué se sincronizaría)
python -m src.sync --dry-run

# Sync real
python -m src.sync
```

### 4. Lanzar dashboard

```bash
streamlit run app.py
```

Se abre en `http://localhost:8501`

## Deploy

### Streamlit Cloud (Dashboard)

1. Sube el repo a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu repo → selecciona `app.py`
4. En Settings → Secrets, pega:
   ```toml
   HEVY_API_KEY = "tu-key"
   NOTION_TOKEN = "tu-token"
   ```
5. Deploy

### GitHub Actions (Sync automático)

1. En tu repo → Settings → Secrets and variables → Actions
2. Añade estos secrets:
   - `HEVY_API_KEY`
   - `NOTION_TOKEN`
   - `NOTION_BBD_LOGBOOK_DB` (opcional, tiene default)
3. El cron corre cada día a las 23:30 UTC (00:30 España)
4. También puedes dispararlo manualmente desde Actions → Run workflow

## Estructura del Proyecto

```
bbd-analytics/
├── app.py                          # Streamlit dashboard
├── src/
│   ├── config.py                   # Constantes, mappings, IDs
│   ├── hevy_client.py              # Hevy API + DataFrame conversion
│   ├── analytics.py                # Motor de cálculos con pandas
│   ├── notion_client.py            # Notion REST API para sync
│   └── sync.py                     # Orquestador de sync
├── .github/workflows/sync.yml     # GitHub Actions cron
├── requirements.txt
├── .env.example
└── .streamlit/secrets.toml.example
```

## Dashboard — Secciones

| Sección | Contenido |
|---|---|
| 📊 Dashboard | Métricas globales, volumen semanal, distribución muscular, objetivos |
| 📈 Progresión | e1RM por ejercicio, PRs históricos, volumen por músculo/semana, recuperación |
| 💪 Sesiones | Detalle de cada entreno con tabla y gráfico de volumen |
| 🏆 PRs | Top 3 showcase + tabla completa de records |
| 🎯 Adherencia | Completación por día BBD, sesiones/semana vs objetivo |

## Analytics Engine (pandas)

Todos los cálculos están en `src/analytics.py`:

- **e1RM**: Fórmula de Epley `peso × (1 + reps/30)`
- **PR detection**: Running max e1RM por ejercicio
- **Volumen**: `peso × reps` por serie, agregado por sesión/semana/músculo
- **Semana**: `(días desde inicio) // 7 + 1`
- **Recuperación**: Delta de volumen semanal con alertas 🟢🟡🔴
- **Adherencia**: Conteo de completación por día BBD

## Notas

- La API de Hevy a veces devuelve `volume_kg: 0` — se calcula manualmente
- Ejercicios de peso corporal (dominadas, GHR) se registran sin peso
- Deduplicación por `Hevy ID` tanto en Notion como en el sync
- El dashboard tiene cache de 5 minutos para no saturar la API
