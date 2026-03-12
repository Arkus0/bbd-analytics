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
    TM_HISTORY,
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
    get_day_accessories,
    _ACC_TIDS,
    round_to_plate,
    get_cycle_position,
    get_effective_tm,
    get_session_tm,
    expected_weights,
    MACRO_CYCLE_LENGTH,
    WORKING_BLOCK_LENGTH,
    # Forever framework
    get_plan_position,
    get_supplemental_pct,
    get_fsl_pct,
    SUPPLEMENTAL_TEMPLATES,
    MAIN_WORK_MODES,
    PLAN_START_SESSION,
    SESSIONS_PER_WEEK,
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


def parse_workout_sets(workout: dict, session_tms: dict | None = None) -> list[dict]:
    """
    Parse a single BBB workout into classified set rows.

    Args:
        workout: Raw Hevy workout dict.
        session_tms: {lift: effective_tm_kg} for this session.
            Computed from TM_HISTORY + bumps by the caller.
            If None, falls back to current TRAINING_MAX.

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
            tm = (session_tms or {}).get(lift) or TRAINING_MAX.get(lift)
            classified = _classify_main_lift_sets(sets, lift, tm_override=tm)
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


def _classify_main_lift_sets(sets: list[dict], lift: str, tm_override: float = None) -> list[dict]:
    """
    Classify individual sets of a main lift exercise.

    Uses the session's effective TM (passed via tm_override) to match
    working sets against expected percentages for each week type (5s/3s/531).

    Predetermined (from TM):  warmup, working_531, amrap, bbb
    Mutable (per session):    joker, fsl, bbb_amrap

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

    tm = tm_override or TRAINING_MAX.get(lift)
    if not tm:
        return _classify_main_lift_sets_fallback(parsed)

    # ── Step 1: Find the 3 working sets by matching expected weights ──
    # Try each week type (5s, 3s, 531) against the session TM.
    # Score = weight matches + rep pattern bonus.
    best_week = None
    best_score = -999
    working_indices = None

    for week_num in [1, 2, 3]:
        exp = expected_weights(lift, week_num, tm_override=tm)
        if not exp:
            continue
        exp_weights = [e["weight"] for e in exp]

        for start in range(len(parsed) - 2):
            candidates = parsed[start:start + 3]
            if candidates[0]["hevy_type"] == "warmup":
                continue
            # Working sets must be strictly ascending weight
            if not (candidates[0]["weight"] < candidates[1]["weight"] < candidates[2]["weight"]):
                continue

            # Weight match score (0-3 points, ±2kg tolerance)
            weight_score = sum(
                1 for cand, ew in zip(candidates, exp_weights)
                if abs(cand["weight"] - ew) <= 2
            )
            if weight_score < 2:
                continue

            # Rep pattern: AMRAP (top set) typically has high reps
            top_reps = candidates[2]["reps"]
            rep_bonus = 3 if top_reps > 8 else (1 if top_reps > 5 else 0)

            # Structural: penalize if heavier sets follow with low reps (→ jokers)
            heavier_after = [p for p in parsed
                            if p["idx"] > candidates[2]["idx"]
                            and p["weight"] > candidates[2]["weight"]]
            structural_penalty = -2 if heavier_after and top_reps <= 5 else 0

            score = weight_score + rep_bonus + structural_penalty
            if score > best_score:
                best_score = score
                best_week = week_num
                working_indices = set(p["idx"] for p in candidates)

    if best_score < 2:
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
    """Convert raw BBB workouts to a flat DataFrame with set-level classification.

    Sorts workouts chronologically, computes the effective TM for each session
    using TM_HISTORY + automatic bumps, and passes it to the classifier so
    every set is classified against the TM that was actually in effect.
    """
    # Sort chronologically so session numbering is correct
    workouts = sorted(workouts, key=lambda w: w.get("start_time", ""))

    lifts = list(TRAINING_MAX.keys())
    all_rows = []

    for session_idx, w in enumerate(workouts):
        date_str = w["start_time"][:10]
        pos = get_cycle_position(session_idx)  # 0-based total completed
        tm_bumps = pos["tm_bumps_completed"]

        # Build per-lift TM dict for this session
        session_tms = {
            lift: get_session_tm(lift, date_str, tm_bumps)
            for lift in lifts
        }

        rows = parse_workout_sets(w, session_tms=session_tms)
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

    Also computes effective_tm per session — the TM that was actually in
    effect for each session, accounting for TM_HISTORY and bumps.
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

    # ── Effective TM per session ──
    # For each session, compute the TM that was in effect for each lift.
    # Stored as a single "effective_tm" column matching the row's lift.
    # Rows without a lift (accessories) get NaN.
    lifts = list(TRAINING_MAX.keys())

    # Pre-compute TMs per session (date + tm_bumps → per-lift TMs)
    session_tms = {}
    for sn, pos in positions.items():
        date = [d for d, s in date_to_session.items() if s == sn][0]
        date_str = str(date)[:10]
        tm_bumps = pos["tm_bumps_completed"]
        session_tms[sn] = {
            lift: get_session_tm(lift, date_str, tm_bumps)
            for lift in lifts
        }

    def _get_eff_tm(row):
        lift = row.get("lift")
        sn = row.get("session_num")
        if not lift or not sn or sn not in session_tms:
            return None
        return session_tms[sn].get(lift)

    df["effective_tm"] = df.apply(_get_eff_tm, axis=1)

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
        lambda r: round(r["weight_kg"] / r["effective_tm"] * 100, 1)
        if r.get("effective_tm") and r["effective_tm"] > 0
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
        effective_tm=("effective_tm", "first"),
    ).reset_index()

    grouped["avg_reps"] = grouped["avg_reps"].round(1)
    grouped["target_sets"] = 5
    grouped["target_reps"] = 10
    grouped["sets_ok"] = grouped["n_sets"] >= 5
    grouped["reps_ok"] = grouped["avg_reps"] >= 9  # Allow slight miss

    # % of TM
    grouped["pct_of_tm"] = grouped.apply(
        lambda r: round(r["weight_kg"] / r["effective_tm"] * 100, 1)
        if r.get("effective_tm") and r["effective_tm"] > 0
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
        effective_tm=("effective_tm", "first"),
    ).reset_index()

    grouped["avg_reps"] = grouped["avg_reps"].round(1)
    grouped["target_sets_min"] = 3
    grouped["target_sets_max"] = 5
    grouped["sets_ok"] = grouped["n_sets"].between(3, 5)
    grouped["reps_ok"] = grouped["avg_reps"].between(5, 8)

    grouped["pct_of_tm"] = grouped.apply(
        lambda r: round(r["weight_kg"] / r["effective_tm"] * 100, 1)
        if r.get("effective_tm") and r["effective_tm"] > 0
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
        effective_tm=("effective_tm", "last"),
    ).reset_index()

    result["estimated_tm"] = (result["e1rm"] * 0.90).apply(round_to_plate)
    result["current_tm"] = result["effective_tm"].fillna(0).astype(float)

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

    # Get current effective TM per lift from the latest session in the data
    latest_tms = {}
    if "effective_tm" in df.columns:
        for lift in df["lift"].dropna().unique():
            lift_rows = df[(df["lift"] == lift) & df["effective_tm"].notna()]
            if not lift_rows.empty:
                latest_tms[lift] = lift_rows.sort_values("date")["effective_tm"].iloc[-1]

    result = {}
    for lift in amraps["lift"].unique():
        lift_amraps = amraps[amraps["lift"] == lift].sort_values("date")
        if lift_amraps.empty:
            continue

        avg_over = lift_amraps["reps_over_min"].mean()
        latest_e1rm = lift_amraps["e1rm"].iloc[-1]
        current_tm = latest_tms.get(lift) or TRAINING_MAX.get(lift, 0) or 0
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
        "lift_label": {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}.get(lift, lift),
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

    # ── Supplemental sets (Forever-aware) ──
    plan_pos = get_plan_position(total_sessions)
    supp_key = plan_pos.get("supplemental_template", "bbb_constant")
    supp_tmpl = SUPPLEMENTAL_TEMPLATES.get(supp_key, {})
    cycle_in_phase = plan_pos.get("cycle_in_phase", 1) or 1
    physical_week = plan_pos.get("physical_week", week_type)

    if supp_key == "none" or supp_tmpl.get("sets_per_session", 0) == 0:
        # Deload / TM test — no supplemental
        plan["bbb"] = None
    elif supp_tmpl.get("replaces_main_work"):
        # 5x5/3/1 etc — supplemental IS the main work, already in working_sets
        plan["bbb"] = None
    else:
        supp_pct = get_supplemental_pct(supp_key, physical_week, cycle_in_phase)
        if supp_pct is None:
            # FSL: use first working set percentage
            supp_pct = get_fsl_pct(week_type)

        # Handle mixed templates (SVR II, Pervertor)
        if supp_tmpl.get("pct_source") == "mixed" and "week_spec" in supp_tmpl:
            ws = supp_tmpl["week_spec"].get(physical_week, {})
            n_sets = ws.get("sets", 5)
            reps = ws.get("reps", 10)
            if isinstance(reps, str):
                reps = 20  # "15-20" → target
            if ws.get("pct_source") == "fsl":
                supp_pct = get_fsl_pct(week_type)
            elif "pct" in ws:
                supp_pct = ws["pct"]
        else:
            n_sets = supp_tmpl.get("sets_per_session", 5)
            reps = supp_tmpl.get("reps_per_set", 10)

        supp_w = round_to_plate(tm * supp_pct)
        supp_plates = plate_breakdown(supp_w)
        plan["bbb"] = {
            "weight": supp_w,
            "sets": n_sets,
            "reps": reps,
            "pct_tm": supp_pct,
            "plates": supp_plates,
            "plates_str": format_plates(supp_plates),
            "template_name": supp_tmpl.get("name", supp_key),
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

    pos = get_plan_position(total_sessions)
    supp_key = pos.get("supplemental_template", "bbb_constant")
    supp_tmpl = SUPPLEMENTAL_TEMPLATES.get(supp_key, {})
    cycle_in_phase = pos.get("cycle_in_phase", 1) or 1
    physical_week = pos.get("physical_week", week_type)

    plans = []
    for day_num in [1, 2, 3, 4]:
        day_cfg = DAY_CONFIG_531.get(day_num, {})
        lift = day_cfg.get("main_lift", "?")
        tm = get_effective_tm(lift, tm_bumps)
        label = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}.get(lift, lift)

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

            # Supplemental weight (Forever-aware)
            if supp_key != "none" and not supp_tmpl.get("replaces_main_work"):
                supp_pct = get_supplemental_pct(supp_key, physical_week, cycle_in_phase)
                if supp_pct is None:
                    supp_pct = get_fsl_pct(week_type)
                if supp_tmpl.get("pct_source") == "mixed" and "week_spec" in supp_tmpl:
                    ws = supp_tmpl["week_spec"].get(physical_week, {})
                    if ws.get("pct_source") == "fsl":
                        supp_pct = get_fsl_pct(week_type)
                    elif "pct" in ws:
                        supp_pct = ws["pct"]
                bbb_w = round_to_plate(tm * supp_pct)
            else:
                bbb_w = 0
            day_plan["bbb_weight"] = bbb_w
            day_plan["bbb_plates"] = format_plates(plate_breakdown(bbb_w)) if bbb_w else ""

        plans.append(day_plan)

    return plans


