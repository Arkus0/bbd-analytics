"""
BBD Analytics — Pandas Analytics Engine v3 (template_id based)

All exercise matching uses exercise_template_id, never localized names.
Exercise names (df["exercise"]) are only used for display.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.config import (
    PROGRAM_START,
    DAY_CONFIG,
    MUSCLE_GROUP_COLORS,
    WEEKLY_TARGETS,
    EXERCISE_DB,
    DEADLIFT_TEMPLATE_ID,
    SHRUG_TEMPLATE_ID,
    PULLUP_TEMPLATE_ID,
    get_muscle_group,
    get_key_lift_ids,
    get_strength_standards,
    get_bbd_ratios,
)


def calc_week(date: pd.Timestamp) -> int:
    """Fallback: calendar-based week. Prefer build_week_map for cycle-aware calc."""
    delta = (date - pd.Timestamp(PROGRAM_START)).days
    return max(1, (delta // 7) + 1)


def build_week_map(df: pd.DataFrame) -> dict:
    """
    Assign week numbers based on BBD day cycle, not calendar.

    A new week starts whenever day_num resets lower than the previous session
    (e.g., after Day 6 comes Day 1, or after any rest/skip the cycle restarts).
    The first partial week (e.g., starting on Day 4) is Week 1.

    Returns a dict mapping date -> week_number.
    """
    if df.empty or "day_num" not in df.columns:
        return {}

    # One row per unique training date with the day_num of that session
    sessions = (
        df.dropna(subset=["day_num"])
        .drop_duplicates("date")[["date", "day_num"]]
        .sort_values("date")
        .reset_index(drop=True)
    )

    week = 1
    week_map = {}
    prev_day = None

    for _, row in sessions.iterrows():
        day = row["day_num"]
        date = row["date"]
        # Cycle reset: current day is less than or equal to the previous day
        # (only bump when it's not the very first session)
        if prev_day is not None and day <= prev_day:
            week += 1
        week_map[date] = week
        prev_day = day

    return week_map


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    week_map = build_week_map(df)
    if week_map:
        df["week"] = df["date"].map(week_map).fillna(1).astype(int)
    else:
        df["week"] = df["date"].apply(calc_week)
    # ── KEY CHANGE: muscle group from template_id, not exercise name ──
    df["muscle_group"] = df["exercise_template_id"].map(get_muscle_group).fillna("Otro")
    df["day_color"] = df["day_num"].map(
        lambda x: DAY_CONFIG.get(x, {}).get("color", "#666")
    )
    return df


# ═══════════════════════════════════════════════════════════════════════
# 1. CORE — Global Summary, Weekly Breakdown, Sessions
# ═══════════════════════════════════════════════════════════════════════

def global_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    sessions = df.groupby("hevy_id").first()
    total_vol = int(df["volume_kg"].sum())
    n_sessions = len(sessions)
    return {
        "total_sessions": n_sessions,
        "total_sets": int(df["n_sets"].sum()),
        "total_volume": total_vol,
        "total_reps": int(df["total_reps"].sum()),
        "avg_duration": round(sessions["duration_min"].mean(), 1),
        "avg_sets_session": round(df.groupby("hevy_id")["n_sets"].sum().mean(), 1),
        "avg_volume_session": round(total_vol / n_sessions) if n_sessions else 0,
        "total_exercises_unique": df["exercise"].nunique(),
        "date_first": df["date"].min(),
        "date_last": df["date"].max(),
        "current_week": int(df["week"].max()) if "week" in df.columns else 1,
        "weeks_active": df["week"].nunique(),
        "days_completed": sorted(df["day_num"].dropna().unique().tolist()),
    }


def weekly_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    weekly = (
        df.groupby("week")
        .agg(
            sessions=("hevy_id", "nunique"),
            total_sets=("n_sets", "sum"),
            total_volume=("volume_kg", "sum"),
            total_reps=("total_reps", "sum"),
            exercises_unique=("exercise", "nunique"),
            days=("day_name", lambda x: sorted(x.unique().tolist())),
            date_start=("date", "min"),
            date_end=("date", "max"),
            avg_e1rm=("e1rm", lambda x: round(x[x > 0].mean(), 1) if (x > 0).any() else 0),
        )
        .reset_index()
    )
    weekly["vol_per_session"] = (weekly["total_volume"] / weekly["sessions"]).round(0)
    weekly["sets_per_session"] = (weekly["total_sets"] / weekly["sessions"]).round(1)
    weekly["vol_delta_pct"] = weekly["total_volume"].pct_change() * 100
    weekly["adherence_pct"] = (weekly["sessions"] / 5 * 100).clip(upper=100).round(0)

    session_dur = df.groupby(["week", "hevy_id"])["duration_min"].first().reset_index()
    dur_weekly = session_dur.groupby("week")["duration_min"].sum().reset_index()
    dur_weekly.columns = ["week", "total_duration"]
    weekly = weekly.merge(dur_weekly, on="week", how="left")
    weekly["density_kg_min"] = (weekly["total_volume"] / weekly["total_duration"]).round(1)

    return weekly


def session_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["hevy_id", "date", "week", "workout_title", "day_name", "day_num", "duration_min", "description"])
        .agg(
            n_exercises=("exercise", "nunique"),
            total_sets=("n_sets", "sum"),
            total_volume=("volume_kg", "sum"),
            total_reps=("total_reps", "sum"),
            top_e1rm=("e1rm", "max"),
        )
        .reset_index()
        .sort_values("date", ascending=False)
    )


def session_detail(df: pd.DataFrame, hevy_id: str = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if hevy_id:
        return df[df["hevy_id"] == hevy_id].copy()
    return df.copy()


# ═══════════════════════════════════════════════════════════════════════
# 2. PR TRACKING
# ═══════════════════════════════════════════════════════════════════════

def pr_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    weighted = df[df["e1rm"] > 0].copy()
    if weighted.empty:
        return pd.DataFrame()
    idx = weighted.groupby("exercise")["e1rm"].idxmax()
    prs = weighted.loc[idx, ["exercise", "max_weight", "max_reps_at_max", "e1rm", "date", "day_name"]].copy()
    prs = prs.sort_values("e1rm", ascending=False).reset_index(drop=True)
    prs.index = prs.index + 1
    return prs


def pr_history(df: pd.DataFrame, exercise: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    ex_df = df[df["exercise"] == exercise].copy()
    if ex_df.empty:
        return pd.DataFrame()
    ex_df = ex_df.sort_values("date")
    ex_df["running_max_e1rm"] = ex_df["e1rm"].cummax()
    ex_df["is_pr"] = ex_df["e1rm"] == ex_df["running_max_e1rm"]
    return ex_df


# ═══════════════════════════════════════════════════════════════════════
# 3. MUSCLE GROUP ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def muscle_volume(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    mg = (
        df.groupby("muscle_group")
        .agg(
            total_volume=("volume_kg", "sum"),
            total_sets=("n_sets", "sum"),
            total_reps=("total_reps", "sum"),
            exercises=("exercise", "nunique"),
            sessions=("hevy_id", "nunique"),
        )
        .reset_index()
    )
    mg["pct_volume"] = (mg["total_volume"] / mg["total_volume"].sum() * 100).round(1)
    mg["color"] = mg["muscle_group"].map(MUSCLE_GROUP_COLORS).fillna("#666")
    mg = mg.sort_values("total_volume", ascending=False).reset_index(drop=True)
    return mg


def weekly_muscle_volume(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["week", "muscle_group"])["volume_kg"]
        .sum()
        .reset_index()
        .pivot_table(index="week", columns="muscle_group", values="volume_kg", fill_value=0)
    )


# ═══════════════════════════════════════════════════════════════════════
# 4. RELATIVE INTENSITY & BBD RATIOS — uses template_id
# ═══════════════════════════════════════════════════════════════════════

def _program_dl_e1rm(df: pd.DataFrame) -> float:
    """Get raw e1RM from the program's deadlift variant (PMR). No conversion."""
    dl_df = df[df["exercise_template_id"] == DEADLIFT_TEMPLATE_ID]
    if not dl_df.empty and dl_df["e1rm"].max() > 0:
        return float(dl_df["e1rm"].max())
    # Fallback: shrug-based PMR estimate (~92.5% of PMR)
    shrug_df = df[df["exercise_template_id"] == SHRUG_TEMPLATE_ID]
    if not shrug_df.empty and shrug_df["e1rm"].max() > 0:
        return round(shrug_df["e1rm"].max() / 0.925 * 0.60, 1)
    return 0.0


