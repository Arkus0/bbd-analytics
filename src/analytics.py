"""
BBD Analytics — Pandas Analytics Engine v2
All calculations, aggregations, and derived metrics.

Modules:
  1. Core (global summary, weekly breakdown, session detail)
  2. PR tracking
  3. Muscle group analysis
  4. Relative intensity & BBD ratios        ← NEW
  5. Intra-session fatigue detection         ← NEW
  6. Training density & efficiency           ← NEW
  7. Body comp / recovery correlation        ← NEW
  8. Strength standards (DOTS)               ← NEW
  9. Recovery indicators (improved)          ← NEW
  10. Adherence & targets
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.config import (
    PROGRAM_START,
    DAY_CONFIG,
    MUSCLE_MAP,
    MUSCLE_GROUP_COLORS,
    KEY_LIFTS,
    WEEKLY_TARGETS,
)


def calc_week(date: pd.Timestamp) -> int:
    delta = (date - pd.Timestamp(PROGRAM_START)).days
    return max(1, (delta // 7) + 1)


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["week"] = df["date"].apply(calc_week)
    df["muscle_group"] = df["exercise"].map(MUSCLE_MAP).fillna("Otro")
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
        "current_week": calc_week(pd.Timestamp(datetime.now().date())),
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

    # Total duration per week
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
        df.groupby(["hevy_id", "date", "workout_title", "day_name", "day_num", "duration_min", "description"])
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
# 4. NEW — RELATIVE INTENSITY & BBD RATIOS
# ═══════════════════════════════════════════════════════════════════════

BBD_LOAD_PRESCRIPTIONS = {
    "Encogimiento de Hombros (Barra)": {"target_pct": (85, 100), "label": "Shrug / DL"},
    "Remo Pendlay (Barra)": {"target_pct": (45, 55), "label": "Pendlay / DL"},
    "Sentadilla Frontal (Barra)": {"target_pct": (55, 70), "label": "Front Squat / DL"},
    "Press Militar (Barra)": {"target_pct": (35, 45), "label": "OHP / DL"},
    "Klokov Press": {"target_pct": (25, 35), "label": "Klokov / DL"},
}

DEADLIFT_EXERCISES = ["Peso Muerto (Barra)", "Reverse Deadlift (Bob Peoples)"]


def estimate_dl_1rm(df: pd.DataFrame) -> float:
    dl_df = df[df["exercise"].isin(DEADLIFT_EXERCISES)]
    if not dl_df.empty and dl_df["e1rm"].max() > 0:
        return float(dl_df["e1rm"].max())
    shrug = df[df["exercise"] == "Encogimiento de Hombros (Barra)"]
    if not shrug.empty and shrug["e1rm"].max() > 0:
        return round(shrug["e1rm"].max() / 0.925, 1)
    return 0.0


def relative_intensity(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    dl_1rm = estimate_dl_1rm(df)
    ex_max = df.groupby("exercise")["e1rm"].transform("max")
    df["pct_of_pr"] = np.where(ex_max > 0, (df["e1rm"] / ex_max * 100).round(1), 0)
    df["dl_1rm_est"] = dl_1rm
    df["pct_of_dl"] = np.where(dl_1rm > 0, (df["max_weight"] / dl_1rm * 100).round(1), 0)
    return df


def bbd_ratios(df: pd.DataFrame) -> pd.DataFrame:
    dl_1rm = estimate_dl_1rm(df)
    if dl_1rm == 0:
        return pd.DataFrame()
    rows = []
    for exercise, rx in BBD_LOAD_PRESCRIPTIONS.items():
        ex_df = df[df["exercise"] == exercise]
        if ex_df.empty:
            rows.append({
                "exercise": exercise, "label": rx["label"],
                "current_weight": 0, "pct_of_dl": 0,
                "target_low": rx["target_pct"][0], "target_high": rx["target_pct"][1],
                "status": "⬜ Sin datos", "dl_1rm": dl_1rm,
            })
            continue
        best = ex_df.loc[ex_df["e1rm"].idxmax()]
        pct = round(best["max_weight"] / dl_1rm * 100, 1)
        lo, hi = rx["target_pct"]
        if pct < lo:
            status = f"🔴 Bajo ({pct:.0f}%)"
        elif pct > hi:
            status = f"🟡 Alto ({pct:.0f}%)"
        else:
            status = f"🟢 En rango ({pct:.0f}%)"
        rows.append({
            "exercise": exercise, "label": rx["label"],
            "current_weight": best["max_weight"], "pct_of_dl": pct,
            "target_low": lo, "target_high": hi,
            "status": status, "dl_1rm": dl_1rm,
        })
    return pd.DataFrame(rows)


def dominadas_progress(df: pd.DataFrame) -> dict:
    dom = df[df["exercise"] == "Dominada"]
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
# 5. NEW — INTRA-SESSION FATIGUE DETECTION
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
# 6. NEW — TRAINING DENSITY & EFFICIENCY
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
# 7. NEW — BODY COMP / RECOVERY CORRELATION
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
# 8. NEW — STRENGTH STANDARDS (DOTS)
# ═══════════════════════════════════════════════════════════════════════


def dots_coefficient(bw_kg: float, gender: str = "male") -> float:
    if gender == "male":
        a, b, c, d, e = -307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.000001093
    else:
        a, b, c, d, e = -57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706
    denom = a + b * bw_kg + c * bw_kg**2 + d * bw_kg**3 + e * bw_kg**4
    return round(500 / denom, 4) if denom != 0 else 0


def strength_standards(df: pd.DataFrame, bodyweight: float = 86.0) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    coeff = dots_coefficient(bodyweight)
    STANDARDS = {
        "Peso Muerto (Barra)": {"int": 1.75, "adv": 2.5, "elite": 3.0},
        "Reverse Deadlift (Bob Peoples)": {"int": 1.75, "adv": 2.5, "elite": 3.0},
        "Sentadilla Frontal (Barra)": {"int": 1.25, "adv": 1.75, "elite": 2.25},
        "Press de Banca - Agarre Cerrado (Barra)": {"int": 1.1, "adv": 1.5, "elite": 2.0},
        "Press Militar (Barra)": {"int": 0.65, "adv": 1.0, "elite": 1.25},
        "Encogimiento de Hombros (Barra)": {"int": 1.0, "adv": 1.5, "elite": 2.0},
        "Remo Pendlay (Barra)": {"int": 0.75, "adv": 1.25, "elite": 1.5},
    }
    rows = []
    for exercise, th in STANDARDS.items():
        ex_df = df[df["exercise"] == exercise]
        if ex_df.empty:
            continue
        best_e1rm = ex_df["e1rm"].max()
        if best_e1rm <= 0:
            continue
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
            "exercise": exercise, "best_e1rm": best_e1rm,
            "bw_ratio": round(ratio, 2), "dots_score": dots,
            "level": level, "percentile": min(pct, 99),
            "next_threshold": f"{next_th_kg:.0f}kg ({next_label})" if next_th_kg > 0 else "—",
            "kg_to_next": round(next_th_kg - best_e1rm, 1) if next_th_kg > 0 else 0,
        })
    return pd.DataFrame(rows).sort_values("dots_score", ascending=False).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# 9. RECOVERY INDICATORS (IMPROVED)
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


def vs_targets(df: pd.DataFrame) -> list[dict]:
    current_week = calc_week(pd.Timestamp(datetime.now().date()))
    wk_df = df[df["week"] == current_week]
    if wk_df.empty and not df.empty:
        current_week = df["week"].max()
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


def key_lifts_progression(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    result = {}
    for lift in KEY_LIFTS:
        ldf = df[df["exercise"] == lift].copy()
        if ldf.empty:
            continue
        ldf = ldf.sort_values("date")
        ldf["running_max"] = ldf["e1rm"].cummax()
        result[lift] = ldf[
            ["date", "week", "max_weight", "max_reps_at_max", "e1rm", "volume_kg", "n_sets", "running_max"]
        ].reset_index(drop=True)
    return result
