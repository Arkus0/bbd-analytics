# BBD Analytics — Roadmap

## Phase 0: Critical Fixes 🔴
> Bugs that WILL bite. Fix before anything else.

### 0.1 — BODYWEIGHT single source of truth
- **Problem**: `BODYWEIGHT = 86.0` hardcoded in 3 places (config.py, config_531.py, app.py). Change one, forget the others → wrong DOTS, standards, gamification.
- **Fix**: Single definition in config.py, imported everywhere.
- **Effort**: 5 min

### 0.2 — get_effective_tm() vs get_session_tm() divergence
- **Problem**: `update_hevy_routines()` uses `get_effective_tm()` (ignores TM_HISTORY recalibrations). Next TM recalibration → Hevy routines get wrong weights.
- **Fix**: Use `get_session_tm()` everywhere. Delete `get_effective_tm()`.
- **Effort**: 15 min

### 0.3 — PR detection by exercise name instead of template_id
- **Problem**: `_detect_prs()` in notion_client.py compares by `row["exercise"]` (Spanish name). Name changes → lost PR history.
- **Fix**: Use `exercise_template_id` for comparison.
- **Effort**: 10 min

---

## Phase 1: Robustness 🟡
> Make the system resilient to failures.

### 1.1 — Error handling in Hevy client
- **Problem**: `_get()` does `raise_for_status()` with no retry/backoff. 429/500/timeout → entire sync crashes.
- **Fix**: Add retry with exponential backoff (3 attempts), rate limiting between pages.
- **Effort**: 20 min

### 1.2 — Sync isolation (BBD ↔ 531 independent)
- **Problem**: If BBD sync crashes, 531 sync never runs (and vice versa).
- **Fix**: Try/except around each sync in `__main__`, report both results independently.
- **Effort**: 10 min

### 1.3 — Notion _patch() rate limiting
- **Problem**: `_post()` has `time.sleep(0.35)`, `_patch()` doesn't.
- **Fix**: Add same delay.
- **Effort**: 2 min

### 1.4 — Dashboard graceful degradation
- **Problem**: If 531 fetch fails, `st.stop()` kills the entire dashboard including BBD.
- **Fix**: Independent try/except per program, show warning for failed program.
- **Effort**: 15 min

---

## Phase 2: Code Quality 🟢
> Reduce duplication, improve maintainability.

### 2.1 — Deduplicate week assignment logic
- **Problem**: Week-by-cycle logic implemented 3 times (build_week_map, add_derived_columns, app.py inline).
- **Fix**: Single `assign_weeks()` function in analytics.py, used everywhere.
- **Effort**: 15 min

### 2.2 — Basic test suite
- **Problem**: Zero tests. Pure functions perfect for testing, especially `_classify_main_lift_sets()` heuristics.
- **Fix**: `tests/test_analytics.py` + `tests/test_531.py` with synthetic data. Add pytest to CI.
- **Effort**: 45 min

### 2.3 — Split app.py into modules
- **Problem**: 1983 lines in one file. Hard to navigate, merge conflicts with self.
- **Fix**: `app.py` as router, `pages/bbd.py`, `pages/bbb.py`, `pages/shared.py`.
- **Effort**: 30 min (risky, defer until test suite exists)

---

## Phase 3: Data & Infrastructure 🔧
> Better data handling, less waste.

### 3.1 — Incremental Hevy fetch
- **Problem**: Every sync/dashboard load fetches ALL workouts. Scales O(n) with history.
- **Fix**: Fetch only workouts since last known date. Cache full history locally or use `since` param if API supports.
- **Effort**: 20 min

### 3.2 — Dynamic bodyweight from Notion
- **Problem**: BW is static 86.0. Bulk/cut → all ratios wrong.
- **Fix**: Read latest entry from NOTION_SEGUIMIENTO_DB, fallback to config constant.
- **Effort**: 20 min

### 3.3 — Data backup on sync
- **Problem**: No recovery if Notion DB corrupts or Hevy changes API.
- **Fix**: Export DataFrames as CSV artifacts in GitHub Actions after each sync.
- **Effort**: 15 min