# ═════════════════════════════════════════════════════════════════════
# HEVY ROUTINE AUTO-UPDATER
# ═════════════════════════════════════════════════════════════════════

def _build_session_notes(plan_pos: dict | None, lift: str, tm: float,
                         week_type: int, supp_key: str, main_work_key: str,
                         replaces_main: bool, cycle_in_phase: int,
                         physical_week: int = 1) -> str:
    """
    Build informational notes for the main lift exercise in Hevy.

    Gives Juan all the context he needs without consulting the book:
    - Phase (Leader/Anchor/Deload/TM Test)
    - Main work mode (5's PRO vs PR Set vs Jokers)
    - Supplemental template and what it means
    - Rest time guidance
    - Key rules for this phase
    """
    if plan_pos is None:
        return ""

    phase = plan_pos.get("phase", "pre_plan")
    block = plan_pos.get("block")
    block_name = block["name"] if block else "Pre-plan"
    week_name = plan_pos.get("week_name", "?")

    lines = []

    # ── Header: where we are ──
    phase_labels = {
        "leader": "📦 LEADER",
        "anchor": "⚓ ANCHOR",
        "7th_week_deload": "🛌 DELOAD",
        "7th_week_tm_test": "📊 TM TEST",
        "pre_plan": "🔄 PRE-PLAN",
    }
    lines.append(f"{phase_labels.get(phase, phase)} · {block_name}")
    lines.append(f"TM: {tm:.0f}kg · {week_name}")

    # ── Main work instructions ──
    if phase == "7th_week_deload":
        lines.append("")
        lines.append("⚡ Deload: pesos ligeros, sin esforzarse")
        lines.append("❌ Sin AMRAP · Sin jokers")
        lines.append("🎯 Movilidad y recuperación")
    elif phase == "7th_week_tm_test":
        lines.append("")
        lines.append("📊 Subir hasta TM × 3-5 reps")
        lines.append("Si no sacas 3-5 reps → bajar TM un 10%")
        lines.append("❌ Sin jokers · Sin AMRAP")
    elif main_work_key == "5s_pro":
        lines.append("")
        lines.append("⚡ 5's PRO: todas las series ×5")
        lines.append("❌ Sin AMRAP · Sin jokers")
        lines.append("🎯 Velocidad de barra · Control")
    elif main_work_key == "pr_set":
        lines.append("")
        lines.append("🔥 PR SET: última serie AMRAP")
        lines.append("💪 Deja 1-2 reps en reserva")
        lines.append("❌ Sin jokers")
    elif main_work_key == "pr_set_jokers":
        lines.append("")
        lines.append("🔥 PR SET: última serie AMRAP")
        lines.append("🃏 JOKERS: 1-3 singles/triples por encima")
        lines.append("💪 Solo si el AMRAP ha ido bien")

    # ── Supplemental info ──
    supp_tmpl = SUPPLEMENTAL_TEMPLATES.get(supp_key, {})
    supp_name = supp_tmpl.get("name", supp_key)
    skip_generic_rest = False

    if replaces_main:
        # 5x5/3/1: the supplemental IS the main work
        lines.append("")
        lines.append(f"📋 {supp_name}: las 5×5 SON el trabajo principal")
        lines.append("🎯 Barra rápida en cada rep")
    elif supp_key == "none":
        pass  # Deload, no supplemental
    elif supp_key == "bbs":
        lines.append("")
        lines.append(f"📋 Suplemental: {supp_name}")
        lines.append("💀 10×5 al peso del primer set (FSL)")
        lines.append("⏱️ Descanso supl: 2-3 min entre sets")
        skip_generic_rest = True
    elif supp_key == "pervertor":
        ws = supp_tmpl.get("week_spec", {}).get(physical_week, {})
        supp_type = ws.get("type", "?")
        type_labels = {"bbs": "10×5 FSL (BBS)", "bbb": "5×10 FSL (BBB)", "ssl": "5×5 SSL (85%)"}
        lines.append("")
        lines.append(f"📋 Suplemental: Pervertor")
        lines.append(f"→ Esta semana: {type_labels.get(supp_type, supp_type)}")
    elif supp_key == "widowmaker":
        lines.append("")
        lines.append(f"📋 Suplemental: Widowmaker")
        lines.append("💀 1×20 al peso del primer set (FSL)")
        lines.append("🫁 Respira entre reps si hace falta")
    elif "bbb" in supp_key:
        pct_map = supp_tmpl.get("pct_by_week", {})
        pct = pct_map.get(week_type) or supp_tmpl.get("pct_by_cycle", {}).get(cycle_in_phase)
        pct_str = f"{int(pct*100)}%" if pct else "FSL%"
        lines.append("")
        lines.append(f"📋 Suplemental: {supp_name}")
        lines.append(f"→ 5×10 @ {pct_str} del TM")
    elif supp_key == "fsl_5x5":
        lines.append("")
        lines.append(f"📋 Suplemental: FSL 5×5")
        lines.append("→ 5×5 al peso del primer set de trabajo")
    elif supp_key == "ssl_5x5":
        lines.append("")
        lines.append(f"📋 Suplemental: SSL 5×5")
        lines.append("→ 5×5 al peso del segundo set de trabajo")
    else:
        if supp_name and supp_name != "No supplemental":
            lines.append("")
            lines.append(f"📋 Suplemental: {supp_name}")

    # ── Rest guidance ──
    if phase not in ("7th_week_deload", "7th_week_tm_test") and not skip_generic_rest:
        lines.append("")
        if lift in ("deadlift", "squat"):
            lines.append("⏱️ Descanso: 3-5 min (principal) · 2-3 min (supl)")
        else:
            lines.append("⏱️ Descanso: 2-3 min (principal) · 90s-2 min (supl)")

    # ── Assistance reminder ──
    if phase == "leader":
        lines.append("")
        lines.append("🏋️ Asistencia: push 25-50, pull 25-50, pierna/core 25-50")
    elif phase == "anchor":
        lines.append("")
        lines.append("🏋️ Asistencia: push 50-100, pull 50-100, pierna/core 50-100")

    return "\n".join(lines)


