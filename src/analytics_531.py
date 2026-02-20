"""
531 BBB Analytics — Pandas Analytics Engine

Tracks Wendler's 5/3/1 Boring But Big program:
- Cycle/week detection and compliance
- AMRAP performance and e1RM estimation
- BBB supplemental volume tracking
- Accessory volume by muscle group
- Training Max progression over cycles
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.config_531 import (
    TRAINING_MAX,
    TM_INCREMENT,
    CYCLE_WEEKS,
    BBB_PCT_PROGRESSION,
    DAY_CONFIG_531,
    MAIN_LIFT_TIDS,
    TID_TO_LIFT,
    EXERCISE_DB_531,
    BODYWEIGHT,
    PROGRAM_START_531,
    STRENGTH_STANDARDS_531,
    BBB_FOLDER_ID,
    BBB_ROUTINE_IDS,
    EXCEPTION_WORKOUT_IDS,
    round_to_plate,
)


# ═════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═════════════════════════════════════════════════════════════════════

def is_bbb_workout(workout: dict) -> bool:
    """Check if a workout belongs to the BBB program."""
    # Method 1: routine_id matches a known BBB routine
    rid = workout.get("routine_id")
    if rid and rid in BBB_ROUTINE_IDS:
        return True
    # Method 2: workout ID is in manual exception list
    if workout.get("id") in EXCEPTION_WORKOUT_IDS:
        return True
    return False


def fetch_bbb_workouts() -> list[dict]:
    """Fetch all BBB workouts from Hevy API."""
    from src.hevy_client import fetch_all_workouts
    all_wk = fetch_all_workouts()
    return [w for w in all_wk if is_bbb_workout(w)]


def classify_sets(exercise: dict, all_exercises: list[dict]) -> str:
    """
    Classify an exercise within a BBB workout as:
    - 'main_531': the main lift with 531 rep scheme
    - 'bbb_supplemental': the 5x10 BBB sets (same lift as main)
    - 'accessory': everything else

    Heuristic: if the exercise's template_id matches a main lift AND
    it appears twice in the workout, the instance with fewer total sets
    at higher weight is the 531 work, and the one with 5x10 is BBB.
    """
    tid = exercise.get("exercise_template_id", "")
    if tid in TID_TO_LIFT:
        return "main"  # Will be split into 531 vs BBB later at set level
    return "accessory"


def parse_workout_sets(workout: dict) -> list[dict]:
    """
    Parse a single BBB workout into classified set rows.

    For main lifts, splits sets into:
    - warmup (lighter, before working sets)
    - working_531 (the 3 main 531 sets)
    - bbb (the 5x10 supplemental)
    - accessory (everything else)
    """
    rows = []
    date = workout["start_time"][:10]
    hevy_id = workout["id"]
    title = workout.get("title", "")

    for ex in workout.get("exercises", []):
        tid = ex.get("exercise_template_id", "")
        name = ex.get("title", "")
        sets = ex.get("sets", [])

        if tid in TID_TO_LIFT:
            # This is a main lift — classify each set
            lift = TID_TO_LIFT[tid]
            classified = _classify_main_lift_sets(sets, lift)
            for s_info in classified:
                rows.append({
                    "date": pd.Timestamp(date),
                    "hevy_id": hevy_id,
                    "workout_title": title,
                    "exercise": name,
                    "exercise_template_id": tid,
                    "lift": lift,
                    "set_type": s_info["type"],  # warmup / working_531 / amrap / bbb
                    "weight_kg": s_info["weight"],
                    "reps": s_info["reps"],
                    "set_number": s_info["set_num"],
                    "is_main_lift": True,
                })
        else:
            # Accessory
            for i, s in enumerate(sets, 1):
                w = s.get("weight_kg", 0) or 0
                r = s.get("reps", 0) or 0
                if r > 0:
                    rows.append({
                        "date": pd.Timestamp(date),
                        "hevy_id": hevy_id,
                        "workout_title": title,
                        "exercise": name,
                        "exercise_template_id": tid,
                        "lift": None,
                        "set_type": "accessory",
                        "weight_kg": float(w),
                        "reps": int(r),
                        "set_number": i,
                        "is_main_lift": False,
                    })

    return rows


def _classify_main_lift_sets(sets: list[dict], lift: str) -> list[dict]:
    """
    Classify individual sets of a main lift exercise.

    Strategy: 531 working sets are the heaviest cluster (ascending weight),
    BBB sets are the repeated-weight cluster (typically 5x10).
    Everything lighter before the working sets is warmup.

    Returns list of {type, weight, reps, set_num}.
    """
    parsed = []
    for i, s in enumerate(sets):
        w = float(s.get("weight_kg", 0) or 0)
        r = int(s.get("reps", 0) or 0)
        if r > 0:
            parsed.append({"weight": w, "reps": r, "idx": i})

    if not parsed:
        return []

    # Find the peak weight (should be the AMRAP/top set)
    max_weight = max(p["weight"] for p in parsed)

    # Identify BBB cluster: sets with same weight and high reps (8+), appearing after peak
    # Find sets after the peak that have repeated weight
    peak_idx = max(p["idx"] for p in parsed if p["weight"] == max_weight)

    # Separate into phases
    result = []
    ascending_weights = []
    bbb_weight = None

    # After the peak, look for BBB pattern (repeated weight, high reps)
    post_peak = [p for p in parsed if p["idx"] > peak_idx]
    if post_peak:
        # BBB sets: all post-peak sets with the same weight
        weight_counts = {}
        for p in post_peak:
            weight_counts[p["weight"]] = weight_counts.get(p["weight"], 0) + 1
        # The most common weight in post-peak is likely BBB
        if weight_counts:
            bbb_weight = max(weight_counts, key=weight_counts.get)

    # Now classify each set
    working_531_found = False
    ascending_phase = True
    prev_weight = 0
    set_num = 0

    for p in parsed:
        set_num += 1
        w, r, idx = p["weight"], p["reps"], p["idx"]

        if idx > peak_idx and bbb_weight is not None and w == bbb_weight:
            # BBB supplemental
            result.append({"type": "bbb", "weight": w, "reps": r, "set_num": set_num})
        elif idx <= peak_idx:
            # Pre-peak: could be warmup or working 531
            # Working 531 sets: the last 3 sets before/including peak in ascending order
            # We'll mark these after collecting all
            result.append({"type": "_pre_peak", "weight": w, "reps": r, "set_num": set_num, "idx": idx})
        else:
            # Post-peak, not BBB weight — could be extra BBB or odd set
            result.append({"type": "bbb", "weight": w, "reps": r, "set_num": set_num})

    # Now classify pre-peak sets: last 3 ascending are working_531, rest are warmup
    pre_peak = [r for r in result if r.get("type") == "_pre_peak"]
    if len(pre_peak) >= 3:
        # Last 3 pre-peak sets are working 531
        for i, entry in enumerate(pre_peak):
            if i >= len(pre_peak) - 3:
                # Check if this is the very last one (AMRAP)
                if i == len(pre_peak) - 1:
                    entry["type"] = "amrap"
                else:
                    entry["type"] = "working_531"
            else:
                entry["type"] = "warmup"
    elif len(pre_peak) > 0:
        # Less than 3 pre-peak sets — all are working 531
        for i, entry in enumerate(pre_peak):
            if i == len(pre_peak) - 1:
                entry["type"] = "amrap"
            else:
                entry["type"] = "working_531"

    # Clean up temp keys
    for r in result:
        r.pop("idx", None)
        if r["type"] == "_pre_peak":
            r["type"] = "warmup"

    return result


# ═════════════════════════════════════════════════════════════════════
# DATAFRAME CONSTRUCTION
# ═════════════════════════════════════════════════════════════════════

def workouts_to_dataframe_531(workouts: list[dict]) -> pd.DataFrame:
    """Convert raw BBB workouts to a flat DataFrame with set-level classification."""
    all_rows = []
    for w in workouts:
        rows = parse_workout_sets(w)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    df = df.sort_values(["date", "set_number"]).reset_index(drop=True)

    # Add volume
    df["volume_kg"] = df["weight_kg"] * df["reps"]

    # Add e1RM (Epley) for main lift sets
    df["e1rm"] = 0.0
    mask = df["weight_kg"] > 0
    single = mask & (df["reps"] == 1)
    multi = mask & (df["reps"] > 1)
    df.loc[single, "e1rm"] = df.loc[single, "weight_kg"]
    df.loc[multi, "e1rm"] = (
        df.loc[multi, "weight_kg"] * (1 + df.loc[multi, "reps"] / 30)
    ).round(1)

    # Add muscle group
    df["muscle_group"] = df["exercise_template_id"].apply(
        lambda tid: EXERCISE_DB_531.get(tid, {}).get("muscle_group", "Otro")
    )

    return df


def add_cycle_info(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add cycle_num and cycle_week columns.

    Cycle detection: each unique session date is a training day.
    Every 4 training days = 1 cycle week.
    Every 4 cycle weeks (or 3 working + 1 deload) = 1 cycle.

    Simplified: since BBB has 4 days/week, we assign based on session order.
    """
    if df.empty:
        return df

    df = df.copy()

    # Get unique training dates in order
    dates = sorted(df["date"].unique())

    # Each date = one training day. 4 days = 1 week. 4 weeks = 1 cycle.
    # But Juan might not train exactly 4 days/week, so we go by session count.
    date_to_session = {d: i + 1 for i, d in enumerate(dates)}

    df["session_num"] = df["date"].map(date_to_session)

    # Cycle week: which week within the cycle (1-4)
    # Every 4 sessions = 1 cycle week iteration
    # Week 1: sessions 1-4, Week 2: sessions 5-8, etc.
    df["cycle_week"] = ((df["session_num"] - 1) // 4) + 1

    # Cycle number: every 4 weeks (16 sessions) = 1 cycle
    # But more practically: every 3 weeks (12 sessions) + optional deload
    # For now, simple: every 12 sessions = 1 cycle (3 working weeks)
    df["cycle_num"] = ((df["session_num"] - 1) // 12) + 1

    # Also assign a within-cycle week (1, 2, 3, or 4=deload)
    sessions_in_cycle = ((df["session_num"] - 1) % 12)
    df["week_in_cycle"] = (sessions_in_cycle // 4) + 1

    return df


# ═════════════════════════════════════════════════════════════════════
# ANALYTICS FUNCTIONS
# ═════════════════════════════════════════════════════════════════════

def global_summary_531(df: pd.DataFrame) -> dict:
    """Overall program summary."""
    if df.empty:
        return {}

    sessions = df["hevy_id"].nunique()
    dates = df["date"].unique()
    total_vol = df["volume_kg"].sum()
    total_sets = len(df)
    total_reps = df["reps"].sum()

    # Main lift stats
    main = df[df["is_main_lift"]]
    amraps = df[df["set_type"] == "amrap"]

    return {
        "total_sessions": sessions,
        "training_days": len(dates),
        "first_session": df["date"].min(),
        "last_session": df["date"].max(),
        "total_volume_kg": int(total_vol),
        "total_sets": total_sets,
        "total_reps": int(total_reps),
        "amrap_count": len(amraps),
        "avg_amrap_reps": round(amraps["reps"].mean(), 1) if not amraps.empty else 0,
    }


def amrap_tracking(df: pd.DataFrame) -> pd.DataFrame:
    """
    Track all AMRAP sets with e1RM, expected vs actual reps.

    This is THE key metric for 531 — the AMRAP set tells you if your TM is right.
    """
    amraps = df[df["set_type"] == "amrap"].copy()
    if amraps.empty:
        return pd.DataFrame()

    # Add expected minimum reps based on cycle week
    def _min_reps(row):
        wic = row.get("week_in_cycle", 1)
        week_cfg = CYCLE_WEEKS.get(wic, {})
        sets_cfg = week_cfg.get("sets", [])
        if sets_cfg:
            last = sets_cfg[-1]
            reps_str = str(last.get("reps", "5+"))
            return int(reps_str.replace("+", ""))
        return 5

    amraps["min_reps"] = amraps.apply(_min_reps, axis=1)
    amraps["reps_over_min"] = amraps["reps"] - amraps["min_reps"]
    amraps["pct_of_tm"] = amraps.apply(
        lambda r: round(r["weight_kg"] / TRAINING_MAX.get(r["lift"], 1) * 100, 1)
        if r["lift"] and TRAINING_MAX.get(r["lift"])
        else None,
        axis=1,
    )

    return amraps[["date", "lift", "weight_kg", "reps", "e1rm",
                    "min_reps", "reps_over_min", "pct_of_tm"]].reset_index(drop=True)


def bbb_compliance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Track BBB supplemental work compliance.

    Shows: date, lift, weight used, sets done, avg reps, target (5x10),
    % of TM used, compliance status.
    """
    bbb = df[df["set_type"] == "bbb"].copy()
    if bbb.empty:
        return pd.DataFrame()

    grouped = bbb.groupby(["date", "hevy_id", "lift"]).agg(
        weight_kg=("weight_kg", "first"),  # Should be constant
        n_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        avg_reps=("reps", "mean"),
        min_reps=("reps", "min"),
    ).reset_index()

    grouped["avg_reps"] = grouped["avg_reps"].round(1)
    grouped["target_sets"] = 5
    grouped["target_reps"] = 10
    grouped["sets_ok"] = grouped["n_sets"] >= 5
    grouped["reps_ok"] = grouped["avg_reps"] >= 9  # Allow slight miss

    # % of TM
    grouped["pct_of_tm"] = grouped.apply(
        lambda r: round(r["weight_kg"] / TRAINING_MAX.get(r["lift"], 1) * 100, 1)
        if r["lift"] and TRAINING_MAX.get(r["lift"])
        else None,
        axis=1,
    )

    return grouped


def accessory_volume(df: pd.DataFrame) -> pd.DataFrame:
    """Accessory work volume by muscle group and date."""
    acc = df[df["set_type"] == "accessory"].copy()
    if acc.empty:
        return pd.DataFrame()

    grouped = acc.groupby(["date", "muscle_group"]).agg(
        n_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        total_volume=("volume_kg", "sum"),
    ).reset_index()

    return grouped


def accessory_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Total accessory volume by muscle group across all sessions."""
    acc = df[df["set_type"] == "accessory"].copy()
    if acc.empty:
        return pd.DataFrame()

    grouped = acc.groupby(["muscle_group"]).agg(
        exercises=("exercise", "nunique"),
        total_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        total_volume=("volume_kg", "sum"),
    ).reset_index().sort_values("total_volume", ascending=False)

    return grouped


def tm_progression(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate Training Max progression over time based on AMRAP performance.

    Uses Epley e1RM from AMRAP sets to estimate true 1RM,
    then TM = 90% of estimated 1RM.
    """
    amraps = df[df["set_type"] == "amrap"].copy()
    if amraps.empty:
        return pd.DataFrame()

    # Group by cycle and lift, take the AMRAP from each
    result = amraps.groupby(["cycle_num", "lift"]).agg(
        date=("date", "last"),
        amrap_weight=("weight_kg", "last"),
        amrap_reps=("reps", "last"),
        e1rm=("e1rm", "max"),
    ).reset_index()

    result["estimated_tm"] = (result["e1rm"] * 0.90).apply(round_to_plate)
    result["current_tm"] = result["lift"].map(
        lambda l: TRAINING_MAX.get(l, 0) or 0
    )

    return result


def session_summary_531(df: pd.DataFrame) -> pd.DataFrame:
    """Summary per session: main lift + BBB + accessories."""
    if df.empty:
        return pd.DataFrame()

    summaries = []
    for hid, grp in df.groupby("hevy_id"):
        date = grp["date"].iloc[0]
        title = grp["workout_title"].iloc[0]

        main = grp[grp["is_main_lift"]]
        acc = grp[~grp["is_main_lift"]]

        lift = main["lift"].iloc[0] if not main.empty else "?"
        amrap = grp[grp["set_type"] == "amrap"]
        bbb = grp[grp["set_type"] == "bbb"]

        summaries.append({
            "date": date,
            "hevy_id": hid,
            "title": title,
            "main_lift": lift,
            "amrap_weight": amrap["weight_kg"].iloc[0] if not amrap.empty else 0,
            "amrap_reps": amrap["reps"].iloc[0] if not amrap.empty else 0,
            "amrap_e1rm": amrap["e1rm"].iloc[0] if not amrap.empty else 0,
            "bbb_sets": len(bbb),
            "bbb_weight": bbb["weight_kg"].iloc[0] if not bbb.empty else 0,
            "bbb_avg_reps": round(bbb["reps"].mean(), 1) if not bbb.empty else 0,
            "accessory_sets": len(acc),
            "accessory_volume": int(acc["volume_kg"].sum()),
            "total_volume": int(grp["volume_kg"].sum()),
            "total_sets": len(grp),
        })

    return pd.DataFrame(summaries).sort_values("date").reset_index(drop=True)


def pr_table_531(df: pd.DataFrame) -> pd.DataFrame:
    """PR table based on e1RM per exercise."""
    if df.empty:
        return pd.DataFrame()

    # Only consider sets with actual weight
    valid = df[df["weight_kg"] > 0].copy()

    prs = valid.groupby("exercise").agg(
        exercise_template_id=("exercise_template_id", "first"),
        max_weight=("weight_kg", "max"),
        max_e1rm=("e1rm", "max"),
        best_date=("date", "last"),
    ).reset_index().sort_values("max_e1rm", ascending=False)

    return prs


def lift_progression(df: pd.DataFrame) -> pd.DataFrame:
    """Track e1RM progression per main lift over time (from AMRAP sets)."""
    amraps = df[df["set_type"] == "amrap"].copy()
    if amraps.empty:
        return pd.DataFrame()

    return amraps[["date", "lift", "weight_kg", "reps", "e1rm"]].sort_values("date")


def strength_level_531(df: pd.DataFrame) -> dict:
    """
    Calculate current strength level for each main lift.

    Returns dict: {lift: {e1rm, ratio_bw, level}}.
    """
    result = {}
    for lift_name, standards in STRENGTH_STANDARDS_531.items():
        amraps = df[(df["set_type"] == "amrap") & (df["lift"] == lift_name)]
        if amraps.empty:
            result[lift_name] = {"e1rm": None, "ratio_bw": None, "level": "Sin datos"}
            continue

        best_e1rm = amraps["e1rm"].max()
        ratio = best_e1rm / BODYWEIGHT

        if ratio >= standards["elite"]:
            level = "Elite"
        elif ratio >= standards["advanced"]:
            level = "Avanzado"
        elif ratio >= standards["intermediate"]:
            level = "Intermedio"
        elif ratio >= standards["beginner"]:
            level = "Principiante"
        else:
            level = "Novato"

        result[lift_name] = {
            "e1rm": round(best_e1rm, 1),
            "ratio_bw": round(ratio, 2),
            "level": level,
        }

    return result


def weekly_volume_531(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly volume breakdown by set type."""
    if df.empty:
        return pd.DataFrame()

    df_c = df.copy()
    # ISO week
    df_c["week_start"] = df_c["date"].dt.to_period("W").apply(lambda p: p.start_time)

    grouped = df_c.groupby(["week_start", "set_type"]).agg(
        total_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        total_volume=("volume_kg", "sum"),
    ).reset_index()

    return grouped


def muscle_volume_531(df: pd.DataFrame) -> pd.DataFrame:
    """Volume distribution by muscle group."""
    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby("muscle_group").agg(
        total_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        total_volume=("volume_kg", "sum"),
    ).reset_index().sort_values("total_volume", ascending=False)

    total = grouped["total_volume"].sum()
    grouped["pct"] = (grouped["total_volume"] / total * 100).round(1) if total > 0 else 0

    return grouped