### 3.4 — Sync failure notifications
- **Problem**: Cron fails silently. Juan doesn't know until he checks Actions.
- **Fix**: GitHub Actions step that posts to Notion or sends Telegram on failure.
- **Effort**: 20 min

---

## Phase 4: Feature Parity (531 ↔ BBD) 🚀
> Port proven BBD features to 531.

### 4.1 — 531 Plateau Detection
- **Problem**: BBD has plateau detection (3+ weeks no e1RM improvement). 531 doesn't.
- **Fix**: Adapt `plateau_detection()` for 531 AMRAP e1RMs per lift.
- **Effort**: 25 min

### 4.2 — 531 ACWR (Acute:Chronic Workload Ratio)
- **Problem**: BBD tracks injury risk via volume ratios. 531 doesn't.
- **Fix**: Implement ACWR on 531 weekly volume data.
- **Effort**: 25 min

### 4.3 — 531 Fatigue & Density Analysis
- **Problem**: BBD has intra-session fatigue and session density trends. 531 doesn't.
- **Fix**: Port fatigue/density functions to 531 context.
- **Effort**: 30 min

### 4.4 — 531 Gamification
- **Problem**: BBD has 30 achievements, 10 levels, XP. 531 has nothing.
- **Fix**: Design 531-specific achievements (AMRAP milestones, TM milestones, cycle completions, joker set badges).
- **Effort**: 45 min

---

## Phase 5: New Features ✨
> Things neither program has yet.

### 5.1 — Cross-program unified view
- Unified dashboard page showing both programs side by side: total volume, frequency, strength progress.
- Single timeline combining BBD + 531 sessions.

### 5.2 — Estimated 1RM trend predictions
- Fit regression on e1RM history per lift → project when you'll hit next milestone.
- "At current rate, you'll deadlift 200kg by June 2026."

### 5.3 — Auto-detect exercise substitutions
- When Juan swaps an exercise in Hevy (e.g., Front Squat → Zercher), detect the unknown template_id automatically and suggest adding it to EXERCISE_DB.

### 5.4 — Workout quality score
- Composite score per session: adherence to plan, volume vs target, AMRAP performance, rest times.
- Track quality over time to spot motivation dips.

### 5.5 — Recovery readiness estimate
- Use session density + volume trends + rest days to suggest "ready to train" vs "consider rest".
- Integrate with ACWR data.

### 5.6 — Shareable workout cards
- Generate PNG/SVG summary cards for individual sessions (for sharing on social).

---

## Execution Order

| # | Item | Est. | Status |
|---|------|------|--------|
| 1 | 0.1 BODYWEIGHT single source | 5m | ⬜ |
| 2 | 0.2 get_effective_tm fix | 15m | ⬜ |
| 3 | 0.3 PR detection by template_id | 10m | ⬜ |
| 4 | 1.1 Hevy client retry + rate limit | 20m | ⬜ |
| 5 | 1.2 Sync isolation | 10m | ⬜ |
| 6 | 1.3 Notion _patch rate limit | 2m | ⬜ |
| 7 | 1.4 Dashboard graceful degradation | 15m | ⬜ |
| 8 | 2.1 Dedup week assignment | 15m | ⬜ |
| 9 | 2.2 Test suite | 45m | ⬜ |
| 10 | 3.1 Incremental Hevy fetch | 20m | ⬜ |
| 11 | 3.2 Dynamic bodyweight | 20m | ⬜ |
| 12 | 3.3 Data backup artifacts | 15m | ⬜ |
| 13 | 3.4 Sync failure notifications | 20m | ⬜ |
| 14 | 4.1 531 Plateau Detection | 25m | ⬜ |
| 15 | 4.2 531 ACWR | 25m | ⬜ |
| 16 | 4.3 531 Fatigue & Density | 30m | ⬜ |
| 17 | 4.4 531 Gamification | 45m | ⬜ |
| 18 | 2.3 Split app.py | 30m | ⬜ |
| 19 | 5.x New features | TBD | ⬜ |