def build_routine_exercises(day_num: int, week_type: int, macro_num: int, tm_bumps: int,
                            plan_pos: dict | None = None) -> list:
    """
    Build the full exercise list for a Hevy routine with correct weights.

    If plan_pos is provided (from get_plan_position), uses the Forever
    framework (Leader/Anchor/7th Week). Otherwise falls back to legacy
    Beyond 5/3/1 BBB behavior for backwards compatibility.
    """
    day_cfg = DAY_CONFIG_531.get(day_num, {})
    lift = day_cfg.get("main_lift")
    tm = get_effective_tm(lift, tm_bumps)
    tid = MAIN_LIFT_TIDS.get(lift)

    if not tm or not tid:
        return []

    # Resolve template and main work mode
    if plan_pos and plan_pos.get("phase") != "pre_plan":
        supp_key = plan_pos.get("supplemental_template", "bbb_constant")
        main_mode_key = plan_pos.get("main_work_mode", "pr_set")
        cycle_in_phase = plan_pos.get("cycle_in_phase", 1) or 1
    else:
        # Legacy: always BBB + PR set
        supp_key = "bbb_constant"
        main_mode_key = "pr_set"
        cycle_in_phase = 1

    supp_tmpl = SUPPLEMENTAL_TEMPLATES.get(supp_key, {})
    main_mode = MAIN_WORK_MODES.get(main_mode_key, MAIN_WORK_MODES["pr_set"])

    # Physical week = position in cycle (1,2,3). Used for supplemental rotation.
    # week_type = remapped via week_order. Used for CYCLE_WEEKS/FSL percentages.
    physical_week = plan_pos.get("physical_week", week_type) if plan_pos else week_type

    # ── Main lift sets ──
    main_sets = []

    # Check if supplemental replaces main work entirely (5x5/3/1)
    replaces_main = supp_tmpl.get("replaces_main_work", False)

    if replaces_main:
        # Templates like 5x5/3/1: warmup → 5x5 at one percentage, no separate 531 sets
        for pct in [0.40, 0.50, 0.60]:
            w = round_to_plate(tm * pct)
            main_sets.append({"type": "warmup", "weight_kg": w, "reps": 5})

        # Get the week-specific spec
        if "week_spec" in supp_tmpl:
            ws = supp_tmpl["week_spec"].get(week_type, supp_tmpl["week_spec"].get(1, {}))
            n_sets = ws.get("sets", 5)
            reps = ws.get("reps", 5)
            pct = ws.get("pct", 0.85)
        else:
            pct_map = supp_tmpl.get("pct_by_week", {})
            pct = pct_map.get(week_type, 0.85)
            n_sets = supp_tmpl.get("sets_per_session", 5)
            reps = supp_tmpl.get("reps_per_set", 5)

        w = round_to_plate(tm * pct)
        for _ in range(n_sets):
            main_sets.append({"type": "normal", "weight_kg": w, "reps": reps})

    else:
        # Standard flow: warmup → working 531 sets → supplemental

        # -- Warmup --
        for pct in [0.40, 0.50, 0.60]:
            w = round_to_plate(tm * pct)
            main_sets.append({"type": "warmup", "weight_kg": w, "reps": 5})

        # -- Working sets (depends on main_work_mode) --
        if "custom_sets" in main_mode:
            # TM Test / Deload: use custom set structure
            for s in main_mode["custom_sets"]:
                w = round_to_plate(tm * s["pct"])
                main_sets.append({"type": "normal", "weight_kg": w, "reps": s["reps"]})
        else:
            # Standard 531 working sets
            week_cfg = CYCLE_WEEKS.get(week_type, CYCLE_WEEKS[1])
            reps_override = main_mode.get("reps_override")  # 5's PRO = 5
            for s in week_cfg["sets"]:
                w = round_to_plate(tm * s["pct"])
                reps = s["reps"]
                if reps_override:
                    reps = reps_override
                elif isinstance(reps, str):
                    # AMRAP: show minimum reps in routine
                    reps = int(reps.replace("+", ""))
                main_sets.append({"type": "normal", "weight_kg": w, "reps": reps})

        # -- Supplemental sets --
        has_supplemental = (
            supp_key != "none"
            and (supp_tmpl.get("sets_per_session", 0) > 0 or "week_spec" in supp_tmpl)
        )
        if has_supplemental:
            # Resolve supplemental percentage
            # physical_week for template rotation, week_type for FSL percentages
            supp_pct = get_supplemental_pct(supp_key, physical_week, cycle_in_phase, lift, tm)

            if supp_pct is None:
                # FSL/Widowmaker: use first working set percentage (follows week_type)
                supp_pct = get_fsl_pct(week_type)

            supp_w = round_to_plate(tm * supp_pct)

            # Handle SVR II, Pervertor and other mixed templates
            if supp_tmpl.get("pct_source") == "mixed" and "week_spec" in supp_tmpl:
                ws = supp_tmpl["week_spec"].get(physical_week, {})
                n_sets = ws.get("sets", 5)
                reps = ws.get("reps", 10)
                if isinstance(reps, str):
                    reps = 20  # "15-20" → show 20 as target
                if ws.get("pct_source") == "fsl":
                    supp_w = round_to_plate(tm * get_fsl_pct(week_type))
                elif "pct" in ws:
                    supp_w = round_to_plate(tm * ws["pct"])
            else:
                n_sets = supp_tmpl.get("sets_per_session", 5)
                reps = supp_tmpl.get("reps_per_set", 10)

            for _ in range(n_sets):
                main_sets.append({"type": "normal", "weight_kg": supp_w, "reps": reps})

    # Rest time: longer for DL/Squat
    rest = 180 if lift in ("deadlift", "squat") else 120

    # ── Build session notes for Hevy ──
    notes = _build_session_notes(
        plan_pos, lift, tm, week_type, supp_key, main_mode_key,
        replaces_main, cycle_in_phase, physical_week=physical_week,
    )

    exercises = [{
        "exercise_template_id": tid,
        "rest_seconds": rest,
        "sets": main_sets,
        "notes": notes,
    }]

    # ── Accessories (phase-aware from config) ──
    # get_day_accessories handles deload/TM test internally (returns minimal)
    accessories = get_day_accessories(day_num, plan_pos)
    exercises.extend(accessories)

    return exercises


