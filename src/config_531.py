"""
531 BBB Analytics — Configuration

Wendler's 5/3/1 Boring But Big program configuration.
Training Maxes, cycle percentages, exercise mapping.
"""
import os

# ── Hevy / Notion IDs ────────────────────────────────────────────────
BBB_FOLDER_ID = 2401466
NOTION_531_LOGBOOK_DB = os.environ.get(
    "NOTION_531_LOGBOOK_DB", "31e7df96-6afb-4b58-a34c-817cb2bf887d"
)
NOTION_531_ANALYTICS_PAGE = os.environ.get(
    "NOTION_531_ANALYTICS_PAGE", "30dcbc49-9cfe-81fb-8d7e-ebe669b303be"
)

# ── Physical ─────────────────────────────────────────────────────────
BODYWEIGHT = 86.0
PROGRAM_START_531 = "2026-02-20"

# ── Training Maxes (updated each cycle) ──────────────────────────────
# TM = ~90% of true 1RM. Updated after each 3-week cycle.
# None = not yet established (waiting for first session)
TRAINING_MAX = {
    "ohp":      58,     # From BBB Day 1 data: 85% x 50kg → TM ≈ 58
    "deadlift": 140,    # From BBD data: e1RM 156kg → TM ≈ 140
    "bench":    76,     # From BBD data: e1RM 85kg (64x10) → TM ≈ 76
    "squat":    80,     # Conservative: no back squat history, based on front sq/zercher
}

# TM increment per cycle
TM_INCREMENT = {
    "ohp":      2,     # Upper body: +2 kg/cycle (smallest: 1kg/side)
    "deadlift": 4,     # Lower body: +4 kg/cycle (2kg/side)
    "bench":    2,
    "squat":    4,
}

# ── 531 Cycle Structure — Beyond 5/3/1 ───────────────────────────────
# Macro cycle = 7 weeks: 3 working + 3 working + 1 deload
# TM bumps after each 3-week mini-cycle (+2kg upper, +4kg lower)
# No deload between mini-cycles — deload only on week 7.
#
# Week 1: 5s   (mini-cycle A)
# Week 2: 3s   (mini-cycle A)
# Week 3: 531  (mini-cycle A) → bump TM
# Week 4: 5s   (mini-cycle B, new TM)
# Week 5: 3s   (mini-cycle B)
# Week 6: 531  (mini-cycle B) → bump TM
# Week 7: Deload
MACRO_CYCLE_LENGTH = 7  # weeks in a full macro cycle
WORKING_BLOCK_LENGTH = 3  # weeks in each working mini-cycle
SESSIONS_PER_WEEK = 4  # one session per main lift (OHP, DL, Bench, Squat)

CYCLE_WEEKS = {
    1: {  # "5s week"
        "name": "Semana 5s",
        "sets": [
            {"pct": 0.65, "reps": 5},
            {"pct": 0.75, "reps": 5},
            {"pct": 0.85, "reps": "5+"},  # AMRAP
        ],
    },
    2: {  # "3s week"
        "name": "Semana 3s",
        "sets": [
            {"pct": 0.70, "reps": 3},
            {"pct": 0.80, "reps": 3},
            {"pct": 0.90, "reps": "3+"},  # AMRAP
        ],
    },
    3: {  # "1s week" / "531 week"
        "name": "Semana 531",
        "sets": [
            {"pct": 0.75, "reps": 5},
            {"pct": 0.85, "reps": 3},
            {"pct": 0.95, "reps": "1+"},  # AMRAP
        ],
    },
    4: {  # Deload (only used on week 7 of macro)
        "name": "Deload",
        "sets": [
            {"pct": 0.40, "reps": 5},
            {"pct": 0.50, "reps": 5},
            {"pct": 0.60, "reps": 5},
        ],
    },
}

# BBB supplemental percentages progression across cycles
BBB_PCT_PROGRESSION = {
    1: 0.50,  # First cycle: 50% of TM
    2: 0.55,
    3: 0.60,  # Progression ceiling for most
    4: 0.60,
    5: 0.65,
    6: 0.70,  # Advanced only
}

