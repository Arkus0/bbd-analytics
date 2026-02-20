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


# ═════════════════════════════════════════════════════════════════════
# NEXT SESSION PLANNER
# ═════════════════════════════════════════════════════════════════════

BAR_WEIGHT = 20.0
# Juan's actual plate inventory: (weight_kg, total_discs)
# Per side = total_discs / 2
PLATE_INVENTORY = [
    (20, 4),   # 2 per side
    (10, 2),   # 1 per side
    (6, 4),    # 2 per side
    (4, 4),    # 2 per side
    (2, 4),    # 2 per side
    (1, 4),    # 2 per side
]
PLATES_PER_SIDE = {w: total // 2 for w, total in PLATE_INVENTORY}
AVAILABLE_PLATES = sorted(PLATES_PER_SIDE.keys(), reverse=True)


def plate_breakdown(total_weight: float) -> list[float]:
    """
    Calculate plates needed per side for a given total weight.
    Respects actual plate inventory (quantity per side).
    Returns list of plate weights for ONE side.
    """
    per_side = (total_weight - BAR_WEIGHT) / 2
    if per_side <= 0:
        return []
    plates = []
    remaining = per_side
    for plate in AVAILABLE_PLATES:
        max_count = PLATES_PER_SIDE[plate]
        used = 0
        while remaining >= plate - 0.01 and used < max_count:
            plates.append(plate)
            remaining -= plate
            used += 1
    return plates


def round_to_available(weight: float) -> float:
    """
    Round weight to nearest achievable weight with Juan's plates.
    Minimum increment = 2 kg (1 kg per side).
    """
    # Achievable = bar + 2 * (sum of some subset of per-side plates)
    # Simplification: round to nearest 2 kg
    return round(weight / 2) * 2


def format_plates(plates: list[float]) -> str:
    """Format plate list as readable string: '20 + 5 + 2.5'"""
    if not plates:
        return "barra vacía"
    parts = []
    for p in plates:
        display = str(int(p)) if p == int(p) else str(p)
        parts.append(display)
    return " + ".join(parts)


def next_session_plan(df: pd.DataFrame) -> dict:
    """
    Figure out what's next and return full workout plan.

    Returns {
        day_num, day_name, lift, lift_label, cycle_num, week_in_cycle, week_name,
        tm, working_sets, bbb, warmup
    }
    """
    DAY_ORDER = [1, 2, 3, 4]

    if df.empty:
        next_day = 1
        total_sessions = 0
    else:
        sessions = (
            df.drop_duplicates("hevy_id")[["hevy_id", "date"]]
            .sort_values("date")
        )
        total_sessions = len(sessions)
        last_day_idx = (total_sessions - 1) % 4
        next_day_idx = (last_day_idx + 1) % 4
        next_day = DAY_ORDER[next_day_idx]

    # Every 4 sessions = 1 week, every 3 weeks = 1 cycle
    completed_weeks = total_sessions // 4
    week_in_cycle = (completed_weeks % 3) + 1
    cycle_num = (completed_weeks // 3) + 1

    day_cfg = DAY_CONFIG_531.get(next_day, {})
    lift = day_cfg.get("main_lift", "?")
    week_cfg = CYCLE_WEEKS.get(week_in_cycle, CYCLE_WEEKS[1])

    tm = TRAINING_MAX.get(lift)

    plan = {
        "day_num": next_day,
        "day_name": day_cfg.get("name", f"Día {next_day}"),
        "focus": day_cfg.get("focus", ""),
        "lift": lift,
        "lift_label": {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Squat"}.get(lift, lift),
        "cycle_num": cycle_num,
        "week_in_cycle": week_in_cycle,
        "week_name": week_cfg["name"],
        "tm": tm,
        "working_sets": [],
        "bbb": None,
        "warmup": [],
    }

    if tm is None:
        return plan

    # ── Warmup sets ──
    warmup_pcts = [0.40, 0.50, 0.60]
    for pct in warmup_pcts:
        w = round_to_plate(tm * pct)
        plates = plate_breakdown(w)
        plan["warmup"].append({
            "weight": w,
            "reps": 5,
            "pct": pct,
            "plates": plates,
            "plates_str": format_plates(plates),
        })

    # ── Working 531 sets ──
    for s in week_cfg["sets"]:
        w = round_to_plate(tm * s["pct"])
        plates = plate_breakdown(w)
        reps = s["reps"]
        plan["working_sets"].append({
            "weight": w,
            "reps": reps,
            "pct": s["pct"],
            "plates": plates,
            "plates_str": format_plates(plates),
            "is_amrap": isinstance(reps, str) and "+" in str(reps),
        })

    # ── BBB supplemental ──
    bbb_pct = BBB_PCT_PROGRESSION.get(cycle_num, 0.50)
    bbb_w = round_to_plate(tm * bbb_pct)
    bbb_plates = plate_breakdown(bbb_w)
    plan["bbb"] = {
        "weight": bbb_w,
        "sets": 5,
        "reps": 10,
        "pct_tm": bbb_pct,
        "plates": bbb_plates,
        "plates_str": format_plates(bbb_plates),
    }

    return plan


def full_week_plan(df: pd.DataFrame) -> list[dict]:
    """
    Return the plan for all 4 days of the current cycle week.
    Useful for weekly overview.
    """
    if df.empty:
        total_sessions = 0
    else:
        total_sessions = df["hevy_id"].nunique()

    completed_weeks = total_sessions // 4
    week_in_cycle = (completed_weeks % 3) + 1
    cycle_num = (completed_weeks // 3) + 1
    week_cfg = CYCLE_WEEKS.get(week_in_cycle, CYCLE_WEEKS[1])

    plans = []
    for day_num in [1, 2, 3, 4]:
        day_cfg = DAY_CONFIG_531.get(day_num, {})
        lift = day_cfg.get("main_lift", "?")
        tm = TRAINING_MAX.get(lift)
        label = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Squat"}.get(lift, lift)

        day_plan = {
            "day_num": day_num,
            "lift": lift,
            "lift_label": label,
            "focus": day_cfg.get("focus", ""),
            "tm": tm,
            "sets": [],
        }

        if tm:
            for s in week_cfg["sets"]:
                w = round_to_plate(tm * s["pct"])
                plates = plate_breakdown(w)
                day_plan["sets"].append({
                    "weight": w,
                    "reps": s["reps"],
                    "pct": s["pct"],
                    "plates_str": format_plates(plates),
                    "is_amrap": isinstance(s["reps"], str) and "+" in str(s["reps"]),
                })

            bbb_pct = BBB_PCT_PROGRESSION.get(cycle_num, 0.50)
            bbb_w = round_to_plate(tm * bbb_pct)
            day_plan["bbb_weight"] = bbb_w
            day_plan["bbb_plates"] = format_plates(plate_breakdown(bbb_w))

        plans.append(day_plan)

    return plans