def _get_manual_accessories(routine_id: str, day_num: int, main_tid: str,
                            headers: dict) -> list:
    """
    Fetch current routine from Hevy and extract manually-added accessories.

    Returns exercise dicts for exercises that are:
    - NOT the main lift
    - NOT in DAY_ACCESSORIES for this day (those are re-generated)
    """
    import requests
    try:
        r = requests.get(
            f"https://api.hevyapp.com/v1/routines/{routine_id}",
            headers=headers
        )
        if not r.ok:
            return []
    except Exception:
        return []

    routine = r.json().get("routine", r.json())
    current_exercises = routine.get("exercises", [])

    # Build set of template_ids that are "managed" (main + all possible accessories)
    managed_tids = {main_tid}
    # All TIDs managed by get_day_accessories (any phase)
    managed_tids.update(_ACC_TIDS.values())

    manual = []
    for ex in current_exercises:
        tid = ex.get("exercise_template_id", "")
        if tid not in managed_tids:
            # Preserve this exercise as-is (sets, rest, notes, etc.)
            manual.append({
                "exercise_template_id": tid,
                "rest_seconds": ex.get("rest_seconds", 60),
                "sets": [
                    {k: v for k, v in s.items() if v is not None}
                    for s in ex.get("sets", [])
                ],
            })

    return manual