# ── Day Configuration ────────────────────────────────────────────────
# Maps BBB day number → main lift + metadata
# Day order matches Juan's Hevy routine setup
DAY_CONFIG_531 = {
    1: {
        "name": "BBB Día 1 - OHP",
        "main_lift": "ohp",
        "focus": "Press + Hombros",
        "color": "#f97316",
    },
    2: {
        "name": "BBB Día 2 - Deadlift",
        "main_lift": "deadlift",
        "focus": "Peso Muerto",
        "color": "#ef4444",
    },
    3: {
        "name": "BBB Día 3 - Bench",
        "main_lift": "bench",
        "focus": "Press de Banca",
        "color": "#3b82f6",
    },
    4: {
        "name": "BBB Día 4 - Zercher",
        "main_lift": "squat",
        "focus": "Sentadilla Zercher",
        "color": "#22c55e",
    },
}

# ── Exercise Template IDs (from Hevy) ────────────────────────────────
# Main lifts — these are the 531 working sets
MAIN_LIFT_TIDS = {
    "ohp":      "073032BB",   # Press Militar de Pie (Barra)
    "deadlift": "C6272009",   # Peso Muerto (Barra)
    "bench":    "E644F828",   # Press de Banca - Agarre Abierto (Barra)
    "squat":    "40C6A9FC",   # Zercher Squat (replaces Back Squat D04AC939)
}

# Reverse lookup: template_id → lift name
TID_TO_LIFT = {v: k for k, v in MAIN_LIFT_TIDS.items() if v}

# ── Exercise Database (531 context) ──────────────────────────────────
# All exercises that appear in BBB workouts
EXERCISE_DB_531 = {
    # Main lifts
    "073032BB": {
        "name": "OHP (Barbell)",
        "role": "main",
        "lift": "ohp",
        "muscle_group": "Hombros",
    },
    "C6272009": {
        "name": "Deadlift (Barbell)",
        "role": "main",
        "lift": "deadlift",
        "muscle_group": "Espalda Baja",
    },
    "E644F828": {
        "name": "Bench Press (Barbell)",
        "role": "main",
        "lift": "bench",
        "muscle_group": "Pecho",
    },
    "40C6A9FC": {
        "name": "Zercher Squat",
        "role": "main",
        "lift": "squat",
        "muscle_group": "Piernas",
    },
    "D04AC939": {
        "name": "Squat (Barbell)",
        "role": "historical",  # Replaced by Zercher Squat
        "lift": "squat",
        "muscle_group": "Piernas",
    },
    # Accessories from Day 1
    "0B841777": {
        "name": "Shrug (Barbell)",
        "role": "accessory",
        "muscle_group": "Trapecios",
    },
    "875F585F": {
        "name": "Skullcrusher (Barbell)",
        "role": "accessory",
        "muscle_group": "Tríceps",
    },
    "23A48484": {
        "name": "Cable Crunch",
        "role": "accessory",
        "muscle_group": "Core",
    },
}

# Workouts done without routine_id that should be included
EXCEPTION_WORKOUT_IDS = {
    "edf3607a-8a50-470c-ae79-7d1b739d8c5d",  # BBB Day 1 — 2026-02-20 (first session, logged manually)
    "864e5e48-2e8f-491a-b7a8-a2b79797cf74",  # BBB Day 2 — 2026-02-21 (routine_id mismatch)
}

# ── Routine IDs in BBB folder ────────────────────────────────────────
BBB_ROUTINE_IDS = {
    "619fb49a-7d62-4de5-9567-86e616103b5b",  # BBB día 1 - OHP
    "47a7c25b-fac8-4979-b853-dc7284ca9e80",  # BBB día 2 - Deadlift
    "5bec1b7b-25d8-4c84-be6e-35f915a9a3fc",  # BBB día 3 - Bench
    "331eb58f-e25e-47c0-b375-5e526ceab5e1",  # BBB día 4 - Squat
}

# Ordered map: day_num → routine_id (for updating routines)
DAY_ROUTINE_MAP = {
    1: "619fb49a-7d62-4de5-9567-86e616103b5b",  # OHP
    2: "47a7c25b-fac8-4979-b853-dc7284ca9e80",  # Deadlift
    3: "5bec1b7b-25d8-4c84-be6e-35f915a9a3fc",  # Bench
    4: "331eb58f-e25e-47c0-b375-5e526ceab5e1",  # Squat
}

# Accessory templates per day (kept static, Juan adjusts weights manually)
DAY_ACCESSORIES = {
    1: [  # OHP day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
    ],
    2: [  # DL day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
    ],
    3: [  # Bench day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
    ],
    4: [  # Squat day
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
    ],
}

