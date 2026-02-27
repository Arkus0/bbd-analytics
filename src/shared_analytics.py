"""
BBD Analytics — Shared utilities for both BBD and 531 programs.

Features:
- Exercise substitution detection
- Workout quality score
- Shareable workout card generation (PNG)
"""
import io
from datetime import datetime
from typing import Optional

import pandas as pd


# ═════════════════════════════════════════════════════════════════════
# 1. AUTO-DETECT EXERCISE SUBSTITUTIONS
# ═════════════════════════════════════════════════════════════════════

def detect_unknown_exercises(
    df: pd.DataFrame,
    known_db: dict,
    program_name: str = "BBD",
) -> pd.DataFrame:
    """
    Find exercises in workout data that aren't in the known exercise database.

    These are potential substitutions Juan made without updating config.
    Returns a DataFrame with: template_id, hevy_name, first_seen, last_seen,
    session_count, total_sets, suggested_day, suggested_muscle_group.

    Args:
        df: Workout DataFrame (must have exercise_template_id, exercise columns)
        known_db: EXERCISE_DB or EXERCISE_DB_531 dict
        program_name: "BBD" or "531" for context
    """
    if df.empty or "exercise_template_id" not in df.columns:
        return pd.DataFrame()

    known_ids = set(known_db.keys())
    all_ids = set(df["exercise_template_id"].unique())
    unknown_ids = all_ids - known_ids - {""}  # exclude empty

    if not unknown_ids:
        return pd.DataFrame()

    rows = []
    for tid in unknown_ids:
        ex_data = df[df["exercise_template_id"] == tid]

        # Get Hevy exercise name (may be in Spanish)
        hevy_name = ex_data["exercise"].iloc[0] if "exercise" in ex_data.columns else "?"

        # Context: which days does it appear on?
        if "day_num" in ex_data.columns:
            days = sorted(ex_data["day_num"].dropna().unique().tolist())
        elif "lift" in ex_data.columns:
            days = sorted(ex_data["lift"].dropna().unique().tolist())
        else:
            days = []

        # Try to guess muscle group from name patterns
        name_lower = hevy_name.lower()
        if any(w in name_lower for w in ["curl", "bícep", "bicep"]):
            guess_mg = "Bíceps"
        elif any(w in name_lower for w in ["trícep", "tricep", "skull", "press francés"]):
            guess_mg = "Tríceps"
        elif any(w in name_lower for w in ["press", "bench", "banca", "pecho"]):
            guess_mg = "Pecho"
        elif any(w in name_lower for w in ["sentadilla", "squat", "pierna", "leg", "lunge"]):
            guess_mg = "Piernas"
        elif any(w in name_lower for w in ["pull", "row", "remo", "jalón", "lat"]):
            guess_mg = "Espalda"
        elif any(w in name_lower for w in ["hombro", "shoulder", "lateral", "ohp"]):
            guess_mg = "Hombros"
        elif any(w in name_lower for w in ["dead", "muerto", "trap", "shrug"]):
            guess_mg = "Espalda Baja"
        elif any(w in name_lower for w in ["abdom", "core", "plank"]):
            guess_mg = "Core"
        else:
            guess_mg = "?"

        rows.append({
            "template_id": tid,
            "hevy_name": hevy_name,
            "program": program_name,
            "first_seen": ex_data["date"].min(),
            "last_seen": ex_data["date"].max(),
            "session_count": ex_data["hevy_id"].nunique() if "hevy_id" in ex_data.columns else len(ex_data),
            "total_sets": len(ex_data),
            "appears_on": days,
            "suggested_muscle_group": guess_mg,
        })

    result = pd.DataFrame(rows).sort_values("session_count", ascending=False).reset_index(drop=True)
    return result


# ═════════════════════════════════════════════════════════════════════
# 2. WORKOUT QUALITY SCORE
# ═════════════════════════════════════════════════════════════════════