def update_hevy_routines(df: pd.DataFrame) -> dict:
    """
    Update all 4 routines in Hevy with correct weights for the current
    week/cycle using Forever 5/3/1 framework.

    Uses get_plan_position() to determine the active template (Leader/Anchor/
    7th Week Deload/TM Test) and builds routines accordingly.

    Returns {day_num: {status, phase, week, block, lift, tm, template}}.
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

    # Determine current position using Forever framework
    if df.empty:
        total_sessions = 0
    else:
        total_sessions = df["hevy_id"].nunique()

    plan_pos = get_plan_position(total_sessions)
    week_type = plan_pos.get("week_type", 1)
    tm_bumps = plan_pos.get("tm_bumps_total", 0)
    phase = plan_pos.get("phase", "pre_plan")
    block = plan_pos.get("block")
    block_name = block["name"] if block else "Pre-plan"

    # For legacy pre-plan, also get macro_num for backwards compat
    macro_num = plan_pos.get("macro_num", 1) if phase == "pre_plan" else (
        plan_pos.get("block_num", 1)
    )

    results = {}

    for day_num, routine_id in DAY_ROUTINE_MAP.items():
        day_cfg = DAY_CONFIG_531.get(day_num, {})
        lift = day_cfg.get("main_lift", "?")
        effective_tm = get_effective_tm(lift, tm_bumps)

        # Build title with phase info
        base_title = day_cfg.get("name", f"531 día {day_num}")
        phase_tag = {
            "pre_plan": "",
            "leader": "L",
            "7th_week_deload": "DL",
            "anchor": "A",
            "7th_week_tm_test": "TM",
        }.get(phase, "")
        title = f"{base_title} [{phase_tag}]" if phase_tag else base_title

        exercises = build_routine_exercises(
            day_num, week_type, macro_num, tm_bumps, plan_pos=plan_pos
        )
        if not exercises:
            results[day_num] = {"status": "skipped", "reason": "no TM"}
            continue

        # Preserve manually-added accessories from current routine
        main_tid = MAIN_LIFT_TIDS.get(lift, "")
        manual_accs = _get_manual_accessories(
            routine_id, day_num, main_tid, headers
        )
        if manual_accs:
            exercises.extend(manual_accs)

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
                    "phase": phase,
                    "week": plan_pos.get("week_name", "?"),
                    "block": block_name,
                    "tm": effective_tm,
                    "tm_bumps": tm_bumps,
                    "template": plan_pos.get("supplemental_template", "?"),
                    "main_work": plan_pos.get("main_work_mode", "?"),
                    "preserved_accessories": len(manual_accs),
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


def attach_calendar_dates(calendar: list[dict]) -> tuple[list[dict], dict]:
    """
    Annotate each week dict with start_date/end_date based on real session
    dates (past) or pace projection (future).

    Returns:
        (calendar_with_dates, pace_info)
    """
    from datetime import date, timedelta
    from src.config_531 import PROGRAM_START_531

    program_start = date.fromisoformat(PROGRAM_START_531)

    # --- Assign dates from real sessions for completed/partial/current weeks ---
    for w in calendar:
        sessions = w.get("sessions", [])
        if sessions:
            dates = []
            for s in sessions:
                d = s["date"]
                if isinstance(d, str):
                    d = date.fromisoformat(d[:10])
                elif hasattr(d, "date"):  # datetime → date
                    d = d.date()
                dates.append(d)
            w["start_date"] = min(dates)
            w["end_date"] = max(dates)
        else:
            w["start_date"] = None
            w["end_date"] = None

    # --- Compute pace from completed weeks with real dates ---
    dated_weeks = [w for w in calendar if w["start_date"] is not None]
    if len(dated_weeks) >= 2:
        first_start = dated_weeks[0]["start_date"]
        last_start = dated_weeks[-1]["start_date"]
        total_days = (last_start - first_start).days
        avg_days = total_days / (len(dated_weeks) - 1)
        avg_days = max(avg_days, 4.0)  # floor: can't train faster than ~4 days/week
        is_fallback = False
    else:
        avg_days = 7.0
        is_fallback = True

    # --- Fill in dates for undated weeks ---
    # Find anchor: last dated week, or use PROGRAM_START_531
    if dated_weeks:
        anchor_date = dated_weeks[-1]["end_date"]
        anchor_idx = calendar.index(dated_weeks[-1])
    else:
        # No sessions yet — anchor week 1 to program start
        anchor_date = program_start - timedelta(days=1)  # so W1 starts at program_start
        anchor_idx = -1

    # Forward-fill future weeks
    cursor = anchor_date
    for w in calendar[anchor_idx + 1:]:
        if w["start_date"] is None:
            w["start_date"] = cursor + timedelta(days=1)
            w["end_date"] = w["start_date"] + timedelta(days=int(avg_days) - 1)
            cursor = w["end_date"]

    # Back-fill any early undated weeks (edge case: current week has no sessions yet)
    for i in range(len(calendar)):
        w = calendar[i]
        if w["start_date"] is None:
            if w["status"] == "current":
                w["start_date"] = date.today()
                w["end_date"] = date.today()
            elif i > 0 and calendar[i - 1]["end_date"]:
                w["start_date"] = calendar[i - 1]["end_date"] + timedelta(days=1)
                w["end_date"] = w["start_date"] + timedelta(days=int(avg_days) - 1)
            else:
                w["start_date"] = program_start
                w["end_date"] = program_start + timedelta(days=int(avg_days) - 1)

    # Projected end date = end_date of last week
    projected_end = calendar[-1]["end_date"] if calendar else None

    pace_info = {
        "avg_days_per_week": round(avg_days, 1),
        "completed_weeks_count": len(dated_weeks),
        "projected_end_date": projected_end,
        "is_fallback_pace": is_fallback,
        "program_start": program_start,
    }

    return calendar, pace_info


def build_annual_calendar(df: pd.DataFrame, year: int = 2026) -> dict:
    """
    Build annual calendar grid ready for visualization.

    Returns grid data structure for both Streamlit and Notion.
    """
    from src.config_531 import CYCLE_WEEKS

    cal = training_calendar(df, weeks_ahead=52)

    # Color mapping
    type_colors = {
        "Semana 5s": "#3b82f6",      # Azul
        "Semana 3s": "#f59e0b",      # Amarillo/naranja
        "Semana 531": "#ef4444",     # Rojo
        "Deload": "#22c55e",         # Verde
    }

    weeks_data = []
    for w in cal:
        # Determine border color based on status
        if w["status"] == "completed":
            border = "#166534"  # Verde oscuro
        elif w["status"] == "current":
            border = "#2563eb"  # Azul
        elif w["status"] == "partial":
            border = "#ea580c"  # Naranja
        else:
            border = "#9ca3af"  # Gris

        weeks_data.append({
            "abs_week": w["abs_week"],
            "macro_num": w["macro_num"],
            "week_in_macro": w["week_in_macro"],
            "week_name": w["week_name"],
            "week_type": w["week_type"],
            "type": w["week_name"].replace("Semana ", "").lower(),  # "5s", "3s", "531", "deload"
            "status": w["status"],
            "is_deload": w["is_deload"],
            "is_bump_week": w["is_bump_week"],
            "tm_bumps": w["tm_bumps"],
            "tms": w["tms"],
            "sessions_done": w["sessions_done"],
            "color": type_colors.get(w["week_name"], "#6b7280"),
            "border_color": border,
        })

    current_week = next((w["abs_week"] for w in weeks_data if w["status"] == "current"), 1)

    return {
        "year": year,
        "weeks": weeks_data,
        "current_week": current_week,
        "total_macros": max(w["macro_num"] for w in weeks_data),
    }


def build_enriched_annual_calendar(df: pd.DataFrame, year: int = 2026) -> dict:
    """
    Annual calendar enriched with Forever plan context (block, phase, template, weights).

    Returns same structure as build_annual_calendar plus:
      - Each week dict gets: block_num, block_name, phase, phase_label,
        supplemental_name, main_work_name, tm_pct, week_weights
      - Top-level "months" key: list of 12 dicts with month_name, primary_block, subtitle
    """
    from datetime import date, timedelta
    from src.config_531 import (
        get_plan_position, SESSIONS_PER_WEEK, SUPPLEMENTAL_TEMPLATES,
        MAIN_WORK_MODES, expected_weights, TRAINING_MAX,
    )

    base = build_annual_calendar(df, year=year)
    if not base["weeks"]:
        return base

    # Merge session data from training_calendar (build_annual_calendar strips it)
    # and attach real calendar dates based on actual session pace
    raw_cal = training_calendar(df, weeks_ahead=52)
    raw_cal, pace_info = attach_calendar_dates(raw_cal)
    sessions_by_week = {w["abs_week"]: w for w in raw_cal}
    for w in base["weeks"]:
        raw_w = sessions_by_week.get(w["abs_week"], {})
        w["sessions"] = raw_w.get("sessions", [])
        w["start_date"] = raw_w.get("start_date")
        w["end_date"] = raw_w.get("end_date")

    phase_labels = {
        "pre_plan": "Pre-Plan",
        "leader": "Leader",
        "anchor": "Anchor",
        "7th_week_deload": "7th Week Deload",
        "7th_week_tm_test": "7th Week TM Test",
    }

    lifts = list(TRAINING_MAX.keys())

    for w in base["weeks"]:
        session_offset = (w["abs_week"] - 1) * SESSIONS_PER_WEEK
        pos = get_plan_position(session_offset)

        block = pos.get("block") or {}
        w["block_num"] = pos.get("block_num", 0)
        w["block_name"] = block.get("name", "Pre-Plan") if block else "Pre-Plan"
        w["phase"] = pos.get("phase", "pre_plan")
        w["phase_label"] = phase_labels.get(w["phase"], w["phase"])

        supp_key = pos.get("supplemental_template", "")
        main_key = pos.get("main_work_mode", "")
        w["supplemental_name"] = SUPPLEMENTAL_TEMPLATES.get(supp_key, {}).get("name", supp_key)
        w["main_work_name"] = MAIN_WORK_MODES.get(main_key, {}).get("name", main_key)
        w["tm_pct"] = block.get("tm_pct", 85) if block else 85

        # Expected weights for upcoming weeks (main work sets)
        if w["status"] == "upcoming" and w["week_type"] in (1, 2, 3):
            w["week_weights"] = {}
            for lift in lifts:
                tm_val = w["tms"].get(lift)
                if tm_val:
                    w["week_weights"][lift] = expected_weights(lift, w["week_type"], tm_override=tm_val)
        else:
            w["week_weights"] = {}

    # Build month summaries using real/projected dates (not hardcoded Jan 1)
    from collections import Counter
    month_names = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    # Group weeks by the month of their start_date
    month_buckets: dict[int, list] = {i: [] for i in range(12)}
    for w in base["weeks"]:
        sd = w.get("start_date")
        if sd and sd.year == year:
            month_buckets[sd.month - 1].append(w)

    months = []
    for m_idx in range(12):
        month_weeks = month_buckets[m_idx]

        if month_weeks:
            block_counts = Counter(w["block_num"] for w in month_weeks)
            primary_block_num = block_counts.most_common(1)[0][0]
            primary = next((w for w in month_weeks if w["block_num"] == primary_block_num), month_weeks[0])
            subtitle = f"{month_names[m_idx]} {year}"
            if primary["block_num"] > 0:
                subtitle += f" — Bloque {primary['block_num']}: {primary['block_name']} · {primary['phase_label']}"
            else:
                subtitle += " — Pre-Plan · Beyond 5/3/1"

            block_nums = [w["block_num"] for w in month_weeks]
            has_transition = len(set(block_nums)) > 1
        else:
            subtitle = f"{month_names[m_idx]} {year}"
            has_transition = False

        months.append({
            "month_idx": m_idx,
            "month_name": month_names[m_idx],
            "subtitle": subtitle,
            "has_transition": has_transition,
            "weeks": month_weeks,
        })

    base["months"] = months
    base["pace"] = pace_info
    return base


def get_kanban_data(df: pd.DataFrame) -> dict:
    """
    Get data for Kanban columns: todo, done, upcoming.
    
    Returns:
        {
            "todo": [{"lift", "weight", "sets", "reps", "week", "macro"}, ...],
            "done": [...],
            "upcoming": [...],
        }
    """
    from src.config_531 import (
        DAY_CONFIG_531, CYCLE_WEEKS, SESSIONS_PER_WEEK,
        get_cycle_position, get_effective_tm
    )
    
    if df.empty:
        return {"todo": [], "done": [], "upcoming": []}
    
    lifts = ["ohp", "deadlift", "bench", "squat"]
    lift_names = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
    
    total_sessions = df["hevy_id"].nunique()
    current_pos = get_cycle_position(total_sessions)
    
    # Get current week data
    current_week_data = None
    for w in training_calendar(df, weeks_ahead=4):
        if w["status"] == "current":
            current_week_data = w
            break
    
    if not current_week_data:
        return {"todo": [], "done": [], "upcoming": []}
    
    # Determine which lifts are done this week
    done_lifts = set()
    if current_week_data["sessions"]:
        for s in current_week_data["sessions"]:
            done_lifts.add(s["lift"])
    
    # Build todo (current week, not done)
    todo = []
    week_type = current_week_data["week_type"]
    week_config = CYCLE_WEEKS.get(week_type, {})
    
    for lift in lifts:
        if lift not in done_lifts:
            tm = current_week_data["tms"].get(lift, 0)
            sets_config = week_config.get("sets", [])
            
            # Format: "5×5" or "5/3/1+"
            if len(sets_config) == 3:
                reps_str = f"{sets_config[0]['reps']}/{sets_config[1]['reps']}/{sets_config[2]['reps']}"
            else:
                reps_str = f"{sets_config[0]['reps']}×5" if sets_config else "?"
            
            todo.append({
                "lift": lift,
                "lift_name": lift_names[lift],
                "weight": tm,
                "sets": len(sets_config),
                "reps": reps_str,
                "week": current_week_data["abs_week"],
                "macro": current_week_data["macro_num"],
                "week_name": current_week_data["week_name"],
            })
    
    # Build done (current week, completed)
    done = []
    for lift in done_lifts:
        tm = current_week_data["tms"].get(lift, 0)
        done.append({
            "lift": lift,
            "lift_name": lift_names.get(lift, lift),
            "weight": tm,
            "sets": 3,  # Simplificado
            "reps": "✓",
            "week": current_week_data["abs_week"],
            "macro": current_week_data["macro_num"],
            "week_name": current_week_data["week_name"],
        })
    
    # Build upcoming (next week)
    upcoming = []
    next_week = None
    for w in training_calendar(df, weeks_ahead=4):
        if w["abs_week"] == current_week_data["abs_week"] + 1:
            next_week = w
            break
    
    if next_week:
        week_type = next_week["week_type"]
        week_config = CYCLE_WEEKS.get(week_type, {})
        for lift in lifts:
            tm = next_week["tms"].get(lift, 0)
            sets_config = week_config.get("sets", [])
            if len(sets_config) == 3:
                reps_str = f"{sets_config[0]['reps']}/{sets_config[1]['reps']}/{sets_config[2]['reps']}"
            else:
                reps_str = f"{sets_config[0]['reps']}×5" if sets_config else "?"
            
            upcoming.append({
                "lift": lift,
                "lift_name": lift_names[lift],
                "weight": tm,
                "sets": len(sets_config),
                "reps": reps_str,
                "week": next_week["abs_week"],
                "macro": next_week["macro_num"],
                "week_name": next_week["week_name"],
            })
    
    return {"todo": todo, "done": done, "upcoming": upcoming}


# ═════════════════════════════════════════════════════════════════════
# PHASE 4: 531-NATIVE INTELLIGENCE
# ═════════════════════════════════════════════════════════════════════

def amrap_performance_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare AMRAP reps at the same %TM across mini-cycles.

    Groups AMRAPs by lift + week_type (5s/3s/531) so you compare
    apples to apples: same prescription, increasing TM.
    If reps hold or climb despite heavier weight → real strength gain.
    If reps drop → TM might be outpacing actual strength.

    Returns one row per (lift, week_type, mini_cycle) with reps, weight,
    e1RM, and deltas vs the previous occurrence of that same week_type.
    """
    amraps = df[df["set_type"] == "amrap"].copy()
    if amraps.empty or "week_type" not in amraps.columns:
        return pd.DataFrame()

    # Filter to actual working weeks (not deload)
    amraps = amraps[amraps["week_type"].isin([1, 2, 3])].copy()
    if amraps.empty:
        return pd.DataFrame()

    week_labels = {1: "5s", 2: "3s", 3: "5/3/1"}

    # One AMRAP per lift per session — take the best if multiple
    grouped = (
        amraps.sort_values("e1rm", ascending=False)
        .drop_duplicates(subset=["date", "lift"])
        .sort_values("date")
    )

    # Build comparison rows
    rows = []
    for (lift, wtype), grp in grouped.groupby(["lift", "week_type"]):
        grp = grp.sort_values("date").reset_index(drop=True)
        for i, row in grp.iterrows():
            entry = {
                "lift": lift,
                "week_type": wtype,
                "week_label": week_labels.get(wtype, "?"),
                "date": row["date"],
                "mini_cycle": row.get("mini_cycle"),
                "macro_num": row.get("macro_num", 1),
                "weight_kg": row["weight_kg"],
                "reps": row["reps"],
                "e1rm": row["e1rm"],
                "pct_of_tm": row.get("pct_of_tm"),
                "effective_tm": row.get("effective_tm"),
            }
            # Deltas vs previous same week_type
            if i > 0:
                prev = grp.iloc[i - 1]
                entry["reps_delta"] = row["reps"] - prev["reps"]
                entry["e1rm_delta"] = round(row["e1rm"] - prev["e1rm"], 1)
                entry["weight_delta"] = row["weight_kg"] - prev["weight_kg"]
            else:
                entry["reps_delta"] = None
                entry["e1rm_delta"] = None
                entry["weight_delta"] = None
            rows.append(entry)

    result = pd.DataFrame(rows)
    return result.sort_values(["lift", "week_type", "date"]).reset_index(drop=True)