# ── Strength Standards (Wendler-style, multiples of BW) ──────────────
STRENGTH_STANDARDS_531 = {
    "ohp":      {"beginner": 0.35, "intermediate": 0.65, "advanced": 1.00, "elite": 1.25},
    "deadlift": {"beginner": 1.00, "intermediate": 1.50, "advanced": 2.00, "elite": 2.50},
    "bench":    {"beginner": 0.50, "intermediate": 1.00, "advanced": 1.50, "elite": 2.00},
    "squat":    {"beginner": 0.50, "intermediate": 0.85, "advanced": 1.25, "elite": 1.60},  # Zercher Squat
}


def get_tm(lift: str) -> float | None:
    """Get current Training Max for a lift."""
    return TRAINING_MAX.get(lift)


def round_to_plate(weight: float) -> float:
    """Round weight to nearest 2kg (Juan's smallest increment: 1kg per side)."""
    return round(weight / 2) * 2


def get_cycle_position(total_sessions: int) -> dict:
    """
    Calculate current position in the Beyond 5/3/1 macro cycle.

    Beyond scheme: 3 working weeks + 3 working weeks + 1 deload = 7-week macro.
    TM bumps after each 3-week mini-cycle (after week 3 and week 6).

    Each 'week' = 4 training sessions (one per main lift).

    Returns:
        week_in_macro: 1-7 (position in 7-week macro)
        week_type: 1, 2, or 3 (maps to 5s, 3s, 531) or 4 (deload)
        mini_cycle: 1 or 2 (which 3-week block we're in, or None for deload)
        macro_num: which macro cycle we're on (1-based)
        tm_bumps_completed: how many TM bumps have occurred
    """
    completed_weeks = total_sessions // 4
    macro_num = (completed_weeks // MACRO_CYCLE_LENGTH) + 1
    week_in_macro = (completed_weeks % MACRO_CYCLE_LENGTH) + 1  # 1-7

    if week_in_macro <= 3:
        # Mini-cycle A
        week_type = week_in_macro  # 1=5s, 2=3s, 3=531
        mini_cycle = 1
    elif week_in_macro <= 6:
        # Mini-cycle B
        week_type = week_in_macro - 3  # 1=5s, 2=3s, 3=531
        mini_cycle = 2
    else:
        # Deload (week 7)
        week_type = 4
        mini_cycle = None

    # TM bumps: one after each completed 3-week block
    # Completed blocks = completed full 3-week sections
    total_completed_blocks = 0
    for m in range(macro_num):
        if m < macro_num - 1:
            total_completed_blocks += 2  # Previous macros contributed 2 blocks each
        else:
            # Current macro
            if week_in_macro > 3:
                total_completed_blocks += 1  # Finished mini-cycle A
            if week_in_macro > 6:
                total_completed_blocks += 1  # Finished mini-cycle B

    return {
        "week_in_macro": week_in_macro,
        "week_type": week_type,
        "week_name": CYCLE_WEEKS.get(week_type, {}).get("name", "?"),
        "mini_cycle": mini_cycle,
        "macro_num": macro_num,
        "tm_bumps_completed": total_completed_blocks,
        "completed_weeks": completed_weeks,
    }


def get_effective_tm(lift: str, tm_bumps: int) -> float:
    """
    Calculate the effective TM for a lift after N bumps from the base TM.
    Base TM is stored in TRAINING_MAX (set at program start).
    Each bump adds TM_INCREMENT for that lift.
    """
    base = TRAINING_MAX.get(lift, 0) or 0
    increment = TM_INCREMENT.get(lift, 2)
    return base + (increment * tm_bumps)


def expected_weights(lift: str, week: int, tm_override: float = None) -> list[dict] | None:
    """
    Get expected working set weights for a lift on a given cycle week.
    Returns list of {weight, reps, pct} or None if TM not set.
    """
    tm = tm_override or get_tm(lift)
    if tm is None:
        return None
    week_config = CYCLE_WEEKS.get(week)
    if not week_config:
        return None
    result = []
    for s in week_config["sets"]:
        result.append({
            "weight": round_to_plate(tm * s["pct"]),
            "reps": s["reps"],
            "pct": s["pct"],
        })
    return result

