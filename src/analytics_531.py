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
    DAY_ROUTINE_MAP,
    DAY_ACCESSORIES,
    round_to_plate,
    get_cycle_position,
    get_effective_tm,
    expected_weights,
    MACRO_CYCLE_LENGTH,
    WORKING_BLOCK_LENGTH,
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
    # Method 3: title starts with "BBB" (fallback for routine_id mismatches)
    title = workout.get("title", "")
    if title.upper().startswith("BBB"):
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
    Classify individual sets of a main lift exercise using TM-based detection.

    Uses known Training Max to identify working sets by matching expected
    percentages (65/75/85, 70/80/90, or 75/85/95 of TM), then classifies:

    - warmup: lighter sets before the working sets
    - working_531: the 3 prescribed 531 sets (ascending weight)
    - amrap: the last working set (heaviest of the 3, often high reps)
    - joker: sets HEAVIER than the top working weight, low reps (1-5)
    - bbb: 5×10 supplemental at ~50% TM (consistent low weight, high reps)
    - fsl: First Set Last — weight ≈ first working set, moderate reps (5-8)
    - bbb_amrap: last BBB set if reps significantly exceed the others

    Returns list of {type, weight, reps, set_num}.
    """
    parsed = []
    for i, s in enumerate(sets):
        w = float(s.get("weight_kg", 0) or 0)
        r = int(s.get("reps", 0) or 0)
        stype = s.get("type", "normal")
        if r > 0:
            parsed.append({"weight": w, "reps": r, "idx": i, "hevy_type": stype})

    if not parsed:
        return []

    tm = TRAINING_MAX.get(lift)
    if not tm:
        # Fallback: old heuristic if no TM
        return _classify_main_lift_sets_fallback(parsed)

    # ── Step 1: Detect which week type by matching expected weights ──
    best_week = None
    best_score = -1
    working_indices = None

    for week_num in [1, 2, 3]:
        exp = expected_weights(lift, week_num, tm_override=tm)
        if not exp:
            continue

        exp_weights = [e["weight"] for e in exp]
        # Find 3 consecutive ascending sets matching these weights (±2kg tolerance)
        for start in range(len(parsed) - 2):
            candidates = parsed[start:start + 3]
            if candidates[0]["hevy_type"] == "warmup":
                continue
            score = 0
            for cand, ew in zip(candidates, exp_weights):
                if abs(cand["weight"] - ew) <= 2:
                    score += 1
            if score > best_score:
                best_score = score
                best_week = week_num
                working_indices = set(p["idx"] for p in candidates)

    # If no good match (score < 2), try looser matching
    if best_score < 2:
        # Fallback: look for 3 ascending normal-type sets in the middle range
        return _classify_main_lift_sets_fallback(parsed)

    # ── Step 2: Identify working set weights ──
    working_sets = [p for p in parsed if p["idx"] in working_indices]
    top_working_weight = max(w["weight"] for w in working_sets)
    first_working_weight = min(w["weight"] for w in working_sets)
    top_working_idx = max(w["idx"] for w in working_sets)

    # ── Step 3: Classify all sets ──
    result = []
    supplemental_sets = []
    set_num = 0

    for p in parsed:
        set_num += 1
        w, r, idx = p["weight"], p["reps"], p["idx"]

        if idx in working_indices:
            # Is this the top (AMRAP) set?
            if idx == top_working_idx:
                result.append({"type": "amrap", "weight": w, "reps": r, "set_num": set_num})
            else:
                result.append({"type": "working_531", "weight": w, "reps": r, "set_num": set_num})

        elif idx < min(working_indices):
            # Before working sets → warmup
            result.append({"type": "warmup", "weight": w, "reps": r, "set_num": set_num})

        elif idx > top_working_idx and w > top_working_weight:
            # After working sets AND heavier → joker
            result.append({"type": "joker", "weight": w, "reps": r, "set_num": set_num})

        elif idx > top_working_idx:
            # After working/joker sets, lower weight → supplemental (classify later)
            supplemental_sets.append({"weight": w, "reps": r, "set_num": set_num, "idx": idx})

        else:
            # Edge case
            result.append({"type": "warmup", "weight": w, "reps": r, "set_num": set_num})

    # ── Step 4: Classify supplemental sets (BBB vs FSL) ──
    if supplemental_sets:
        supp_weights = [s["weight"] for s in supplemental_sets]
        primary_weight = max(set(supp_weights), key=supp_weights.count)  # most common weight

        # FSL: weight matches first working set (±2kg), reps typically 5-8
        is_fsl = abs(primary_weight - first_working_weight) <= 2
        avg_reps_supp = sum(s["reps"] for s in supplemental_sets) / len(supplemental_sets)

        if is_fsl and avg_reps_supp <= 8:
            supp_type = "fsl"
        else:
            supp_type = "bbb"

        # Check if last supplemental set is an AMRAP (reps >> average of others)
        if len(supplemental_sets) >= 3:
            others = supplemental_sets[:-1]
            last = supplemental_sets[-1]
            avg_others = sum(s["reps"] for s in others) / len(others)
            if last["reps"] > avg_others * 1.5 and last["reps"] > 12:
                # Last set is a supplemental AMRAP
                for s in supplemental_sets[:-1]:
                    result.append({"type": supp_type, "weight": s["weight"], "reps": s["reps"], "set_num": s["set_num"]})
                result.append({"type": f"{supp_type}_amrap", "weight": last["weight"], "reps": last["reps"], "set_num": last["set_num"]})
            else:
                for s in supplemental_sets:
                    result.append({"type": supp_type, "weight": s["weight"], "reps": s["reps"], "set_num": s["set_num"]})
        else:
            for s in supplemental_sets:
                result.append({"type": supp_type, "weight": s["weight"], "reps": s["reps"], "set_num": s["set_num"]})

    # Sort by set_num
    result.sort(key=lambda x: x["set_num"])
    return result


def _classify_main_lift_sets_fallback(parsed: list[dict]) -> list[dict]:
    """
    Fallback classification when TM is not available.
    Uses heuristic: find 3 ascending sets, everything before = warmup,
    after = supplemental. No joker detection without TM.
    """
    if not parsed:
        return []

    max_weight = max(p["weight"] for p in parsed)
    peak_idx = max(p["idx"] for p in parsed if p["weight"] == max_weight)

    result = []
    post_peak = [p for p in parsed if p["idx"] > peak_idx]
    bbb_weight = None
    if post_peak:
        weight_counts = {}
        for p in post_peak:
            weight_counts[p["weight"]] = weight_counts.get(p["weight"], 0) + 1
        if weight_counts:
            bbb_weight = max(weight_counts, key=weight_counts.get)

    pre_peak = [p for p in parsed if p["idx"] <= peak_idx]
    set_num = 0
    for p in parsed:
        set_num += 1
        w, r, idx = p["weight"], p["reps"], p["idx"]
        if idx > peak_idx and bbb_weight is not None and w == bbb_weight:
            result.append({"type": "bbb", "weight": w, "reps": r, "set_num": set_num})
        elif idx <= peak_idx:
            if p in pre_peak[-3:]:
                if p == pre_peak[-1]:
                    result.append({"type": "amrap", "weight": w, "reps": r, "set_num": set_num})
                else:
                    result.append({"type": "working_531", "weight": w, "reps": r, "set_num": set_num})
            else:
                result.append({"type": "warmup", "weight": w, "reps": r, "set_num": set_num})
        else:
            result.append({"type": "bbb", "weight": w, "reps": r, "set_num": set_num})

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
    Add cycle info columns using Beyond 5/3/1 structure.

    Beyond scheme: 7-week macro = 3 working + 3 working + 1 deload.
    TM bumps after each 3-week mini-cycle.
    Each 'week' = 4 training sessions.
    """
    if df.empty:
        return df

    df = df.copy()

    # Get unique training dates in order
    dates = sorted(df["date"].unique())
    date_to_session = {d: i + 1 for i, d in enumerate(dates)}
    df["session_num"] = df["date"].map(date_to_session)

    # Use get_cycle_position for each session
    def _pos(session_num):
        # session_num is 1-based, get_cycle_position takes total completed sessions
        return get_cycle_position(session_num - 1)

    positions = {sn: _pos(sn) for sn in df["session_num"].unique()}

    df["week_in_macro"] = df["session_num"].map(lambda sn: positions[sn]["week_in_macro"])
    df["week_type"] = df["session_num"].map(lambda sn: positions[sn]["week_type"])
    df["week_name"] = df["session_num"].map(lambda sn: positions[sn]["week_name"])
    df["mini_cycle"] = df["session_num"].map(lambda sn: positions[sn]["mini_cycle"])
    df["macro_num"] = df["session_num"].map(lambda sn: positions[sn]["macro_num"])
    df["tm_bumps"] = df["session_num"].map(lambda sn: positions[sn]["tm_bumps_completed"])

    # Keep backwards-compatible column names
    df["cycle_num"] = df["macro_num"]
    df["week_in_cycle"] = df["week_type"]
    df["cycle_week"] = df["week_in_macro"]

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
    bbb = df[df["set_type"].str.startswith("bbb")].copy()
    if bbb.empty:
        return pd.DataFrame()

    grouped = bbb.groupby(["date", "hevy_id", "lift"]).agg(
        weight_kg=("weight_kg", "first"),  # Should be constant
        n_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        avg_reps=("reps", "mean"),
        min_reps=("reps", "min"),
        has_amrap=("set_type", lambda x: (x == "bbb_amrap").any()),
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


def fsl_compliance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Track FSL (First Set Last) supplemental work compliance.

    FSL target: 3-5 sets of 5-8 reps at first working set weight.
    """
    fsl = df[df["set_type"] == "fsl"].copy()
    if fsl.empty:
        return pd.DataFrame()

    grouped = fsl.groupby(["date", "hevy_id", "lift"]).agg(
        weight_kg=("weight_kg", "first"),
        n_sets=("reps", "count"),
        total_reps=("reps", "sum"),
        avg_reps=("reps", "mean"),
        min_reps=("reps", "min"),
    ).reset_index()

    grouped["avg_reps"] = grouped["avg_reps"].round(1)
    grouped["target_sets_min"] = 3
    grouped["target_sets_max"] = 5
    grouped["sets_ok"] = grouped["n_sets"].between(3, 5)
    grouped["reps_ok"] = grouped["avg_reps"].between(5, 8)

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
        bbb = grp[grp["set_type"].str.startswith("bbb")]

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


def joker_sets_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate joker set data: date, lift, weight, reps, e1rm."""
    jokers = df[df["set_type"] == "joker"].copy()
    if jokers.empty:
        return pd.DataFrame()

    result = jokers.groupby(["date", "hevy_id", "lift"]).agg(
        weight_kg=("weight_kg", "max"),
        total_sets=("reps", "count"),
        best_reps=("reps", "max"),
        best_e1rm=("e1rm", "max"),
    ).reset_index()

    return result.sort_values("date", ascending=False).reset_index(drop=True)


def validate_tm(df: pd.DataFrame) -> dict:
    """
    Check if Training Max is calibrated for each lift.

    Uses AMRAP performance (reps over minimum) to determine if TM is
    too light, too heavy, or correctly set.

    Returns dict per lift:
      - status: "ok" | "too_light" | "too_heavy"
      - avg_reps_over_min: mean reps above prescribed minimum
      - latest_e1rm: most recent AMRAP e1RM
      - current_tm: from config
      - recommended_tm: latest_e1rm * 0.90 rounded to plate
    """
    amraps = amrap_tracking(df)
    if amraps.empty:
        return {}

    result = {}
    for lift in amraps["lift"].unique():
        lift_amraps = amraps[amraps["lift"] == lift].sort_values("date")
        if lift_amraps.empty:
            continue

        avg_over = lift_amraps["reps_over_min"].mean()
        latest_e1rm = lift_amraps["e1rm"].iloc[-1]
        current_tm = TRAINING_MAX.get(lift, 0) or 0
        recommended_tm = round_to_plate(latest_e1rm * 0.90)

        if avg_over > 5:
            status = "too_light"
        elif avg_over < 0:
            status = "too_heavy"
        else:
            status = "ok"

        result[lift] = {
            "status": status,
            "avg_reps_over_min": round(avg_over, 1),
            "latest_e1rm": round(latest_e1rm, 1),
            "current_tm": current_tm,
            "recommended_tm": recommended_tm,
            "tm_delta": recommended_tm - current_tm,
            "n_amraps": len(lift_amraps),
        }

    return result


def cycle_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare metrics across cycles per lift.

    Groups by cycle_num and lift, aggregates AMRAP e1RM, BBB volume,
    and total sets. Adds delta columns vs previous cycle.
    """
    if df.empty or "cycle_num" not in df.columns:
        return pd.DataFrame()

    amraps = df[df["set_type"] == "amrap"].copy()
    bbb = df[df["set_type"].str.startswith("bbb")].copy()

    if amraps.empty:
        return pd.DataFrame()

    # AMRAP metrics per cycle per lift
    amrap_agg = amraps.groupby(["cycle_num", "lift"]).agg(
        amrap_avg_reps=("reps", "mean"),
        amrap_best_e1rm=("e1rm", "max"),
        amrap_avg_e1rm=("e1rm", "mean"),
        n_amraps=("reps", "count"),
    ).reset_index()

    amrap_agg["amrap_avg_reps"] = amrap_agg["amrap_avg_reps"].round(1)
    amrap_agg["amrap_avg_e1rm"] = amrap_agg["amrap_avg_e1rm"].round(1)

    # BBB volume per cycle per lift
    if not bbb.empty:
        bbb_agg = bbb.groupby(["cycle_num", "lift"]).agg(
            bbb_total_volume=("volume_kg", "sum"),
            bbb_sets=("reps", "count"),
        ).reset_index()
        result = amrap_agg.merge(bbb_agg, on=["cycle_num", "lift"], how="left")
    else:
        result = amrap_agg
        result["bbb_total_volume"] = 0
        result["bbb_sets"] = 0

    result = result.fillna(0)

    # Add deltas vs previous cycle
    result = result.sort_values(["lift", "cycle_num"])
    result["e1rm_delta"] = result.groupby("lift")["amrap_best_e1rm"].diff()
    result["e1rm_delta_pct"] = (
        result.groupby("lift")["amrap_best_e1rm"]
        .pct_change() * 100
    ).round(1)

    return result.sort_values(["cycle_num", "lift"]).reset_index(drop=True)


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
    Uses Beyond 5/3/1 cycle position and effective TM (with bumps).

    Returns {
        day_num, day_name, lift, lift_label, macro_num, week_in_macro,
        week_name, mini_cycle, tm, working_sets, bbb, warmup
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

    pos = get_cycle_position(total_sessions)
    week_type = pos["week_type"]
    macro_num = pos["macro_num"]
    tm_bumps = pos["tm_bumps_completed"]

    day_cfg = DAY_CONFIG_531.get(next_day, {})
    lift = day_cfg.get("main_lift", "?")
    week_cfg = CYCLE_WEEKS.get(week_type, CYCLE_WEEKS[1])

    # Effective TM after all bumps
    tm = get_effective_tm(lift, tm_bumps)

    plan = {
        "day_num": next_day,
        "day_name": day_cfg.get("name", f"Día {next_day}"),
        "focus": day_cfg.get("focus", ""),
        "lift": lift,
        "lift_label": {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Squat"}.get(lift, lift),
        "macro_num": macro_num,
        "week_in_macro": pos["week_in_macro"],
        "mini_cycle": pos["mini_cycle"],
        "week_type": week_type,
        "week_name": pos["week_name"],
        "tm": tm,
        "tm_bumps": tm_bumps,
        "working_sets": [],
        "bbb": None,
        "warmup": [],
        # Backwards compat
        "cycle_num": macro_num,
        "week_in_cycle": week_type,
    }

    if not tm:
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
    # Cycle for BBB progression is based on total macro cycles completed
    bbb_cycle_key = min(macro_num, max(BBB_PCT_PROGRESSION.keys()))
    bbb_pct = BBB_PCT_PROGRESSION.get(bbb_cycle_key, 0.50)
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
    Uses Beyond 5/3/1 position and effective TM.
    """
    if df.empty:
        total_sessions = 0
    else:
        total_sessions = df["hevy_id"].nunique()

    pos = get_cycle_position(total_sessions)
    week_type = pos["week_type"]
    macro_num = pos["macro_num"]
    tm_bumps = pos["tm_bumps_completed"]
    week_cfg = CYCLE_WEEKS.get(week_type, CYCLE_WEEKS[1])

    plans = []
    for day_num in [1, 2, 3, 4]:
        day_cfg = DAY_CONFIG_531.get(day_num, {})
        lift = day_cfg.get("main_lift", "?")
        tm = get_effective_tm(lift, tm_bumps)
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

            bbb_cycle_key = min(macro_num, max(BBB_PCT_PROGRESSION.keys()))
            bbb_pct = BBB_PCT_PROGRESSION.get(bbb_cycle_key, 0.50)
            bbb_w = round_to_plate(tm * bbb_pct)
            day_plan["bbb_weight"] = bbb_w
            day_plan["bbb_plates"] = format_plates(plate_breakdown(bbb_w))

        plans.append(day_plan)

    return plans


# ═════════════════════════════════════════════════════════════════════
# HEVY ROUTINE AUTO-UPDATER
# ═════════════════════════════════════════════════════════════════════

def build_routine_exercises(day_num: int, week_type: int, macro_num: int, tm_bumps: int) -> list:
    """
    Build the full exercise list for a Hevy routine with correct weights
    for the given week/cycle, using effective TM after bumps.
    """
    day_cfg = DAY_CONFIG_531.get(day_num, {})
    lift = day_cfg.get("main_lift")
    tm = get_effective_tm(lift, tm_bumps)
    tid = MAIN_LIFT_TIDS.get(lift)
    week_cfg = CYCLE_WEEKS.get(week_type, CYCLE_WEEKS[1])

    if not tm or not tid:
        return []

    # ── Main lift sets ──
    main_sets = []

    # Warmup: 40%, 50%, 60%
    for pct in [0.40, 0.50, 0.60]:
        w = round_to_plate(tm * pct)
        main_sets.append({"type": "warmup", "weight_kg": w, "reps": 5})

    # Working 531 sets
    for s in week_cfg["sets"]:
        w = round_to_plate(tm * s["pct"])
        reps = s["reps"]
        # AMRAP shows as the minimum reps target in routine
        if isinstance(reps, str):
            reps = int(reps.replace("+", ""))
        main_sets.append({"type": "normal", "weight_kg": w, "reps": reps})

    # BBB 5×10
    bbb_cycle_key = min(macro_num, max(BBB_PCT_PROGRESSION.keys()))
    bbb_pct = BBB_PCT_PROGRESSION.get(bbb_cycle_key, 0.50)
    bbb_w = round_to_plate(tm * bbb_pct)
    for _ in range(5):
        main_sets.append({"type": "normal", "weight_kg": bbb_w, "reps": 10})

    # Rest time: longer for DL/Squat
    rest = 180 if lift in ("deadlift", "squat") else 120

    exercises = [{"exercise_template_id": tid, "rest_seconds": rest, "sets": main_sets}]

    # ── Accessories (static templates from config) ──
    accessories = DAY_ACCESSORIES.get(day_num, [])
    exercises.extend(accessories)

    return exercises


def update_hevy_routines(df: pd.DataFrame) -> dict:
    """
    Update all 4 BBB routines in Hevy with correct weights for the current
    week/cycle using Beyond 5/3/1 structure and effective TM.
    Returns {day_num: {status, week, macro, lift, tm}}.
    """
    import requests
    import time
    import os

    api_key = os.environ.get("HEVY_API_KEY", "")
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "Content-Type": "application/json",
    }

    # Determine current position
    if df.empty:
        total_sessions = 0
    else:
        total_sessions = df["hevy_id"].nunique()

    pos = get_cycle_position(total_sessions)
    week_type = pos["week_type"]
    macro_num = pos["macro_num"]
    tm_bumps = pos["tm_bumps_completed"]

    results = {}

    for day_num, routine_id in DAY_ROUTINE_MAP.items():
        day_cfg = DAY_CONFIG_531.get(day_num, {})
        lift = day_cfg.get("main_lift", "?")
        title = day_cfg.get("name", f"BBB día {day_num}")
        effective_tm = get_effective_tm(lift, tm_bumps)

        exercises = build_routine_exercises(day_num, week_type, macro_num, tm_bumps)
        if not exercises:
            results[day_num] = {"status": "skipped", "reason": "no TM"}
            continue

        payload = {
            "routine": {
                "title": title,
                "exercises": exercises,
            }
        }

        time.sleep(0.5)
        try:
            r = requests.put(
                f"https://api.hevyapp.com/v1/routines/{routine_id}",
                headers=headers, json=payload
            )
            if r.ok:
                results[day_num] = {
                    "status": "updated",
                    "lift": lift,
                    "week": pos["week_name"],
                    "macro": macro_num,
                    "tm": effective_tm,
                    "tm_bumps": tm_bumps,
                    "week_in_macro": pos["week_in_macro"],
                }
            else:
                results[day_num] = {"status": "error", "code": r.status_code, "msg": r.text[:200]}
        except Exception as e:
            results[day_num] = {"status": "error", "msg": str(e)}

    return results