def tm_sustainability(df: pd.DataFrame) -> dict:
    """
    Per-lift TM health check based on AMRAP trends.

    Rules (Wendler):
    - 5s week AMRAP < 5 reps → TM too high
    - 3s week AMRAP < 3 reps → TM too high
    - 531 week AMRAP < 1 rep → TM way too high
    - Declining reps at same week_type across cycles → TM outpacing strength

    Returns dict with per-lift verdicts and an overall system health score.
    """
    api = amrap_performance_index(df)
    if api.empty:
        return {"lifts": {}, "system_health": None}

    min_reps_map = {1: 5, 2: 3, 3: 1}  # week_type → absolute minimum
    target_reps_map = {1: 8, 2: 6, 3: 3}  # week_type → healthy target

    lifts_result = {}
    for lift in api["lift"].unique():
        lift_data = api[api["lift"] == lift].copy()
        latest_per_week = (
            lift_data.sort_values("date")
            .drop_duplicates(subset=["week_type"], keep="last")
        )

        alerts = []
        scores = []

        for _, row in latest_per_week.iterrows():
            wt = row["week_type"]
            reps = row["reps"]
            minimum = min_reps_map.get(wt, 1)
            target = target_reps_map.get(wt, 5)
            label = row["week_label"]

            if reps < minimum:
                alerts.append(f"🔴 {label}: {reps} reps (mínimo {minimum})")
                scores.append(0.0)
            elif reps < target:
                alerts.append(f"🟡 {label}: {reps} reps (objetivo ≥{target})")
                scores.append(0.5)
            else:
                scores.append(1.0)

        # Trend: are reps declining for the most common week_type?
        trend_status = "stable"
        for wt in [1, 2, 3]:
            wt_data = lift_data[lift_data["week_type"] == wt].sort_values("date")
            if len(wt_data) >= 2:
                reps_list = wt_data["reps"].tolist()
                if reps_list[-1] < reps_list[-2]:
                    trend_status = "declining"
                elif reps_list[-1] > reps_list[-2]:
                    trend_status = "improving"
                break  # Use the first week_type with enough data

        avg_score = sum(scores) / len(scores) if scores else None
        if avg_score is not None:
            if avg_score >= 0.8:
                verdict = "🟢 TM sostenible"
            elif avg_score >= 0.4:
                verdict = "🟡 Vigilar"
            else:
                verdict = "🔴 Recalibrar TM"
        else:
            verdict = "⬜ Sin datos"

        lifts_result[lift] = {
            "verdict": verdict,
            "score": round(avg_score, 2) if avg_score is not None else None,
            "trend": trend_status,
            "alerts": alerts,
            "n_amraps": len(lift_data),
        }

    # System-wide health
    all_scores = [v["score"] for v in lifts_result.values() if v["score"] is not None]
    system_health = round(sum(all_scores) / len(all_scores), 2) if all_scores else None

    return {"lifts": lifts_result, "system_health": system_health}