def workout_quality_531(df: pd.DataFrame) -> pd.DataFrame:
    """
    Composite quality score per 531 session (0-100).

    Components:
    - AMRAP Score (40%): reps over minimum → 0-40 points
    - BBB Completion (30%): 5 sets × 10 reps = 100% → 0-30 points
    - Accessory Coverage (15%): ≥2 accessories = full → 0-15 points
    - Volume Consistency (15%): vs rolling avg → 0-15 points
    """
    if df.empty:
        return pd.DataFrame()

    # Pre-compute rolling average volume (4-session window)
    session_vols = (
        df.groupby("hevy_id")
        .agg(date=("date", "first"), total_vol=("volume_kg", "sum"))
        .sort_values("date")
    )
    session_vols["rolling_avg"] = session_vols["total_vol"].rolling(4, min_periods=1).mean()
    vol_map = session_vols[["rolling_avg"]].to_dict()["rolling_avg"]

    rows = []
    for hid, grp in df.groupby("hevy_id"):
        date = grp["date"].iloc[0]
        title = grp["workout_title"].iloc[0] if "workout_title" in grp.columns else ""
        lift = grp[grp["is_main_lift"] == True]["lift"].iloc[0] if "is_main_lift" in grp.columns and grp["is_main_lift"].any() else "?"

        # ── AMRAP Score (0-40) ──
        amraps = grp[grp["set_type"] == "amrap"]
        if not amraps.empty:
            best_amrap = amraps.loc[amraps["e1rm"].idxmax()]
            reps = best_amrap["reps"]
            wic = best_amrap.get("week_in_cycle", 1)
            from src.config_531 import CYCLE_WEEKS
            week_cfg = CYCLE_WEEKS.get(wic, {})
            sets_cfg = week_cfg.get("sets", [])
            min_reps = int(str(sets_cfg[-1].get("reps", "5+")).replace("+", "")) if sets_cfg else 5

            reps_over = reps - min_reps
            # 0 reps over = 20pts, each extra rep = +4pts, max 40
            amrap_score = min(40, max(0, 20 + reps_over * 4))
        else:
            amrap_score = 0

        # ── BBB Completion (0-30) ──
        bbb = grp[grp["set_type"].str.startswith("bbb")] if "set_type" in grp.columns else pd.DataFrame()
        if not bbb.empty:
            bbb_sets = len(bbb)
            bbb_avg_reps = bbb["reps"].mean()
            # 5 sets × 10 reps target
            set_score = min(1.0, bbb_sets / 5)
            rep_score = min(1.0, bbb_avg_reps / 10)
            bbb_score = round(set_score * rep_score * 30)
        else:
            bbb_score = 0

        # ── Accessory Coverage (0-15) ──
        acc = grp[~grp.get("is_main_lift", pd.Series(False, index=grp.index))]
        non_bbb_acc = acc[~acc["set_type"].str.startswith("bbb")] if "set_type" in acc.columns else acc
        n_accessories = non_bbb_acc["exercise"].nunique() if "exercise" in non_bbb_acc.columns else 0
        acc_score = min(15, round(n_accessories / 2 * 15))  # 2+ accessories = full

        # ── Volume Consistency (0-15) ──
        session_vol = grp["volume_kg"].sum()
        rolling = vol_map.get(hid, session_vol)
        if rolling > 0:
            vol_ratio = session_vol / rolling
            # 0.85-1.15 = full points, taper outside
            if 0.85 <= vol_ratio <= 1.15:
                vol_score = 15
            elif 0.7 <= vol_ratio <= 1.3:
                vol_score = 10
            else:
                vol_score = 5
        else:
            vol_score = 10

        total = amrap_score + bbb_score + acc_score + vol_score

        rows.append({
            "date": date,
            "hevy_id": hid,
            "title": title,
            "lift": lift,
            "quality_score": total,
            "amrap_score": amrap_score,
            "bbb_score": bbb_score,
            "acc_score": acc_score,
            "vol_score": vol_score,
            "amrap_reps": amraps["reps"].iloc[0] if not amraps.empty else 0,
            "bbb_sets": len(bbb),
            "n_accessories": n_accessories,
            "total_volume": int(session_vol),
            "grade": _grade(total),
        })

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def workout_quality_bbd(df: pd.DataFrame, day_config: dict, exercise_db: dict) -> pd.DataFrame:
    """
    Composite quality score per BBD session (0-100).

    Components:
    - Key Lift Performance (35%): e1RM vs recent best → 0-35 points
    - Volume (25%): vs rolling avg → 0-25 points
    - Exercise Coverage (25%): planned exercises done → 0-25 points
    - Consistency (15%): session duration within normal range → 0-15 points
    """
    if df.empty:
        return pd.DataFrame()

    # Rolling avg volume per session
    session_vols = (
        df.groupby("hevy_id")
        .agg(date=("date", "first"), total_vol=("volume_kg", "sum"))
        .sort_values("date")
    )
    session_vols["rolling_avg"] = session_vols["total_vol"].rolling(4, min_periods=1).mean()
    vol_map = session_vols[["rolling_avg"]].to_dict()["rolling_avg"]

    # Best e1RM per exercise (running)
    running_best = {}

    rows = []
    for hid, grp in df.sort_values("date").groupby("hevy_id", sort=False):
        date = grp["date"].iloc[0]
        day_num = grp["day_num"].iloc[0] if "day_num" in grp.columns else None
        day_cfg = day_config.get(day_num, {}) if day_num else {}

        # ── Key Lift Performance (0-35) ──
        key_ids = {tid for tid, e in exercise_db.items() if e.get("is_key_lift")}
        key_rows = grp[grp["exercise_template_id"].isin(key_ids)]
        if not key_rows.empty:
            best_e1rm = key_rows["e1rm"].max()
            ex_id = key_rows.loc[key_rows["e1rm"].idxmax(), "exercise_template_id"]
            prev_best = running_best.get(ex_id, best_e1rm)
            ratio = best_e1rm / prev_best if prev_best > 0 else 1.0
            # PR = 35, match = 25, slight drop = 15, big drop = 5
            if ratio >= 1.0:
                lift_score = 35
            elif ratio >= 0.95:
                lift_score = 25
            elif ratio >= 0.90:
                lift_score = 15
            else:
                lift_score = 5
            # Update running best
            for _, kr in key_rows.iterrows():
                eid = kr["exercise_template_id"]
                running_best[eid] = max(running_best.get(eid, 0), kr["e1rm"])
        else:
            lift_score = 10

        # ── Volume (0-25) ──
        session_vol = grp["volume_kg"].sum()
        rolling = vol_map.get(hid, session_vol)
        if rolling > 0:
            vol_ratio = session_vol / rolling
            if 0.85 <= vol_ratio <= 1.15:
                vol_score = 25
            elif 0.7 <= vol_ratio <= 1.3:
                vol_score = 17
            else:
                vol_score = 8
        else:
            vol_score = 15

        # ── Exercise Coverage (0-25) ──
        if day_num:
            planned_ids = {tid for tid, e in exercise_db.items() if e.get("day") == day_num}
            done_ids = set(grp["exercise_template_id"].unique())
            if planned_ids:
                coverage = len(done_ids & planned_ids) / len(planned_ids)
                cov_score = round(coverage * 25)
            else:
                cov_score = 15
        else:
            cov_score = 15

        # ── Consistency (0-15) ──
        duration = grp["duration_min"].iloc[0] if "duration_min" in grp.columns else 0
        if 40 <= duration <= 90:
            dur_score = 15
        elif 30 <= duration <= 120:
            dur_score = 10
        else:
            dur_score = 5

        total = lift_score + vol_score + cov_score + dur_score

        rows.append({
            "date": date,
            "hevy_id": hid,
            "day_num": day_num,
            "day_name": day_cfg.get("name", f"Día {day_num}"),
            "quality_score": total,
            "lift_score": lift_score,
            "vol_score": vol_score,
            "cov_score": cov_score,
            "dur_score": dur_score,
            "total_volume": int(session_vol),
            "n_exercises": grp["exercise"].nunique() if "exercise" in grp.columns else 0,
            "duration_min": duration,
            "grade": _grade(total),
        })

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def _grade(score: int) -> str:
    """Map numeric score to letter grade."""
    if score >= 90:
        return "S"
    elif score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 35:
        return "D"
    return "F"


