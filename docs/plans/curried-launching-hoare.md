# Plan: Mobile CSS + 5/3/1 Features (Joker Sets, TM Validation, Cycle vs Cycle)

## Context

The Streamlit dashboard has zero mobile-responsive CSS — all layouts, fonts, and chart heights are fixed for desktop ("wide" mode). Juan wants the dashboard usable on his phone. Additionally, the 5/3/1 section needs three new analytics features: joker set detection, training max calibration validation, and cycle-over-cycle comparison. **No migration to GitHub Pages** — Streamlit stays, we add responsive CSS via `st.markdown()`.

---

## Changes Overview

| # | Feature | Files Modified |
|---|---------|----------------|
| 1 | Mobile-responsive CSS | `app.py` |
| 2 | Joker sets tracking | `src/analytics_531.py`, `app.py` |
| 3 | TM test validation | `src/analytics_531.py`, `app.py` |
| 4 | Cycle vs cycle comparison | `src/analytics_531.py`, `app.py` |

---

## 1. Mobile-Responsive CSS (`app.py`)

**Problem**: 17 hard-coded column layouts, 6 custom HTML sections with fixed font sizes, 30+ charts with fixed heights, no media queries.

**Approach**: Inject a `<style>` block with CSS media queries into the existing global CSS at line ~133. Streamlit renders columns as `div[data-testid="stHorizontalBlock"]` children — we can make them stack vertically on small screens.

**Add to global `st.markdown` (line 133):**

```css
/* Mobile responsive */
@media (max-width: 768px) {
    /* Stack columns vertically */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    div[data-testid="stHorizontalBlock"] > div {
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
    /* Smaller fonts for custom HTML */
    .stApp h1 { font-size: 1.4rem !important; }
    .stApp h2 { font-size: 1.2rem !important; }
    /* Metric cards: tighter padding */
    div[data-testid="stMetric"] { padding: 10px !important; }
    /* iframe responsive */
    iframe { height: 200px !important; }
}
```

**Why this works**: Streamlit's column system uses flexbox. By setting `flex-wrap: wrap` and `min-width: 100%` on mobile, all 4-col/6-col/3-col layouts automatically stack vertically. No Python logic changes needed — pure CSS.

**Chart heights**: Already use `use_container_width=True` so width is fine. Fixed heights (250-450px) are acceptable on mobile since they scroll vertically. No change needed.

---

## 2. Joker Sets Tracking

### 2a. Analytics: `src/analytics_531.py`

**Modify `_classify_main_lift_sets()`** (lines 140-232):

Current logic after finding `peak_idx` (AMRAP) classifies all post-peak sets as BBB. Need to intercept and detect joker sets first.

**Detection heuristic** (insert after line ~181, before BBB assignment):
- Post-peak sets where `weight > amrap_weight` AND `reps <= 5` → classify as `"joker"`
- Everything else post-peak continues to BBB logic as-is

**Modify `workouts_to_dataframe_531()`** (lines 234-270):
- Include `"joker"` as a valid `set_type` in the DataFrame rows
- Calculate e1RM for joker sets same as AMRAP (Epley formula already exists)

### 2b. New function: `joker_sets_summary(df)` in `analytics_531.py`

```python
def joker_sets_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate joker set data: date, lift, weight, reps, e1rm."""
    jokers = df[df["set_type"] == "joker"]
    # Group by workout + lift, return table
```

### 2c. Dashboard: `app.py` (531 Dashboard section, after line ~421)

- Add a "Joker Sets" subsection if any joker sets exist
- Display: table with date, lift, weight, reps, e1RM
- Metric: total joker sets count, heaviest joker per lift

---

## 3. TM Test Validation

### 3a. New function: `validate_tm(df)` in `analytics_531.py`

Uses existing `amrap_tracking()` output (which already has `reps_over_min` and `e1rm`).

```python
def validate_tm(df: pd.DataFrame) -> dict:
    """Check if Training Max is calibrated for each lift.

    Returns dict per lift:
      - status: "ok" | "too_light" | "too_heavy"
      - avg_reps_over_min: mean reps above prescribed minimum
      - estimated_true_1rm: avg e1RM from recent AMRAPs
      - current_tm: from config
      - recommended_tm: estimated_true_1rm * 0.90
    """
```

**Wendler's rules**:
- If avg reps_over_min > 5 across last cycle → TM too light
- If avg reps_over_min < 0 → TM too heavy
- Recommended TM = latest AMRAP e1RM * 0.90

Reuses: `amrap_tracking()` (line 346), `TRAINING_MAX` from `config_531.py` (line 25)

### 3b. Dashboard: `app.py` (AMRAP Tracker section, ~line 433)

- Add alert banners per lift using `st.warning()` / `st.success()`
- Show: current TM vs recommended TM, delta, status icon
- If TM is off: show specific recommendation ("Subir OHP de 58 a 62 kg")

---

## 4. Cycle vs Cycle Comparison

### 4a. New function: `cycle_comparison(df)` in `analytics_531.py`

Groups data by `cycle_num` (column already exists via `add_cycle_info()`).

```python
def cycle_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Compare metrics across cycles per lift.

    Returns DataFrame with columns:
      cycle_num, lift, amrap_avg_reps, amrap_avg_e1rm,
      bbb_total_volume, total_sets, sessions_count
    """
```

Reuses: `cycle_num` column from `add_cycle_info()` (line 273), set_type classification, e1RM values.

### 4b. Dashboard: `app.py` (Progresion section, ~line 480)

- Table: cycles as columns, lifts as rows, showing e1RM and volume deltas
- Chart: grouped bar chart — e1RM per lift per cycle (Plotly grouped bars)
- Delta indicators: arrows/colors showing improvement cycle-over-cycle

---

## File Summary

| File | Changes |
|------|---------|
| `app.py:133` | Add mobile CSS media queries to existing `<style>` block |
| `app.py:421` | Add joker sets subsection in 531 Dashboard |
| `app.py:433` | Add TM validation alerts in AMRAP Tracker |
| `app.py:480` | Add cycle comparison in Progresion section |
| `src/analytics_531.py:181` | Modify `_classify_main_lift_sets()` for joker detection |
| `src/analytics_531.py:270` | Modify `workouts_to_dataframe_531()` to include joker type |
| `src/analytics_531.py` (new) | Add `joker_sets_summary()`, `validate_tm()`, `cycle_comparison()` |

---

## Verification

1. `python -c "import ast; ast.parse(open('src/analytics_531.py').read())"` — syntax check
2. `python -c "import ast; ast.parse(open('app.py').read())"` — syntax check
3. `python -c "from src.analytics_531 import joker_sets_summary, validate_tm, cycle_comparison"` — import check
4. Manual test: open dashboard on mobile viewport (Chrome DevTools → toggle device toolbar) to verify CSS stacking
5. Check that existing 531 sections still render correctly (no regressions in set classification)
