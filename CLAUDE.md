# CLAUDE.md

BBD Analytics — automated strength training analytics for Juan's "Backed by Deadlifts" program.
Hevy API → Python analytics → Notion (logbook + analytics page) + Streamlit dashboard.

## Architecture

```
Hevy API → GitHub Actions (00:30 Spain) → sync.py → Notion
Hevy API → Streamlit (cache 5min) → Live dashboard
```

- **Repo**: github.com/Arkus0/bbd-analytics (push to main, no PRs)
- **Dashboard**: https://bbd-analytics.streamlit.app
- **Cron**: `.github/workflows/sync.yml` — daily 23:30 UTC

## File Structure

| File | Role | Rules |
|------|------|-------|
| `src/config.py` | Constants, EXERCISE_DB, IDs | Single source of truth for exercises |
| `src/hevy_client.py` | Hevy API fetch (BBD folder 2353809) | Template IDs only, never names |
| `src/analytics.py` | ~1100 lines, 20+ pure functions | DataFrame in → DataFrame/dict out, no side effects |
| `src/notion_analytics.py` | Notion block builder (18 sections) | Max 100 blocks per append |
| `src/sync.py` | Cron entry point | Don't touch unless sync flow changes |
| `app.py` | Streamlit dashboard | Imports analytics, renders |

## Critical Rules

1. **Exercise matching = template_id ONLY**. Hevy returns Spanish names unpredictably. Never match by name.
2. **ALWAYS verify exercises**: Before assuming a template_id matches config, check real Hevy data. Juan changes exercises without warning.
3. **Conventional DL (C6272009)** is the primary deadlift. Historical PMR data (2B4B7310) used ÷0.60 conversion.
4. **`_program_dl_e1rm()`** = raw program metric. **`estimate_dl_1rm()`** = conventional equivalent for standards/gamification.
5. **Commits**: prefix with `feat:`, `fix:`, `refactor:`. Push directly to main.
6. **Testing**: `ast.parse()` + functional test before push. Streamlit deploys in 1-2 min after push.
7. **Notion API**: use page ID for DB queries, NOT collection/data-source ID.
8. **pip**: always `--break-system-packages`.
9. **Streamlit**: don't use `select_slider` with < 2 options.

## Key IDs

| Resource | Value |
|----------|-------|
| Hevy API Key | `HEVY_API_KEY` env var |
| Notion Token | `NOTION_TOKEN` env var |
| Notion Logbook DB | ac92ba6bbc18464f9f2b2a7f82e6c443 |
| Notion Analytics Page | 306cbc499cfe81b08aedce82d40289f6 |
| Notion Hall of Titans | 34d213072fb14686910d35f3fec1062f |
| Hevy BBD Folder | 2353809 |

## Program BBD — 6 Days

| Day | Focus | Key Lift |
|-----|-------|----------|
| 1 | Deadlift + Legs | Conventional Deadlift 6×6 |
| 2 | Press + Shoulders | Strict Press 6×2 |
| 3 | Arms (optional) | Skullcrushers 6×6 |
| 4 | Back + Traps | Shrugs 8×8, Pendlay Row 10×3 |
| 5 | Legs | Zercher Squat 6×4 (replaced Front Squat) |
| 6 | Press + Chest | Klokov Press 10×10 |

## Physical Data

- Weight: 86 kg (hardcoded as BODYWEIGHT in config.py)
- Height: 1.74 m
- Program start: 2026-02-12

## Development Flow

1. Implement logic in `analytics.py` (pure functions)
2. Add visualization in `app.py`
3. Add Notion output in `notion_analytics.py`
4. Test with `ast.parse()` + real/synthetic data
5. Push to main → Streamlit auto-deploys

## Agents & Skills

See `.claude/agents/` for specialized subagents and `.claude/skills/` for preloaded domain knowledge.
Use `/validate-exercises` to verify config vs real Hevy data before any exercise-related changes.
