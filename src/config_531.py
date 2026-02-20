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
    "bench":    None,    # TBD — Juan hasn't done bench day yet
    "squat":    None,    # TBD — Juan hasn't done squat day yet
}

# TM increment per cycle
TM_INCREMENT = {
    "ohp":      2.5,   # Upper body: +2.5 kg/cycle
    "deadlift": 5.0,   # Lower body: +5 kg/cycle
    "bench":    2.5,
    "squat":    5.0,
}

# ── 531 Cycle Structure ──────────────────────────────────────────────
# Each cycle = 3 working weeks + 1 deload (optional)
# Percentages are of Training Max
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
    3: {  # "1s week"
        "name": "Semana 1s",
        "sets": [
            {"pct": 0.75, "reps": 5},
            {"pct": 0.85, "reps": 3},
            {"pct": 0.95, "reps": "1+"},  # AMRAP
        ],
    },
    4: {  # Deload
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
        "name": "BBB Día 4 - Squat",
        "main_lift": "squat",
        "focus": "Sentadilla",
        "color": "#22c55e",
    },
}

# ── Exercise Template IDs (from Hevy) ────────────────────────────────
# Main lifts — these are the 531 working sets
MAIN_LIFT_TIDS = {
    "ohp":      "073032BB",   # Press Militar de Pie (Barra)
    "deadlift": "C6272009",   # Peso Muerto (Barra)
    "bench":    "E644F828",   # Press de Banca - Agarre Abierto (Barra)
    "squat":    None,         # TBD — will set when Juan creates squat routine
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
}

# ── Routine IDs in BBB folder ────────────────────────────────────────
BBB_ROUTINE_IDS = {
    "619fb49a-7d62-4de5-9567-86e616103b5b",  # BBB día 1
    # More will be added as Juan creates routines for days 2-4
}

# ── Strength Standards (Wendler-style, multiples of BW) ──────────────
STRENGTH_STANDARDS_531 = {
    "ohp":      {"beginner": 0.35, "intermediate": 0.65, "advanced": 1.00, "elite": 1.25},
    "deadlift": {"beginner": 1.00, "intermediate": 1.50, "advanced": 2.00, "elite": 2.50},
    "bench":    {"beginner": 0.50, "intermediate": 1.00, "advanced": 1.50, "elite": 2.00},
    "squat":    {"beginner": 0.75, "intermediate": 1.25, "advanced": 1.75, "elite": 2.25},
}


def get_tm(lift: str) -> float | None:
    """Get current Training Max for a lift."""
    return TRAINING_MAX.get(lift)


def round_to_plate(weight: float) -> float:
    """Round weight to nearest 2kg (Juan's smallest increment: 1kg per side)."""
    return round(weight / 2) * 2


def expected_weights(lift: str, week: int) -> list[dict] | None:
    """
    Get expected working set weights for a lift on a given cycle week.
    Returns list of {weight, reps, pct} or None if TM not set.
    """
    tm = get_tm(lift)
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