# ── Training Calendar / Timeline ────────────────────────────────────

def training_calendar(df: pd.DataFrame, weeks_ahead: int = 16) -> list[dict]:
    """
    Build a training calendar showing past completed weeks and future projections.
    Returns a list of week dicts with TMs, status, deload flags, etc.
    """
    from src.config_531 import (
        get_cycle_position, get_effective_tm, TRAINING_MAX,
        SESSIONS_PER_WEEK, MACRO_CYCLE_LENGTH,
    )

    # Ensure cycle info is present
    if not df.empty and "week_in_macro" not in df.columns:
        df = add_cycle_info(df)

    lifts = list(TRAINING_MAX.keys())
    total_sessions = df["hevy_id"].nunique() if not df.empty else 0

    # --- Past weeks: group actual sessions ---
    past_weeks = {}
    if not df.empty and "week_in_macro" in df.columns:
        # Each unique (macro_num, week_in_macro) = one training week
        session_dates = df.groupby("hevy_id").agg(
            date=("date", "first"),
            week_in_macro=("week_in_macro", "first"),
            macro_num=("macro_num", "first"),
            week_name=("week_name", "first"),
            tm_bumps=("tm_bumps", "first"),
        ).reset_index()

        for (macro, week_m), grp in session_dates.groupby(["macro_num", "week_in_macro"]):
            key = (int(macro), int(week_m))
            sessions_in_week = []
            for _, row in grp.iterrows():
                hid = row["hevy_id"]
                sess_df = df[df["hevy_id"] == hid]
                main = sess_df[sess_df["set_type"].isin(["amrap", "working_531"])].head(1)
                lift = main["lift"].iloc[0] if not main.empty else "?"
                amrap = sess_df[sess_df["set_type"] == "amrap"]
                amrap_str = ""
                if not amrap.empty:
                    a = amrap.iloc[0]
                    amrap_str = f"{a['weight_kg']:.0f}kg × {a['reps']:.0f}"
                sessions_in_week.append({
                    "date": row["date"],
                    "lift": lift,
                    "amrap": amrap_str,
                })
            past_weeks[key] = {
                "sessions": sorted(sessions_in_week, key=lambda s: s["date"]),
                "week_name": grp["week_name"].iloc[0],
                "tm_bumps": int(grp["tm_bumps"].iloc[0]),
            }

    # --- Build calendar: past + current + future ---
    current_pos = get_cycle_position(total_sessions)
    current_macro = current_pos["macro_num"]
    current_week_m = current_pos["week_in_macro"]

    calendar = []

    # Determine range: from week 1 of macro 1 through weeks_ahead from now
    # Each "week" = 4 sessions, so session_offset = (absolute_week - 1) * 4
    # We need to figure out total weeks completed + future
    weeks_completed = total_sessions // SESSIONS_PER_WEEK
    total_weeks = weeks_completed + weeks_ahead

    for abs_week in range(total_weeks):
        session_offset = abs_week * SESSIONS_PER_WEEK
        pos = get_cycle_position(session_offset)

        tms = {lift: get_effective_tm(lift, pos["tm_bumps_completed"])
               for lift in lifts}

        key = (pos["macro_num"], pos["week_in_macro"])
        is_deload = pos["week_type"] == 4
        # TM bump happens after weeks 3 and 6
        is_bump_week = pos["week_in_macro"] in (3, 6)

        # Status
        if key in past_weeks:
            pw = past_weeks[key]
            done_count = len(pw["sessions"])
            if done_count >= SESSIONS_PER_WEEK:
                status = "completed"
            else:
                status = "partial"
            sessions = pw["sessions"]
        elif abs_week == weeks_completed:
            status = "current"
            sessions = past_weeks.get(key, {}).get("sessions", [])
        else:
            status = "upcoming"
            sessions = []

        calendar.append({
            "abs_week": abs_week + 1,
            "macro_num": pos["macro_num"],
            "week_in_macro": pos["week_in_macro"],
            "mini_cycle": pos["mini_cycle"],
            "week_name": pos["week_name"],
            "week_type": pos["week_type"],
            "is_deload": is_deload,
            "is_bump_week": is_bump_week,
            "tm_bumps": pos["tm_bumps_completed"],
            "tms": tms,
            "status": status,
            "sessions": sessions,
            "sessions_done": len(sessions),
        })

    return calendar
