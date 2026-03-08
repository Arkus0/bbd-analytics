"""
Candito Linear Program — Analytics Engine

Fetch/parse workouts, track progression, auto-update Hevy routines.
"""
import os
import re
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from src.config_candito import (
    CANDITO_FOLDER_ID, EXERCISE_DB_CANDITO, DAY_CONFIG_CANDITO,
    STARTING_WEIGHTS, PROGRESSION_INCREMENT, MAIN_LIFT_TIDS,
    TID_TO_LIFT, DAY_ROUTINE_MAP_CANDITO, LIFT_PAIRS,
    STRENGTH_STANDARDS_CANDITO, round_to_plate,
)
from src.config import BODYWEIGHT, HEVY_API_KEY

BASE_URL = "https://api.hevyapp.com/v1"
HEADERS = {"accept": "application/json", "api-key": HEVY_API_KEY}


# ══════════════════════════════════════════════════════════════════════
# DATA FETCH & PARSE
# ══════════════════════════════════════════════════════════════════════

def _is_candito_workout(title: str) -> bool:
    """Check if a workout title matches Candito naming convention."""
    return bool(re.match(r"Candito\s*D\d", title, re.IGNORECASE))


def fetch_candito_workouts() -> list[dict]:
    """Fetch all Candito LP workouts from Hevy (title-based filter)."""
    all_workouts = []
    page = 1
    while True:
        time.sleep(0.35)
        r = requests.get(
            f"{BASE_URL}/workouts",
            headers=HEADERS,
            params={"page": page, "pageSize": 10},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        wks = data.get("workouts", [])
        if not wks:
            break
        for w in wks:
            if _is_candito_workout(w.get("title", "")):
                all_workouts.append(w)
        if page >= data.get("page_count", 1):
            break
        page += 1
    return all_workouts


def _get_day_number(title: str) -> int | None:
    """Extract day number from 'Candito D1 - ...' title."""
    m = re.match(r"Candito\s*D(\d)", title, re.IGNORECASE)
    return int(m.group(1)) if m else None


def workouts_to_dataframe_candito(workouts: list[dict]) -> pd.DataFrame:
    """Convert raw Hevy workouts to flat DataFrame (one row per exercise)."""
    rows = []
    for w in workouts:
        date = w["start_time"][:10]
        title = w["title"]
        hevy_id = w["id"]
        day_num = _get_day_number(title)

        start = datetime.fromisoformat(w["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(w["end_time"].replace("Z", "+00:00"))
        duration_min = round((end - start).total_seconds() / 60)

        day_cfg = DAY_CONFIG_CANDITO.get(day_num, {})
        day_name = day_cfg.get("name", title)
        day_type = day_cfg.get("type", "unknown")

        for ex in w.get("exercises", []):
            tid = ex.get("exercise_template_id", "")
            ex_cfg = EXERCISE_DB_CANDITO.get(tid, {})
            sets = ex.get("sets", [])
            working = [s for s in sets if s.get("type") in ("normal", "failure", None)]
            if not working:
                working = sets

            reps_list = [s.get("reps", 0) or 0 for s in working]
            weights = [s.get("weight_kg", 0) or 0 for s in working]
            volume = sum(wt * r for wt, r in zip(weights, reps_list))

            max_w = max(weights) if weights else 0
            reps_at_max = [r for wt, r in zip(weights, reps_list) if wt == max_w]
            max_r = max(reps_at_max) if reps_at_max else 0

            # Epley e1RM
            if max_w > 0 and max_r > 0:
                e1rm = round(max_w * (1 + max_r / 30), 1) if max_r > 1 else max_w
            else:
                e1rm = 0

            lift_key = ex_cfg.get("lift_key", "")
            role = ex_cfg.get("role", "unknown")
            prescribed = ex_cfg.get("prescribed", {})

            rows.append({
                "date": pd.Timestamp(date),
                "hevy_id": hevy_id,
                "workout_title": title,
                "day_num": day_num,
                "day_name": day_name,
                "day_type": day_type,
                "duration_min": duration_min,
                "exercise": ex["title"],
                "exercise_template_id": tid,
                "lift_key": lift_key,
                "role": role,
                "n_sets": len(working),
                "reps_list": reps_list,
                "total_reps": sum(reps_list),
                "max_weight": max_w,
                "max_reps_at_max": max_r,
                "volume_kg": volume,
                "e1rm": e1rm,
                "top_set": f"{max_w}kg x {max_r}" if max_w > 0 else f"BW x {max_r}",
                "prescribed_sets": prescribed.get("sets", 0),
                "prescribed_reps": prescribed.get("reps", 0),
                "muscle_group": ex_cfg.get("muscle_group", "Otro"),
                "is_compound": ex_cfg.get("is_compound", False),
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "day_num"]).reset_index(drop=True)
    return df


# ══════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════

def global_summary_candito(df: pd.DataFrame) -> dict:
    """High-level program stats."""
    if df.empty:
        return {"total_sessions": 0, "total_volume_kg": 0, "total_sets": 0}
    sessions = df["hevy_id"].nunique()
    return {
        "total_sessions": sessions,
        "total_volume_kg": int(df["volume_kg"].sum()),
        "total_sets": int(df["n_sets"].sum()),
        "total_reps": int(df["total_reps"].sum()),
        "avg_duration": round(df.groupby("hevy_id")["duration_min"].first().mean(), 1),
        "weeks_active": max(1, (df["date"].max() - df["date"].min()).days // 7 + 1),
        "first_session": df["date"].min(),
        "last_session": df["date"].max(),
    }


def pr_table_candito(df: pd.DataFrame) -> pd.DataFrame:
    """Best e1RM per exercise."""
    if df.empty:
        return pd.DataFrame()
    compounds = df[df["is_compound"] & (df["max_weight"] > 0)]
    if compounds.empty:
        return pd.DataFrame()
    idx = compounds.groupby("exercise_template_id")["e1rm"].idxmax()
    prs = compounds.loc[idx, ["exercise", "exercise_template_id", "lift_key",
                               "max_weight", "max_reps_at_max", "e1rm", "date"]].copy()
    prs = prs.sort_values("e1rm", ascending=False).reset_index(drop=True)
    return prs


def lift_progression_candito(df: pd.DataFrame) -> pd.DataFrame:
    """Track weight used per session for each main/secondary lift."""
    if df.empty:
        return pd.DataFrame()
    main = df[df["role"].isin(["main", "secondary"]) & (df["max_weight"] > 0)]
    if main.empty:
        return pd.DataFrame()
    prog = main.groupby(["date", "lift_key", "exercise"]).agg(
        weight=("max_weight", "max"),
        e1rm=("e1rm", "max"),
        total_reps=("total_reps", "sum"),
        n_sets=("n_sets", "sum"),
        volume=("volume_kg", "sum"),
    ).reset_index()
    return prog.sort_values(["lift_key", "date"]).reset_index(drop=True)


def session_summary_candito(df: pd.DataFrame) -> pd.DataFrame:
    """One row per session with key stats."""
    if df.empty:
        return pd.DataFrame()
    sessions = []
    for hid, grp in df.groupby("hevy_id"):
        first = grp.iloc[0]
        main_lifts = grp[grp["role"] == "main"]
        top = main_lifts.loc[main_lifts["e1rm"].idxmax()] if not main_lifts.empty else first
        sessions.append({
            "date": first["date"],
            "day_num": first["day_num"],
            "day_name": first["day_name"],
            "day_type": first["day_type"],
            "duration_min": first["duration_min"],
            "volume_kg": int(grp["volume_kg"].sum()),
            "total_sets": int(grp["n_sets"].sum()),
            "exercises": len(grp),
            "top_set": top["top_set"],
            "top_e1rm": top["e1rm"],
            "hevy_id": hid,
        })
    return pd.DataFrame(sessions).sort_values("date", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════
# PROGRESSION ENGINE
# ══════════════════════════════════════════════════════════════════════

def analyze_progression(df: pd.DataFrame) -> dict:
    """
    Analyze each main lift's progression status.

    Returns {lift_key: {
        current_weight, prescribed_sets, prescribed_reps,
        completed_all_reps (bool), sessions_at_weight (int),
        suggested_weight, status ('progress' | 'hold' | 'stall')
    }}
    """
    if df.empty:
        return {}

    results = {}
    main_lifts = df[df["role"].isin(["main", "secondary"])]

    for lift_key, tid in MAIN_LIFT_TIDS.items():
        lift_df = main_lifts[main_lifts["exercise_template_id"] == tid].copy()
        if lift_df.empty:
            continue

        ex_cfg = EXERCISE_DB_CANDITO.get(tid, {})
        prescribed = ex_cfg.get("prescribed", {})
        p_sets = prescribed.get("sets", 3)
        p_reps = prescribed.get("reps", 6)

        # Get most recent session for this lift
        latest_date = lift_df["date"].max()
        latest = lift_df[lift_df["date"] == latest_date].iloc[0]
        current_weight = latest["max_weight"]

        # Check if all prescribed reps were completed in latest session
        latest_session = lift_df[lift_df["date"] == latest_date]
        total_reps_done = latest_session["total_reps"].sum()
        target_reps = p_sets * p_reps
        completed = total_reps_done >= target_reps

        # Count consecutive sessions at this weight
        lift_by_date = lift_df.sort_values("date", ascending=False)
        dates_at_weight = lift_by_date.groupby("date")["max_weight"].max()
        sessions_at = 0
        for d in dates_at_weight.sort_index(ascending=False).index:
            if dates_at_weight[d] == current_weight:
                sessions_at += 1
            else:
                break

        # Determine status
        increment = PROGRESSION_INCREMENT.get(lift_key, 2.5)
        if completed:
            status = "progress"
            suggested = round_to_plate(current_weight + increment)
        elif sessions_at >= 3:
            status = "stall"
            suggested = current_weight  # Consider deload or change
        else:
            status = "hold"
            suggested = current_weight

        results[lift_key] = {
            "current_weight": current_weight,
            "prescribed_sets": p_sets,
            "prescribed_reps": p_reps,
            "total_reps_done": total_reps_done,
            "target_reps": target_reps,
            "completed": completed,
            "sessions_at_weight": sessions_at,
            "suggested_weight": suggested,
            "status": status,
            "e1rm": latest["e1rm"],
            "last_date": latest_date,
        }

    return results


def weekly_volume_candito(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly volume breakdown."""
    if df.empty:
        return pd.DataFrame()
    df2 = df.copy()
    df2["week"] = df2["date"].dt.isocalendar().week.astype(int)
    df2["year"] = df2["date"].dt.year
    weekly = df2.groupby(["year", "week"]).agg(
        volume_kg=("volume_kg", "sum"),
        sessions=("hevy_id", "nunique"),
        sets=("n_sets", "sum"),
    ).reset_index()
    return weekly


def muscle_volume_candito(df: pd.DataFrame) -> pd.DataFrame:
    """Volume per muscle group."""
    if df.empty:
        return pd.DataFrame()
    return df.groupby("muscle_group").agg(
        volume_kg=("volume_kg", "sum"),
        sets=("n_sets", "sum"),
        exercises=("exercise", "nunique"),
    ).sort_values("volume_kg", ascending=False).reset_index()


def strength_level_candito(df: pd.DataFrame) -> list[dict]:
    """Calculate strength level for each main lift vs bodyweight standards."""
    if df.empty:
        return []
    bw = BODYWEIGHT
    results = []
    for lift_key, standards in STRENGTH_STANDARDS_CANDITO.items():
        tid = MAIN_LIFT_TIDS.get(lift_key)
        if not tid:
            continue
        lift_df = df[df["exercise_template_id"] == tid]
        if lift_df.empty:
            continue
        best_e1rm = lift_df["e1rm"].max()
        ratio = best_e1rm / bw if bw > 0 else 0

        level = "Principiante"
        for lvl, threshold in [
            ("Elite", standards.get("elite", 99)),
            ("Avanzado", standards.get("advanced", 99)),
            ("Intermedio", standards.get("intermediate", 99)),
            ("Principiante", standards.get("beginner", 0)),
        ]:
            if ratio >= threshold:
                level = lvl
                break

        # Progress to next level
        current_idx = ["Principiante", "Intermedio", "Avanzado", "Elite"].index(level)
        next_level = ["Intermedio", "Avanzado", "Elite", None][current_idx]
        next_threshold = standards.get(
            {"Intermedio": "intermediate", "Avanzado": "advanced", "Elite": "elite"}.get(next_level, ""),
            None
        )
        pct_to_next = None
        if next_threshold:
            current_threshold = standards.get(
                {"Principiante": "beginner", "Intermedio": "intermediate", "Avanzado": "advanced"}.get(level, "beginner"),
                0
            )
            if next_threshold > current_threshold:
                pct_to_next = min(100, int((ratio - current_threshold) / (next_threshold - current_threshold) * 100))

        results.append({
            "lift_key": lift_key,
            "exercise": EXERCISE_DB_CANDITO.get(tid, {}).get("name", lift_key),
            "e1rm": best_e1rm,
            "ratio": round(ratio, 2),
            "level": level,
            "next_level": next_level,
            "pct_to_next": pct_to_next,
        })
    return results


# ══════════════════════════════════════════════════════════════════════
# HEVY ROUTINE AUTO-UPDATE
# ══════════════════════════════════════════════════════════════════════

def build_routine_exercises(day_num: int, progression: dict) -> list[dict]:
    """Build Hevy routine exercise payload for a given day with updated weights."""
    exercises = []

    for tid, ex_cfg in EXERCISE_DB_CANDITO.items():
        day_val = ex_cfg.get("day")
        # Handle multi-day exercises (e.g. shrugs on days 1 and 3)
        if isinstance(day_val, list):
            if day_num not in day_val:
                continue
        elif day_val != day_num:
            continue

        lift_key = ex_cfg.get("lift_key", "")
        prescribed = ex_cfg.get("prescribed", {})
        p_sets = prescribed.get("sets", 3)
        p_reps = prescribed.get("reps", 6)

        # Get weight: from progression analysis if available, else starting weight
        prog_info = progression.get(lift_key, {})
        weight = prog_info.get("suggested_weight") or STARTING_WEIGHTS.get(lift_key, 0)

        # Bodyweight exercises (pull-ups)
        is_bw = lift_key in ("pullup",)

        sets = []
        for _ in range(p_sets):
            s = {"type": "normal", "reps": p_reps}
            if not is_bw:
                s["weight_kg"] = weight
            sets.append(s)

        rest = 180 if ex_cfg.get("role") == "main" else (120 if ex_cfg.get("is_compound") else 60)

        exercises.append({
            "exercise_template_id": tid,
            "rest_seconds": rest,
            "sets": sets,
        })

    return exercises


def update_hevy_routines_candito(df: pd.DataFrame) -> dict:
    """Update all 4 Candito routines in Hevy with progression weights."""
    api_key = os.environ.get("HEVY_API_KEY", "")
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    progression = analyze_progression(df)
    results = {}

    for day_num, routine_id in DAY_ROUTINE_MAP_CANDITO.items():
        day_cfg = DAY_CONFIG_CANDITO.get(day_num, {})
        exercises = build_routine_exercises(day_num, progression)

        if not exercises:
            results[day_num] = {"status": "skipped", "reason": "no exercises"}
            continue

        payload = {
            "routine": {
                "title": f"Candito D{day_num} - {day_cfg.get('name', '?')}",
                "exercises": exercises,
            }
        }

        time.sleep(0.5)
        try:
            r = requests.put(
                f"{BASE_URL}/routines/{routine_id}",
                headers=headers, json=payload,
            )
            if r.ok:
                # Summarize main lift weights
                main_weights = {}
                for ex in exercises:
                    tid = ex["exercise_template_id"]
                    lk = TID_TO_LIFT.get(tid)
                    if lk and ex.get("sets"):
                        w = ex["sets"][0].get("weight_kg", 0)
                        if w:
                            main_weights[lk] = w

                results[day_num] = {
                    "status": "updated",
                    "day": day_cfg.get("name", "?"),
                    "weights": main_weights,
                    "progression": {
                        lk: progression.get(lk, {}).get("status", "new")
                        for lk in main_weights
                    },
                }
            else:
                results[day_num] = {"status": "error", "code": r.status_code, "msg": r.text[:200]}
        except Exception as e:
            results[day_num] = {"status": "error", "msg": str(e)}

    return results


def next_session_plan_candito(df: pd.DataFrame) -> dict:
    """Determine what's next and with what weights."""
    progression = analyze_progression(df)

    if df.empty:
        next_day = 1
    else:
        last_day = df.sort_values("date", ascending=False).iloc[0]["day_num"]
        next_day = (last_day % 4) + 1 if last_day else 1

    day_cfg = DAY_CONFIG_CANDITO.get(next_day, {})
    exercises = []

    for tid, ex_cfg in EXERCISE_DB_CANDITO.items():
        day_val = ex_cfg.get("day")
        if isinstance(day_val, list):
            if next_day not in day_val:
                continue
        elif day_val != next_day:
            continue

        lk = ex_cfg.get("lift_key", "")
        prog = progression.get(lk, {})
        weight = prog.get("suggested_weight") or STARTING_WEIGHTS.get(lk, 0)
        prescribed = ex_cfg.get("prescribed", {})
        status = prog.get("status", "new")

        exercises.append({
            "name": ex_cfg.get("name", "?"),
            "lift_key": lk,
            "role": ex_cfg.get("role", "?"),
            "weight": weight,
            "sets": prescribed.get("sets", 0),
            "reps": prescribed.get("reps", 0),
            "status": status,
        })

    return {
        "day_num": next_day,
        "day_name": day_cfg.get("name", "?"),
        "day_type": day_cfg.get("type", "?"),
        "emoji": day_cfg.get("emoji", ""),
        "exercises": exercises,
    }