def joker_analysis(df: pd.DataFrame) -> dict:
    """
    Joker set analysis: frequency, intensity, and trends.

    Joker sets are optional heavy singles/doubles AFTER the AMRAP.
    Overusing them adds fatigue without program benefit.
    Underusing them misses PR opportunities on good days.
    """
    jokers = df[df["set_type"] == "joker"].copy()
    all_sessions = df.drop_duplicates("hevy_id")

    total_sessions = len(all_sessions)
    sessions_with_jokers = jokers["hevy_id"].nunique() if not jokers.empty else 0
    frequency_pct = round(sessions_with_jokers / total_sessions * 100, 1) if total_sessions > 0 else 0

    if jokers.empty:
        return {
            "total_joker_sets": 0,
            "sessions_with_jokers": 0,
            "total_sessions": total_sessions,
            "frequency_pct": 0,
            "per_lift": {},
            "assessment": "Sin joker sets registrados",
        }

    # Per-lift breakdown
    per_lift = {}
    for lift in jokers["lift"].dropna().unique():
        lj = jokers[jokers["lift"] == lift].sort_values("date")
        lift_sessions = df[df["lift"] == lift].drop_duplicates("hevy_id")

        # Weight relative to TM
        pct_of_tm_list = []
        for _, row in lj.iterrows():
            tm = row.get("effective_tm")
            if tm and tm > 0:
                pct_of_tm_list.append(round(row["weight_kg"] / tm * 100, 1))

        per_lift[lift] = {
            "count": len(lj),
            "sessions": lj["hevy_id"].nunique(),
            "lift_sessions": len(lift_sessions),
            "best_weight": lj["weight_kg"].max(),
            "best_e1rm": round(lj["e1rm"].max(), 1),
            "avg_pct_of_tm": round(sum(pct_of_tm_list) / len(pct_of_tm_list), 1) if pct_of_tm_list else None,
            "dates": lj["date"].dt.strftime("%d/%m").tolist(),
        }

    # Assessment
    if frequency_pct > 60:
        assessment = "🟡 Alta frecuencia — cuidado con la fatiga acumulada"
    elif frequency_pct > 20:
        assessment = "🟢 Uso equilibrado — aprovechando días buenos"
    elif frequency_pct > 0:
        assessment = "🔵 Uso conservador — podrías aprovechar más los días buenos"
    else:
        assessment = "⬜ Sin joker sets"

    return {
        "total_joker_sets": len(jokers),
        "sessions_with_jokers": sessions_with_jokers,
        "total_sessions": total_sessions,
        "frequency_pct": frequency_pct,
        "per_lift": per_lift,
        "assessment": assessment,
    }