def quality_trend(quality_df: pd.DataFrame) -> dict:
    """Compute quality trend stats from a quality DataFrame."""
    if quality_df.empty:
        return {"avg": 0, "trend": "stable", "best": 0, "worst": 0, "n": 0}

    scores = quality_df["quality_score"]
    avg = round(scores.mean(), 1)
    best = int(scores.max())
    worst = int(scores.min())

    # Trend: last 3 vs first 3
    if len(scores) >= 6:
        first3 = scores.head(3).mean()
        last3 = scores.tail(3).mean()
        if last3 > first3 + 5:
            trend = "improving"
        elif last3 < first3 - 5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {"avg": avg, "trend": trend, "best": best, "worst": worst, "n": len(scores)}


# ═════════════════════════════════════════════════════════════════════
# 3. SHAREABLE WORKOUT CARDS (PNG)
# ═════════════════════════════════════════════════════════════════════

def generate_workout_card(session_data: dict, program: str = "531") -> bytes:
    """
    Generate a shareable PNG workout card for a single session.

    Args:
        session_data: dict with session info (keys depend on program)
        program: "531" or "BBD"

    Returns:
        PNG image as bytes
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("Pillow required: pip install Pillow")

    # ── Card dimensions ──
    W, H = 1080, 1350  # Instagram story-friendly
    BG = "#0f172a"      # Dark slate
    ACCENT = "#f59e0b" if program == "531" else "#ef4444"
    TEXT = "#e2e8f0"
    MUTED = "#94a3b8"

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts — use system defaults, PIL handles it
    try:
        font_xl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except (IOError, OSError):
        font_xl = font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    y = 50

    # ── Header bar ──
    draw.rectangle([0, 0, W, 120], fill=ACCENT)
    program_label = "5/3/1 BBB" if program == "531" else "BACKED BY DEADLIFTS"
    draw.text((W // 2, 60), program_label, font=font_xl, fill=BG, anchor="mm")

    y = 160

    # ── Date + Title ──
    date_str = session_data.get("date", "")
    if isinstance(date_str, pd.Timestamp):
        date_str = date_str.strftime("%d %b %Y")
    title = session_data.get("title", "Sesión")
    draw.text((W // 2, y), date_str, font=font_md, fill=MUTED, anchor="mm")
    y += 50
    draw.text((W // 2, y), title, font=font_lg, fill=TEXT, anchor="mm")
    y += 70

    # ── Divider ──
    draw.line([(80, y), (W - 80, y)], fill=ACCENT, width=3)
    y += 40

    if program == "531":
        # ── AMRAP highlight ──
        amrap_w = session_data.get("amrap_weight", 0)
        amrap_r = session_data.get("amrap_reps", 0)
        amrap_e1rm = session_data.get("amrap_e1rm", 0)
        lift = session_data.get("lift", "").upper()

        draw.text((W // 2, y), "AMRAP", font=font_md, fill=ACCENT, anchor="mm")
        y += 55
        big_text = f"{amrap_w:.0f}kg × {amrap_r}"
        draw.text((W // 2, y), big_text, font=font_xl, fill=TEXT, anchor="mm")
        y += 65
        draw.text((W // 2, y), f"e1RM: {amrap_e1rm:.0f} kg", font=font_md, fill=MUTED, anchor="mm")
        y += 60

        # ── BBB summary ──
        bbb_sets = session_data.get("bbb_sets", 0)
        bbb_weight = session_data.get("bbb_weight", 0)
        bbb_reps = session_data.get("bbb_avg_reps", 0)
        if bbb_sets > 0:
            draw.line([(80, y), (W - 80, y)], fill="#334155", width=1)
            y += 30
            draw.text((W // 2, y), "BBB SUPPLEMENTAL", font=font_sm, fill=ACCENT, anchor="mm")
            y += 40
            draw.text((W // 2, y), f"{bbb_sets}×{bbb_reps:.0f} @ {bbb_weight:.0f}kg",
                      font=font_lg, fill=TEXT, anchor="mm")
            y += 55

    else:  # BBD
        # ── Key lift highlight ──
        exercise = session_data.get("exercise", "")
        top_set = session_data.get("top_set", "")
        e1rm = session_data.get("e1rm", 0)

        draw.text((W // 2, y), "TOP SET", font=font_md, fill=ACCENT, anchor="mm")
        y += 55
        draw.text((W // 2, y), exercise, font=font_lg, fill=TEXT, anchor="mm")
        y += 55
        draw.text((W // 2, y), top_set, font=font_xl, fill=TEXT, anchor="mm")
        y += 65
        draw.text((W // 2, y), f"e1RM: {e1rm:.0f} kg", font=font_md, fill=MUTED, anchor="mm")
        y += 60

    # ── Stats grid ──
    draw.line([(80, y), (W - 80, y)], fill="#334155", width=1)
    y += 40

    stats = session_data.get("stats", {})
    col_w = (W - 160) // max(len(stats), 1)
    for i, (label, value) in enumerate(stats.items()):
        cx = 80 + col_w * i + col_w // 2
        draw.text((cx, y), str(value), font=font_lg, fill=TEXT, anchor="mm")
        draw.text((cx, y + 45), label, font=font_xs, fill=MUTED, anchor="mm")

    y += 100

    # ── Quality score badge ──
    quality = session_data.get("quality_score")
    if quality is not None:
        draw.line([(80, y), (W - 80, y)], fill="#334155", width=1)
        y += 40
        grade = session_data.get("grade", _grade(quality))

        # Score circle
        cx = W // 2
        r = 60
        # Color by grade
        grade_colors = {"S": "#f59e0b", "A": "#10b981", "B": "#3b82f6",
                       "C": "#8b5cf6", "D": "#f97316", "F": "#ef4444"}
        circle_color = grade_colors.get(grade, ACCENT)
        draw.ellipse([cx - r, y - r + 60, cx + r, y + r + 60], outline=circle_color, width=4)
        draw.text((cx, y + 60), grade, font=font_xl, fill=circle_color, anchor="mm")
        draw.text((cx, y + r + 80), f"Quality Score: {quality}/100", font=font_sm, fill=MUTED, anchor="mm")
        y += r + 120

    # ── Footer ──
    draw.rectangle([0, H - 60, W, H], fill="#1e293b")
    draw.text((W // 2, H - 30), "BBD Analytics", font=font_xs, fill=MUTED, anchor="mm")

    # ── Export ──
    buf = io.BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf.getvalue()


def build_card_data_531(df: pd.DataFrame, hevy_id: str) -> Optional[dict]:
    """Extract session data for a 531 workout card."""
    session = df[df["hevy_id"] == hevy_id]
    if session.empty:
        return None

    amraps = session[session["set_type"] == "amrap"]
    bbb = session[session["set_type"].str.startswith("bbb")]
    acc = session[~session.get("is_main_lift", pd.Series(False, index=session.index))]

    lift_names = {"ohp": "OHP", "deadlift": "Peso Muerto", "bench": "Banca", "squat": "Sentadilla"}
    lift = session[session["is_main_lift"] == True]["lift"].iloc[0] if session["is_main_lift"].any() else "?"

    return {
        "date": session["date"].iloc[0],
        "title": session["workout_title"].iloc[0] if "workout_title" in session.columns else lift_names.get(lift, lift),
        "lift": lift,
        "amrap_weight": amraps["weight_kg"].iloc[0] if not amraps.empty else 0,
        "amrap_reps": int(amraps["reps"].iloc[0]) if not amraps.empty else 0,
        "amrap_e1rm": round(amraps["e1rm"].iloc[0], 1) if not amraps.empty else 0,
        "bbb_sets": len(bbb),
        "bbb_weight": bbb["weight_kg"].iloc[0] if not bbb.empty else 0,
        "bbb_avg_reps": round(bbb["reps"].mean(), 1) if not bbb.empty else 0,
        "stats": {
            "Volumen": f"{int(session['volume_kg'].sum()):,}kg",
            "Sets": str(len(session)),
            "Ejercicios": str(session["exercise"].nunique()),
        },
    }


def build_card_data_bbd(df: pd.DataFrame, hevy_id: str, exercise_db: dict) -> Optional[dict]:
    """Extract session data for a BBD workout card."""
    session = df[df["hevy_id"] == hevy_id]
    if session.empty:
        return None

    key_ids = {tid for tid, e in exercise_db.items() if e.get("is_key_lift")}
    key_rows = session[session["exercise_template_id"].isin(key_ids)]

    if not key_rows.empty:
        best = key_rows.loc[key_rows["e1rm"].idxmax()]
        exercise = best["exercise"]
        top_set = best.get("top_set", f"{best['max_weight']}kg × {best['max_reps_at_max']}")
        e1rm = best["e1rm"]
    else:
        best = session.loc[session["e1rm"].idxmax()] if session["e1rm"].max() > 0 else session.iloc[0]
        exercise = best["exercise"]
        top_set = best.get("top_set", "")
        e1rm = best["e1rm"]

    day_num = session["day_num"].iloc[0] if "day_num" in session.columns else None

    return {
        "date": session["date"].iloc[0],
        "title": session["day_name"].iloc[0] if "day_name" in session.columns else f"Día {day_num}",
        "exercise": exercise,
        "top_set": top_set,
        "e1rm": round(e1rm, 1),
        "stats": {
            "Volumen": f"{int(session['volume_kg'].sum()):,}kg",
            "Sets": str(session["n_sets"].sum()),
            "Ejercicios": str(session["exercise"].nunique()),
            "Duración": f"{session['duration_min'].iloc[0]:.0f}m",
        },
    }