def estimate_dl_1rm(df: pd.DataFrame) -> float:
    """Estimate conventional deadlift 1RM.
    
    The weight loaded on the bar for PMR IS 60% of conventional DL 1RM,
    regardless of how many reps are performed with it.
    So: conventional DL 1RM ≈ PMR bar weight / 0.60
    Fallback: estimate from shrug (~92.5% of conventional DL).
    """
    dl_df = df[df["exercise_template_id"] == DEADLIFT_TEMPLATE_ID]
    if not dl_df.empty and dl_df["max_weight"].max() > 0:
        return round(float(dl_df["max_weight"].max()) / 0.60, 1)
    # Fallback: estimate from shrug (~92.5% of conventional DL)
    shrug_df = df[df["exercise_template_id"] == SHRUG_TEMPLATE_ID]
    if not shrug_df.empty and shrug_df["e1rm"].max() > 0:
        return round(shrug_df["e1rm"].max() / 0.925, 1)
    return 0.0


def relative_intensity(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    dl_1rm = _program_dl_e1rm(df)  # Raw PMR e1RM for program-relative %
    ex_max = df.groupby("exercise")["e1rm"].transform("max")
    df["pct_of_pr"] = np.where(ex_max > 0, (df["e1rm"] / ex_max * 100).round(1), 0)
    df["dl_1rm_est"] = dl_1rm
    df["pct_of_dl"] = np.where(dl_1rm > 0, (df["max_weight"] / dl_1rm * 100).round(1), 0)
    return df


def bbd_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate BBD exercise ratios vs program DL (PMR) e1RM — uses template_id."""
    dl_1rm = _program_dl_e1rm(df)  # Raw PMR e1RM, NOT conventional estimate
    if dl_1rm == 0:
        return pd.DataFrame()
    
    ratio_config = get_bbd_ratios()  # {template_id: {label, range}}
    rows = []
    for tid, rx in ratio_config.items():
        ex_df = df[df["exercise_template_id"] == tid]
        # Get display name from data or fallback to EXERCISE_DB
        display_name = (
            ex_df.iloc[0]["exercise"] if not ex_df.empty
            else EXERCISE_DB.get(tid, {}).get("name", tid)
        )
        if ex_df.empty or ex_df["e1rm"].max() <= 0:
            rows.append({
                "exercise": display_name, "label": rx["label"],
                "current_weight": 0, "pct_of_dl": 0,
                "target_low": rx["range"][0], "target_high": rx["range"][1],
                "status": "⬜ Sin datos", "dl_1rm": dl_1rm,
            })
            continue
        best = ex_df.loc[ex_df["e1rm"].idxmax()]
        pct = round(best["max_weight"] / dl_1rm * 100, 1)
        lo, hi = rx["range"]
        if pct < lo:
            status = f"🔴 Bajo ({pct:.0f}%)"
        elif pct > hi:
            status = f"🟡 Alto ({pct:.0f}%)"
        else:
            status = f"🟢 En rango ({pct:.0f}%)"
        rows.append({
            "exercise": display_name, "label": rx["label"],
            "current_weight": best["max_weight"], "pct_of_dl": pct,
            "target_low": lo, "target_high": hi,
            "status": status, "dl_1rm": dl_1rm,
        })
    return pd.DataFrame(rows)


def dominadas_progress(df: pd.DataFrame) -> dict:
    """Track pull-up volume progress — uses template_id."""
    dom = df[df["exercise_template_id"] == PULLUP_TEMPLATE_ID]
    if dom.empty:
        return {"target": 75, "best": 0, "last": 0, "pct": 0, "history": []}
    per_session = dom.groupby(["hevy_id", "date"])["total_reps"].sum().reset_index().sort_values("date")
    return {
        "target": 75,
        "best": int(per_session["total_reps"].max()),
        "last": int(per_session.iloc[-1]["total_reps"]),
        "pct": round(per_session["total_reps"].max() / 75 * 100, 1),
        "history": per_session[["date", "total_reps"]].to_dict("records"),
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. INTRA-SESSION FATIGUE DETECTION
# ═══════════════════════════════════════════════════════════════════════

def intra_session_fatigue(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        reps = row["reps_list"]
        if not isinstance(reps, list) or len(reps) < 3:
            continue
        first_rep = reps[0]
        last_rep = reps[-1]
        if first_rep == 0:
            continue
        fatigue_pct = round((first_rep - last_rep) / first_rep * 100, 1)
        mean_reps = np.mean(reps)
        cv = round(np.std(reps) / mean_reps * 100, 1) if mean_reps > 0 else 0
        if fatigue_pct <= 10:
            pattern = "🟢 Estable"
        elif fatigue_pct <= 25:
            pattern = "🟡 Moderada"
        else:
            pattern = "🔴 Alta"
        rows.append({
            "date": row["date"], "week": row.get("week", 0),
            "exercise": row["exercise"], "day_name": row["day_name"],
            "n_sets": len(reps), "reps_first": first_rep, "reps_last": last_rep,
            "reps_mean": round(mean_reps, 1), "fatigue_pct": fatigue_pct,
            "cv_reps": cv, "pattern": pattern, "reps_list": reps,
            "weight": row["max_weight"],
        })
    return pd.DataFrame(rows)


def fatigue_trend(df: pd.DataFrame) -> pd.DataFrame:
    fatigue = intra_session_fatigue(df)
    if fatigue.empty:
        return pd.DataFrame()
    trend = (
        fatigue.groupby("week")
        .agg(avg_fatigue=("fatigue_pct", "mean"), max_fatigue=("fatigue_pct", "max"),
             avg_cv=("cv_reps", "mean"), n_exercises=("exercise", "count"))
        .reset_index().round(1)
    )
    trend["fatigue_delta"] = trend["avg_fatigue"].diff().round(1)
    return trend


# ═══════════════════════════════════════════════════════════════════════
# 6. TRAINING DENSITY & EFFICIENCY
# ═══════════════════════════════════════════════════════════════════════

def session_density(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    sessions = session_summary(df)
    sessions["density_kg_min"] = (sessions["total_volume"] / sessions["duration_min"]).round(1)
    sessions["sets_per_min"] = (sessions["total_sets"] / sessions["duration_min"]).round(2)
    sessions["reps_per_min"] = (sessions["total_reps"] / sessions["duration_min"]).round(1)
    return sessions


def density_trend(df: pd.DataFrame) -> pd.DataFrame:
    density = session_density(df)
    if density.empty:
        return pd.DataFrame()
    session_dur = df.groupby(["week", "hevy_id"]).agg(
        duration=("duration_min", "first"), volume=("volume_kg", "sum"),
        sets=("n_sets", "sum"),
    ).reset_index()
    wk = session_dur.groupby("week").agg(
        total_duration=("duration", "sum"), total_volume=("volume", "sum"),
        total_sets=("sets", "sum"), sessions=("hevy_id", "nunique"),
    ).reset_index()
    wk["density_kg_min"] = (wk["total_volume"] / wk["total_duration"]).round(1)
    wk["density_delta"] = wk["density_kg_min"].pct_change() * 100
    return wk


# ═══════════════════════════════════════════════════════════════════════
# 7. BODY COMP / RECOVERY CORRELATION
# ═══════════════════════════════════════════════════════════════════════

def correlate_with_body(training_df: pd.DataFrame, body_df: pd.DataFrame) -> pd.DataFrame:
    if training_df.empty or body_df.empty:
        return pd.DataFrame()
    wk_train = weekly_breakdown(training_df)
    body_df = body_df.copy()
    body_df["date"] = pd.to_datetime(body_df["date"])
    body_df["week"] = body_df["date"].apply(calc_week)
    body_cols = [c for c in body_df.columns if c not in ("date", "week", "notas")]
    wk_body = body_df.groupby("week")[body_cols].mean().round(2).reset_index()
    merged = wk_train.merge(wk_body, on="week", how="outer").sort_values("week")
    return merged


def compute_correlations(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty or len(merged) < 3:
        return pd.DataFrame()
    training_metrics = ["total_volume", "total_sets", "avg_e1rm", "density_kg_min"]
    body_metrics = ["peso_corporal", "pct_grasa", "calorias", "proteina", "horas_sueno"]
    t_cols = [c for c in training_metrics if c in merged.columns and merged[c].notna().sum() >= 3]
    b_cols = [c for c in body_metrics if c in merged.columns and merged[c].notna().sum() >= 3]
    if not t_cols or not b_cols:
        return pd.DataFrame()
    rows = []
    for tc in t_cols:
        for bc in b_cols:
            valid = merged[[tc, bc]].dropna()
            if len(valid) < 3:
                continue
            corr = valid[tc].corr(valid[bc])
            rows.append({
                "training_metric": tc, "body_metric": bc,
                "correlation": round(corr, 3), "n_weeks": len(valid),
                "strength": "💪 Fuerte" if abs(corr) > 0.7 else "📊 Moderada" if abs(corr) > 0.4 else "〰️ Débil",
                "direction": "↗️ Positiva" if corr > 0 else "↘️ Negativa",
            })
    return pd.DataFrame(rows).sort_values("correlation", key=abs, ascending=False)


# ═══════════════════════════════════════════════════════════════════════
# 8. STRENGTH STANDARDS (DOTS) — uses template_id
# ═══════════════════════════════════════════════════════════════════════

def dots_coefficient(bw_kg: float, gender: str = "male") -> float:
    if gender == "male":
        a, b, c, d, e = -307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093
    else:
        a, b, c, d, e = -57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706
    denom = a + b * bw_kg + c * bw_kg**2 + d * bw_kg**3 + e * bw_kg**4
    return round(500 / denom, 4) if denom != 0 else 0


def strength_standards(df: pd.DataFrame, bodyweight: float = 86.0) -> pd.DataFrame:
    """Calculate strength standards with DOTS — uses template_id for matching."""
    if df.empty:
        return pd.DataFrame()
    coeff = dots_coefficient(bodyweight)
    standards = get_strength_standards()  # {template_id: {int, adv, elite}}
    
    rows = []
    for tid, th in standards.items():
        ex_df = df[df["exercise_template_id"] == tid]
        if ex_df.empty:
            continue
        best_e1rm = ex_df["e1rm"].max()
        if best_e1rm <= 0:
            continue
        
        # Use the actual display name from workout data
        display_name = ex_df.iloc[0]["exercise"]
        
        ratio = best_e1rm / bodyweight
        dots = round(best_e1rm * coeff, 1)
        if ratio >= th["elite"]:
            level, pct = "🏆 Elite", 95
        elif ratio >= th["adv"]:
            level = "💪 Avanzado"
            pct = round(75 + (ratio - th["adv"]) / (th["elite"] - th["adv"]) * 20)
        elif ratio >= th["int"]:
            level = "📊 Intermedio"
            pct = round(50 + (ratio - th["int"]) / (th["adv"] - th["int"]) * 25)
        else:
            level = "🌱 Principiante"
            pct = round(ratio / th["int"] * 50)
        next_th_kg = (
            th["int"] * bodyweight if ratio < th["int"]
            else th["adv"] * bodyweight if ratio < th["adv"]
            else th["elite"] * bodyweight if ratio < th["elite"]
            else 0
        )
        next_label = (
            "Intermedio" if ratio < th["int"]
            else "Avanzado" if ratio < th["adv"]
            else "Elite" if ratio < th["elite"]
            else "—"
        )
        rows.append({
            "exercise": display_name, "best_e1rm": best_e1rm,
            "bw_ratio": round(ratio, 2), "dots_score": dots,
            "level": level, "percentile": min(pct, 99),
            "next_threshold": f"{next_th_kg:.0f}kg ({next_label})" if next_th_kg > 0 else "—",
            "kg_to_next": round(next_th_kg - best_e1rm, 1) if next_th_kg > 0 else 0,
        })
    return pd.DataFrame(rows).sort_values("dots_score", ascending=False).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# 9. RECOVERY INDICATORS
# ═══════════════════════════════════════════════════════════════════════

def recovery_indicators(df: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly_breakdown(df)
    if weekly.empty:
        return pd.DataFrame()
    fatigue = fatigue_trend(df)
    if not fatigue.empty:
        weekly = weekly.merge(
            fatigue[["week", "avg_fatigue", "max_fatigue", "fatigue_delta"]],
            on="week", how="left",
        )
    else:
        weekly["avg_fatigue"] = np.nan
        weekly["max_fatigue"] = np.nan
        weekly["fatigue_delta"] = np.nan

    def composite_alert(row):
        signals = []
        if pd.notna(row["vol_delta_pct"]) and row["vol_delta_pct"] < -15:
            signals.append("vol_drop")
        if pd.notna(row.get("avg_fatigue")) and row["avg_fatigue"] > 25:
            signals.append("high_fatigue")
        if pd.notna(row.get("fatigue_delta")) and row["fatigue_delta"] > 10:
            signals.append("fatigue_rising")
        if row["adherence_pct"] < 60:
            signals.append("low_adherence")
        n = len(signals)
        if n == 0:
            return "🟢 OK"
        if n == 1:
            return "🟡 Monitorizar"
        return "🔴 Deload"

    weekly["alert"] = weekly.apply(composite_alert, axis=1)
    return weekly


# ═══════════════════════════════════════════════════════════════════════
# 10. ADHERENCE & TARGETS
# ═══════════════════════════════════════════════════════════════════════

def day_adherence(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day_num, cfg in DAY_CONFIG.items():
        day_df = df[df["day_num"] == day_num]
        count = day_df["hevy_id"].nunique()
        last = day_df["date"].max() if not day_df.empty else None
        rows.append({
            "day_num": day_num, "day_name": cfg["name"],
            "focus": cfg["focus"], "times_completed": count,
            "last_date": last, "status": "✅" if count > 0 else "❌",
        })
    return pd.DataFrame(rows)


def vs_targets(df: pd.DataFrame) -> list:
    current_week = int(df["week"].max()) if not df.empty else 1
    wk_df = df[df["week"] == current_week]
    sessions = wk_df["hevy_id"].nunique()
    sets = int(wk_df["n_sets"].sum())
    volume = int(wk_df["volume_kg"].sum())
    return [
        {"metric": "Sesiones", "target": f"{WEEKLY_TARGETS['sessions'][0]}-{WEEKLY_TARGETS['sessions'][1]}",
         "actual": sessions, "pct": round(sessions / WEEKLY_TARGETS["sessions"][0] * 100)},
        {"metric": "Series totales", "target": f"{WEEKLY_TARGETS['total_sets'][0]}-{WEEKLY_TARGETS['total_sets'][1]}",
         "actual": sets, "pct": round(sets / WEEKLY_TARGETS["total_sets"][0] * 100)},
        {"metric": "Volumen (kg)",
         "target": f"{WEEKLY_TARGETS['total_volume_kg'][0]:,}-{WEEKLY_TARGETS['total_volume_kg'][1]:,}",
         "actual": f"{volume:,}", "pct": round(volume / WEEKLY_TARGETS["total_volume_kg"][0] * 100)},
    ]


def key_lifts_progression(df: pd.DataFrame) -> dict:
    """Track progression for key lifts — uses template_id."""
    key_ids = get_key_lift_ids()
    result = {}
    for tid in key_ids:
        ldf = df[df["exercise_template_id"] == tid].copy()
        if ldf.empty:
            continue
        # Use actual display name as dict key
        display_name = ldf.iloc[0]["exercise"]
        ldf = ldf.sort_values("date")
        ldf["running_max"] = ldf["e1rm"].cummax()
        result[display_name] = ldf[
            ["date", "week", "max_weight", "max_reps_at_max", "e1rm", "volume_kg", "n_sets", "running_max"]
        ].reset_index(drop=True)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 15. GAMIFICATION — RPG Strength Levels
# ═══════════════════════════════════════════════════════════════════════

# Achievement definitions
STRENGTH_ACHIEVEMENTS = [
    # ── Deadlift milestones (conventional DL equivalent, estimated from PMR ÷ 0.60) ──
    {"id": "dl_1.5x", "cat": "🏋️ Fuerza", "name": "Deadlift 1.5×BW", "desc": "Peso muerto convencional equivalente a 1.5×BW", "xp": 100,
     "lift_tid": "2B4B7310", "ratio": 1.5, "conv_factor": 0.60},
    {"id": "dl_2x", "cat": "🏋️ Fuerza", "name": "Deadlift 2×BW", "desc": "Peso muerto convencional equivalente a 2×BW", "xp": 250,
     "lift_tid": "2B4B7310", "ratio": 2.0, "conv_factor": 0.60},
    {"id": "dl_2.5x", "cat": "🏋️ Fuerza", "name": "Deadlift 2.5×BW", "desc": "Peso muerto convencional equivalente a 2.5×BW", "xp": 500,
     "lift_tid": "2B4B7310", "ratio": 2.5, "conv_factor": 0.60},
    {"id": "dl_3x", "cat": "🏋️ Fuerza", "name": "Deadlift 3×BW", "desc": "Peso muerto convencional equivalente a 3×BW — élite", "xp": 1000,
     "lift_tid": "2B4B7310", "ratio": 3.0, "conv_factor": 0.60},
    # ── Bench milestones ──
    {"id": "bench_1x", "cat": "🏋️ Fuerza", "name": "Bench 1×BW", "desc": "Press banca a 1 vez tu peso corporal", "xp": 150,
     "lift_tid": "E644F828", "ratio": 1.0},
    {"id": "bench_1.5x", "cat": "🏋️ Fuerza", "name": "Bench 1.5×BW", "desc": "Press banca a 1.5 veces tu peso corporal", "xp": 400,
     "lift_tid": "E644F828", "ratio": 1.5},
    {"id": "bench_2x", "cat": "🏋️ Fuerza", "name": "Bench 2×BW", "desc": "Press banca a 2 veces tu peso corporal — élite", "xp": 800,
     "lift_tid": "E644F828", "ratio": 2.0},
    # ── OHP milestones ──
    {"id": "ohp_0.5x", "cat": "🏋️ Fuerza", "name": "OHP 0.5×BW", "desc": "Press militar a medio peso corporal", "xp": 75,
     "lift_tid": "073032BB", "ratio": 0.5},
    {"id": "ohp_0.75x", "cat": "🏋️ Fuerza", "name": "OHP 0.75×BW", "desc": "Press militar a 0.75 veces tu peso corporal", "xp": 200,
     "lift_tid": "073032BB", "ratio": 0.75},
    {"id": "ohp_1x", "cat": "🏋️ Fuerza", "name": "OHP 1×BW", "desc": "Press militar a tu peso corporal — hito legendario", "xp": 600,
     "lift_tid": "073032BB", "ratio": 1.0},
    # ── Front Squat milestones ──
    {"id": "fsq_1x", "cat": "🏋️ Fuerza", "name": "Front Squat 1×BW", "desc": "Sentadilla frontal a tu peso corporal", "xp": 100,
     "lift_tid": "5046D0A9", "ratio": 1.0},
    {"id": "fsq_1.5x", "cat": "🏋️ Fuerza", "name": "Front Squat 1.5×BW", "desc": "Sentadilla frontal a 1.5 veces tu peso corporal", "xp": 300,
     "lift_tid": "5046D0A9", "ratio": 1.5},
    {"id": "fsq_2x", "cat": "🏋️ Fuerza", "name": "Front Squat 2×BW", "desc": "Sentadilla frontal a 2 veces tu peso corporal — élite", "xp": 700,
     "lift_tid": "5046D0A9", "ratio": 2.0},
    # ── Pendlay Row milestones ──
    {"id": "row_1x", "cat": "🏋️ Fuerza", "name": "Pendlay Row 1×BW", "desc": "Remo Pendlay a tu peso corporal", "xp": 150,
     "lift_tid": "018ADC12", "ratio": 1.0},
    {"id": "row_1.25x", "cat": "🏋️ Fuerza", "name": "Pendlay Row 1.25×BW", "desc": "Remo Pendlay a 1.25 veces tu peso corporal", "xp": 350,
     "lift_tid": "018ADC12", "ratio": 1.25},
    {"id": "row_1.5x", "cat": "🏋️ Fuerza", "name": "Pendlay Row 1.5×BW", "desc": "Remo Pendlay a 1.5 veces tu peso corporal — élite", "xp": 600,
     "lift_tid": "018ADC12", "ratio": 1.5},
]

VOLUME_ACHIEVEMENTS = [
    {"id": "vol_50k", "cat": "📦 Volumen", "name": "50.000 kg", "desc": "Medio camión de volumen total", "xp": 50, "threshold": 50_000},
    {"id": "vol_100k", "cat": "📦 Volumen", "name": "100.000 kg", "desc": "Un camión entero", "xp": 100, "threshold": 100_000},
    {"id": "vol_250k", "cat": "📦 Volumen", "name": "250.000 kg", "desc": "Un cuarto de millón", "xp": 200, "threshold": 250_000},
    {"id": "vol_500k", "cat": "📦 Volumen", "name": "500.000 kg", "desc": "Medio millón de kilos", "xp": 400, "threshold": 500_000},
    {"id": "vol_1m", "cat": "📦 Volumen", "name": "1.000.000 kg", "desc": "Un millón de kilos — máquina", "xp": 800, "threshold": 1_000_000},
]

CONSISTENCY_ACHIEVEMENTS = [
    {"id": "sess_10", "cat": "🔥 Consistencia", "name": "10 sesiones", "desc": "Primeras 10 sesiones completadas", "xp": 25, "threshold": 10},
    {"id": "sess_25", "cat": "🔥 Consistencia", "name": "25 sesiones", "desc": "25 sesiones — ya es hábito", "xp": 75, "threshold": 25},
    {"id": "sess_50", "cat": "🔥 Consistencia", "name": "50 sesiones", "desc": "50 sesiones — dedicación real", "xp": 150, "threshold": 50},
    {"id": "sess_100", "cat": "🔥 Consistencia", "name": "100 sesiones", "desc": "100 sesiones — máquina imparable", "xp": 400, "threshold": 100},
    {"id": "sess_200", "cat": "🔥 Consistencia", "name": "200 sesiones", "desc": "200 sesiones — leyenda", "xp": 800, "threshold": 200},
]

DOTS_ACHIEVEMENTS = [
    {"id": "dots_200", "cat": "💎 DOTS", "name": "DOTS 200+", "desc": "Score DOTS compuesto superior a 200", "xp": 100, "threshold": 200},
    {"id": "dots_300", "cat": "💎 DOTS", "name": "DOTS 300+", "desc": "Score DOTS compuesto superior a 300", "xp": 250, "threshold": 300},
    {"id": "dots_400", "cat": "💎 DOTS", "name": "DOTS 400+", "desc": "Score DOTS compuesto superior a 400 — avanzado", "xp": 500, "threshold": 400},
    {"id": "dots_500", "cat": "💎 DOTS", "name": "DOTS 500+", "desc": "Score DOTS compuesto superior a 500 — élite", "xp": 1000, "threshold": 500},
]

LEVEL_TABLE = [
    (1, 0, "Novato"),
    (2, 50, "Iniciado"),
    (3, 125, "Aprendiz"),
    (4, 225, "Guerrero"),
    (5, 375, "Veterano"),
    (6, 575, "Campeón"),
    (7, 850, "Titán"),
    (8, 1200, "Leyenda"),
    (9, 1700, "Mítico"),
    (10, 2500, "Inmortal"),
]


def _check_lift_achievement(ach: dict, df: pd.DataFrame, bodyweight: float) -> dict:
    """Check a BW-ratio lift achievement.
    
    If conv_factor is present (e.g. 0.60 for PMR→conventional DL),
    the raw e1RM is divided by conv_factor to estimate the conventional equivalent.
    """
    tid = ach["lift_tid"]
    target_ratio = ach["ratio"]
    conv_factor = ach.get("conv_factor", 1.0)  # 1.0 = no conversion
    target_kg = target_ratio * bodyweight

    ex_df = df[df["exercise_template_id"] == tid]
    if ex_df.empty or ex_df["e1rm"].max() <= 0:
        return {**ach, "unlocked": False, "progress": 0.0, "current": "Sin datos", "target_kg": target_kg}

    if conv_factor != 1.0:
        # PMR: the bar weight IS the percentage of conventional DL 1RM
        bar_weight = ex_df["max_weight"].max()
        estimated_1rm = bar_weight / conv_factor
        ratio = estimated_1rm / bodyweight
        label = f"{bar_weight:.0f}kg PMR → ~{estimated_1rm:.0f}kg conv ({ratio:.2f}×BW)"
    else:
        estimated_1rm = ex_df["e1rm"].max()
        ratio = estimated_1rm / bodyweight
        label = f"{estimated_1rm:.0f}kg ({ratio:.2f}×BW)"

    progress = min(1.0, ratio / target_ratio)

    return {
        **ach, "unlocked": ratio >= target_ratio, "progress": round(progress, 3),
        "current": label, "target_kg": target_kg,
    }


def gamification_status(df: pd.DataFrame, bodyweight: float = 86.0) -> dict:
    """
    Calculate full RPG gamification status:
    - All achievements with unlock status and progress
    - Total XP and current level
    - Next level info
    """
    if df.empty:
        return {"level": 1, "title": "Novato", "xp": 0, "achievements": [], "unlocked": 0, "total": 0}

    summary = global_summary(df)
    total_volume = summary.get("total_volume", 0)
    total_sessions = summary.get("total_sessions", 0)

    # Composite DOTS
    ss = strength_standards(df, bodyweight)
    composite_dots = ss["dots_score"].sum() if not ss.empty else 0

    achievements = []

    # Strength
    for ach in STRENGTH_ACHIEVEMENTS:
        achievements.append(_check_lift_achievement(ach, df, bodyweight))

    # Volume
    for ach in VOLUME_ACHIEVEMENTS:
        progress = min(1.0, total_volume / ach["threshold"])
        achievements.append({
            **ach, "unlocked": total_volume >= ach["threshold"],
            "progress": round(progress, 3), "current": f"{total_volume:,} kg", "target_kg": ach["threshold"],
        })

    # Consistency
    for ach in CONSISTENCY_ACHIEVEMENTS:
        progress = min(1.0, total_sessions / ach["threshold"])
        achievements.append({
            **ach, "unlocked": total_sessions >= ach["threshold"],
            "progress": round(progress, 3), "current": f"{total_sessions} sesiones", "target_kg": ach["threshold"],
        })

    # DOTS
    for ach in DOTS_ACHIEVEMENTS:
        progress = min(1.0, composite_dots / ach["threshold"]) if ach["threshold"] > 0 else 0
        achievements.append({
            **ach, "unlocked": composite_dots >= ach["threshold"],
            "progress": round(progress, 3), "current": f"DOTS {composite_dots:.0f}", "target_kg": ach["threshold"],
        })

    # XP and level
    total_xp = sum(a["xp"] for a in achievements if a["unlocked"])
    unlocked_count = sum(1 for a in achievements if a["unlocked"])

    level, title = 1, "Novato"
    next_level_xp, next_title = LEVEL_TABLE[1][1], LEVEL_TABLE[1][2]
    for lvl, xp_req, ttl in LEVEL_TABLE:
        if total_xp >= xp_req:
            level, title = lvl, ttl
        else:
            next_level_xp, next_title = xp_req, ttl
            break
    else:
        next_level_xp, next_title = total_xp, title

    current_floor = LEVEL_TABLE[level - 1][1]
    level_range = next_level_xp - current_floor
    level_progress = (total_xp - current_floor) / level_range if level_range > 0 and level < 10 else 1.0

    return {
        "level": level, "title": title, "xp": total_xp,
        "xp_for_next": max(0, next_level_xp - total_xp),
        "next_title": next_title, "level_progress": round(level_progress, 3),
        "achievements": achievements, "unlocked": unlocked_count, "total": len(achievements),
        "composite_dots": round(composite_dots, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 11. PLATEAU DETECTION — Phase 1
# ═══════════════════════════════════════════════════════════════════════

def plateau_detection(df: pd.DataFrame, stale_weeks: int = 3) -> pd.DataFrame:
    """
    Detect exercises where e1RM has not improved in `stale_weeks` or more.
    Returns a DataFrame with one row per exercise showing plateau status.
    Requires ≥2 weeks of data per exercise to be meaningful.
    """
    if df.empty:
        return pd.DataFrame()

    weighted = df[df["e1rm"] > 0].copy()
    if weighted.empty:
        return pd.DataFrame()

    current_week = int(df["week"].max()) if not df.empty else 1
    rows = []

    for exercise in weighted["exercise"].unique():
        ex_df = weighted[weighted["exercise"] == exercise].sort_values("date")
        weeks_present = ex_df["week"].nunique()
        if weeks_present < 2:
            continue

        # Best e1RM per week
        weekly_best = ex_df.groupby("week")["e1rm"].max().reset_index()
        weekly_best = weekly_best.sort_values("week")

        # Current PR and when it was set
        pr_e1rm = weekly_best["e1rm"].max()
        pr_week = weekly_best.loc[weekly_best["e1rm"].idxmax(), "week"]
        weeks_since_pr = current_week - pr_week

        # Trend: linear regression slope over last 4 weeks
        recent = weekly_best.tail(4)
        if len(recent) >= 2:
            x = recent["week"].values.astype(float)
            y = recent["e1rm"].values.astype(float)
            slope = np.polyfit(x, y, 1)[0]
        else:
            slope = 0.0

        # Classification
        if weeks_since_pr >= stale_weeks and slope < 0.5:
            status = "🔴 Estancado"
        elif weeks_since_pr >= 2 and slope < 0.5:
            status = "🟡 Vigilar"
        elif slope > 1.0:
            status = "🟢 Subiendo"
        else:
            status = "🟢 Estable"

        # Last week vs PR
        last_week_best = weekly_best.iloc[-1]["e1rm"]
        pct_of_pr = round(last_week_best / pr_e1rm * 100, 1) if pr_e1rm > 0 else 0

        rows.append({
            "exercise": exercise,
            "pr_e1rm": round(pr_e1rm, 1),
            "pr_week": int(pr_week),
            "weeks_since_pr": int(weeks_since_pr),
            "last_e1rm": round(last_week_best, 1),
            "pct_of_pr": pct_of_pr,
            "trend_slope": round(slope, 2),
            "weeks_tracked": weeks_present,
            "status": status,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("weeks_since_pr", ascending=False).reset_index(drop=True)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 12. ACWR — Acute:Chronic Workload Ratio — Phase 1
# ═══════════════════════════════════════════════════════════════════════

def acwr(df: pd.DataFrame, acute_weeks: int = 1, chronic_weeks: int = 4) -> pd.DataFrame:
    """
    Acute:Chronic Workload Ratio per week.
    Acute = last `acute_weeks` volume. Chronic = rolling avg of last `chronic_weeks`.
    Safe zone: 0.8 – 1.3. Warning: 1.3 – 1.5. Risk: >1.5 or <0.8.
    Requires at least `chronic_weeks` of data to compute.
    """
    wk = weekly_breakdown(df)
    if wk.empty or len(wk) < 2:
        return pd.DataFrame()

    wk = wk.sort_values("week").copy()
    # Chronic load = rolling mean of volume over last N weeks (excluding current)
    wk["chronic_volume"] = wk["total_volume"].rolling(window=chronic_weeks, min_periods=2).mean()
    wk["acute_volume"] = wk["total_volume"]  # acute = current week

    # ACWR = acute / chronic
    wk["acwr"] = np.where(
        wk["chronic_volume"] > 0,
        (wk["acute_volume"] / wk["chronic_volume"]).round(2),
        np.nan,
    )

    # Zone classification
    def classify_acwr(ratio):
        if pd.isna(ratio):
            return "⬜ Insuf. datos"
        if ratio < 0.8:
            return "🔵 Detraining"
        if ratio <= 1.3:
            return "🟢 Zona segura"
        if ratio <= 1.5:
            return "🟡 Overreaching"
        return "🔴 Riesgo lesión"

    wk["acwr_zone"] = wk["acwr"].apply(classify_acwr)

    # Week-over-week volume delta for context
    wk["vol_change_pct"] = (wk["total_volume"].pct_change() * 100).round(1)

    return wk[["week", "acute_volume", "chronic_volume", "acwr", "acwr_zone",
               "vol_change_pct", "sessions", "date_start", "date_end"]].copy()


# ═══════════════════════════════════════════════════════════════════════
# 13. MESOCYCLES — Automatic 4-week blocks — Phase 1
# ═══════════════════════════════════════════════════════════════════════

def calc_mesocycle(week: int) -> int:
    """Map a program week to its mesocycle number (1-indexed, 4-week blocks)."""
    return max(1, ((week - 1) // 4) + 1)


def mesocycle_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group training into 4-week mesocycle blocks.
    Compare volume, intensity, fatigue, and sessions across mesocycles.
    """
    if df.empty:
        return pd.DataFrame()

    wk = weekly_breakdown(df)
    if wk.empty:
        return pd.DataFrame()

    wk["mesocycle"] = wk["week"].apply(calc_mesocycle)

    fatigue_data = fatigue_trend(df)

    meso = wk.groupby("mesocycle").agg(
        weeks=("week", "nunique"),
        week_start=("week", "min"),
        week_end=("week", "max"),
        total_sessions=("sessions", "sum"),
        total_volume=("total_volume", "sum"),
        avg_weekly_volume=("total_volume", "mean"),
        total_sets=("total_sets", "sum"),
        avg_e1rm=("avg_e1rm", "mean"),
        avg_density=("density_kg_min", "mean"),
        date_start=("date_start", "min"),
        date_end=("date_end", "max"),
    ).reset_index()
    # Round only numeric columns to avoid warning on datetime
    _num = meso.select_dtypes(include=[np.number]).columns
    meso[_num] = meso[_num].round(1)

    # Merge fatigue if available
    if not fatigue_data.empty:
        fatigue_data["mesocycle"] = fatigue_data["week"].apply(calc_mesocycle)
        meso_fatigue = fatigue_data.groupby("mesocycle").agg(
            avg_fatigue=("avg_fatigue", "mean"),
        ).reset_index().round(1)
        meso = meso.merge(meso_fatigue, on="mesocycle", how="left")
    else:
        meso["avg_fatigue"] = np.nan

    # Deltas vs previous mesocycle
    meso["vol_delta_pct"] = meso["avg_weekly_volume"].pct_change().mul(100).round(1)
    meso["e1rm_delta"] = meso["avg_e1rm"].diff().round(1)
    meso["fatigue_delta"] = meso["avg_fatigue"].diff().round(1)
    meso["density_delta"] = meso["avg_density"].pct_change().mul(100).round(1)

    return meso


def mesocycle_comparison(df: pd.DataFrame, meso_a: int, meso_b: int) -> dict:
    """
    Compare two specific mesocycles side-by-side.
    Returns dict with deltas and insights.
    """
    meso_df = mesocycle_summary(df)
    if meso_df.empty:
        return {}

    a = meso_df[meso_df["mesocycle"] == meso_a]
    b = meso_df[meso_df["mesocycle"] == meso_b]

    if a.empty or b.empty:
        return {}

    a, b = a.iloc[0], b.iloc[0]

    def pct_delta(new, old):
        if old == 0 or pd.isna(old):
            return 0
        return round((new - old) / old * 100, 1)

    return {
        "meso_a": meso_a, "meso_b": meso_b,
        "vol_delta_pct": pct_delta(b["avg_weekly_volume"], a["avg_weekly_volume"]),
        "e1rm_delta": round(b["avg_e1rm"] - a["avg_e1rm"], 1),
        "fatigue_delta": round(b["avg_fatigue"] - a["avg_fatigue"], 1) if pd.notna(b["avg_fatigue"]) and pd.notna(a["avg_fatigue"]) else None,
        "sessions_delta": int(b["total_sessions"] - a["total_sessions"]),
        "density_delta_pct": pct_delta(b["avg_density"], a["avg_density"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# 14. HISTORICAL COMPARISON ("Yo vs Yo") — Phase 1
# ═══════════════════════════════════════════════════════════════════════

def strength_profile(df: pd.DataFrame, as_of_week: int = None) -> dict:
    """
    Build a strength profile with 5 axes for radar chart:
    - Empuje Vertical (OHP, Klokov, Bradford)
    - Empuje Horizontal (Bench variations, Incline)
    - Tracción (Pendlay, Pull-ups, DB Row, Cable Row)
    - Piernas (Front Squat, Quarter Squat, Deadlift, Lunges, Leg Curl)
    - Core & Grip (Ab Wheel, Dead Hold, KB Swing)

    Returns {axis: normalized_score 0-100} based on best e1RM relative to body weight.
    If as_of_week is given, only considers data up to that week.
    """
    if df.empty:
        return {}

    from src.config import BODYWEIGHT

    data = df.copy()
    if as_of_week is not None:
        data = data[data["week"] <= as_of_week]
    if data.empty:
        return {}

    # Map template_ids to axes
    axis_map = {}
    for tid, info in EXERCISE_DB.items():
        mg = info["muscle_group"]
        if mg in ("Hombros",):
            axis_map[tid] = "Empuje Vertical"
        elif mg in ("Pecho",):
            axis_map[tid] = "Empuje Horizontal"
        elif mg in ("Espalda", "Trapecios"):
            axis_map[tid] = "Tracción"
        elif mg in ("Cuádriceps", "Piernas", "Isquios", "Gemelos", "Espalda Baja"):
            axis_map[tid] = "Piernas"
        elif mg in ("Core", "Agarre", "Posterior"):
            axis_map[tid] = "Core & Grip"
        # Biceps/Triceps not key axes

    axes = ["Empuje Vertical", "Empuje Horizontal", "Tracción", "Piernas", "Core & Grip"]
    profile = {}

    for axis in axes:
        tids = [tid for tid, a in axis_map.items() if a == axis]
        ax_df = data[data["exercise_template_id"].isin(tids)]
        if ax_df.empty or ax_df["e1rm"].max() <= 0:
            profile[axis] = 0
            continue
        # Score = best e1RM / bodyweight, normalized to 0-100 scale
        # Using approximate ceilings: 3xBW legs, 2xBW pull, 1.5xBW push, 1xBW core
        ceilings = {
            "Empuje Vertical": 1.25,
            "Empuje Horizontal": 2.0,
            "Tracción": 2.0,
            "Piernas": 3.0,
            "Core & Grip": 1.0,
        }
        best_ratio = ax_df["e1rm"].max() / BODYWEIGHT
        ceiling = ceilings.get(axis, 2.0)
        score = min(100, round(best_ratio / ceiling * 100))
        profile[axis] = score

    return profile


def historical_comparison(df: pd.DataFrame, weeks_ago: int = 4) -> dict:
    """
    Compare current metrics vs X weeks ago.
    Returns dict with per-exercise and aggregate comparisons.
    """
    if df.empty:
        return {}

    current_week = int(df["week"].max()) if not df.empty else 1
    compare_week = max(1, current_week - weeks_ago)

    # Only meaningful if we have data in both periods
    current_data = df[df["week"] >= current_week - 1]  # last 2 weeks as "current"
    past_data = df[df["week"] <= compare_week]

    if current_data.empty or past_data.empty:
        return {"error": "Datos insuficientes para comparar"}

    # Aggregate comparisons
    now_vol = current_data.groupby("week")["volume_kg"].sum().mean()
    then_vol = past_data.groupby("week")["volume_kg"].sum().mean()

    # Per-exercise e1RM comparison
    exercise_deltas = []
    for exercise in df["exercise"].unique():
        now_ex = current_data[current_data["exercise"] == exercise]
        then_ex = past_data[past_data["exercise"] == exercise]
        if now_ex.empty or then_ex.empty:
            continue
        now_e1rm = now_ex["e1rm"].max()
        then_e1rm = then_ex["e1rm"].max()
        if then_e1rm <= 0:
            continue
        delta_pct = round((now_e1rm - then_e1rm) / then_e1rm * 100, 1)
        exercise_deltas.append({
            "exercise": exercise,
            "e1rm_now": round(now_e1rm, 1),
            "e1rm_then": round(then_e1rm, 1),
            "delta_kg": round(now_e1rm - then_e1rm, 1),
            "delta_pct": delta_pct,
            "trend": "📈" if delta_pct > 2 else "📉" if delta_pct < -2 else "➡️",
        })

    # Strength profiles for radar
    profile_now = strength_profile(df, as_of_week=current_week)
    profile_then = strength_profile(df, as_of_week=compare_week)

    return {
        "weeks_ago": weeks_ago,
        "current_week": current_week,
        "compare_week": compare_week,
        "volume_now": round(now_vol),
        "volume_then": round(then_vol),
        "volume_delta_pct": round((now_vol - then_vol) / then_vol * 100, 1) if then_vol > 0 else 0,
        "exercise_deltas": sorted(exercise_deltas, key=lambda x: x["delta_pct"], reverse=True),
        "profile_now": profile_now,
        "profile_then": profile_then,
    }