def bbb_fatigue_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Track rep drop-off within BBB 5×10 sets and across sessions.

    Within a session: are later sets losing reps? (e.g., 10,10,10,9,8)
    Across sessions: is the average reps trend declining as BBB% increases?

    Returns one row per BBB session with fatigue metrics.
    """
    bbb = df[df["set_type"].str.startswith("bbb")].copy()
    if bbb.empty:
        return pd.DataFrame()

    rows = []
    for (hevy_id, lift), grp in bbb.groupby(["hevy_id", "lift"]):
        grp = grp.sort_values("set_number")
        reps_list = grp["reps"].tolist()
        n_sets = len(reps_list)
        if n_sets == 0:
            continue

        avg_reps = sum(reps_list) / n_sets
        first_half = reps_list[:n_sets // 2] if n_sets >= 4 else reps_list[:1]
        second_half = reps_list[n_sets // 2:] if n_sets >= 4 else reps_list[1:]

        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0
        rep_dropoff = round(avg_first - avg_second, 1)

        # % of TM
        tm = grp["effective_tm"].iloc[0] if "effective_tm" in grp.columns else None
        pct_tm = round(grp["weight_kg"].iloc[0] / tm * 100, 1) if tm and tm > 0 else None

        rows.append({
            "date": grp["date"].iloc[0],
            "lift": lift,
            "hevy_id": hevy_id,
            "weight_kg": grp["weight_kg"].iloc[0],
            "n_sets": n_sets,
            "reps_list": reps_list,
            "avg_reps": round(avg_reps, 1),
            "rep_dropoff": rep_dropoff,
            "min_reps": min(reps_list),
            "all_tens": all(r >= 10 for r in reps_list),
            "pct_of_tm": pct_tm,
            "macro_num": grp["macro_num"].iloc[0] if "macro_num" in grp.columns else None,
        })

    result = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # Overall fatigue classification per session
    def _classify(row):
        if row["all_tens"]:
            return "🟢 Sin fatiga"
        elif row["rep_dropoff"] <= 1:
            return "🟡 Fatiga leve"
        else:
            return "🔴 Fatiga alta"

    if not result.empty:
        result["fatigue_status"] = result.apply(_classify, axis=1)

    return result


def true_1rm_trend(df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimated true 1RM over time, derived from AMRAP performance.

    The TM is NOT your 1RM — it's a training tool at ~85-90% of true max.
    This function estimates actual 1RM from AMRAP e1RMs, which is a much
    better indicator of real strength than the programmed TM.

    Returns one row per AMRAP with estimated true 1RM and trend.
    """
    amraps = df[df["set_type"] == "amrap"].copy()
    if amraps.empty:
        return pd.DataFrame()

    # One best AMRAP per lift per session
    best = (
        amraps.sort_values("e1rm", ascending=False)
        .drop_duplicates(subset=["date", "lift"])
        .sort_values("date")
    )

    rows = []
    for lift in best["lift"].unique():
        lift_data = best[best["lift"] == lift].sort_values("date").reset_index(drop=True)
        for i, row in lift_data.iterrows():
            entry = {
                "date": row["date"],
                "lift": lift,
                "weight_kg": row["weight_kg"],
                "reps": row["reps"],
                "estimated_1rm": round(row["e1rm"], 1),
                "effective_tm": row.get("effective_tm"),
                "macro_num": row.get("macro_num", 1),
            }
            # TM as % of estimated 1RM
            if entry["effective_tm"] and entry["estimated_1rm"] > 0:
                entry["tm_as_pct_of_1rm"] = round(
                    entry["effective_tm"] / entry["estimated_1rm"] * 100, 1
                )
            else:
                entry["tm_as_pct_of_1rm"] = None

            # Delta vs previous
            if i > 0:
                prev = lift_data.iloc[i - 1]
                entry["e1rm_delta"] = round(row["e1rm"] - prev["e1rm"], 1)
            else:
                entry["e1rm_delta"] = None

            rows.append(entry)

    result = pd.DataFrame(rows)

    # Running max (all-time best) per lift
    if not result.empty:
        result["running_max"] = result.groupby("lift")["estimated_1rm"].cummax()

    return result.sort_values(["lift", "date"]).reset_index(drop=True)
