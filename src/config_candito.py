"""
Candito Linear Program (Strength/Control) — Configuration

Upper/Lower split, 4 days/week. Linear progression.
Heavy days (Mon/Tue) + Control days (Thu/Fri).
"""
import os
from src.config import BODYWEIGHT

# ── Hevy / Notion IDs ────────────────────────────────────────────────
CANDITO_FOLDER_ID = 2492173
NOTION_CANDITO_LOGBOOK_DB = os.environ.get(
    "NOTION_CANDITO_LOGBOOK_DB", "31dcbc49-9cfe-815a-8a18-f91635269054"
)
NOTION_CANDITO_ANALYTICS_PAGE = os.environ.get(
    "NOTION_CANDITO_ANALYTICS_PAGE", "31dcbc49-9cfe-8127-b575-e62e982cd57a"
)

PROGRAM_START_CANDITO = "2026-03-08"

# ── Routine IDs (Hevy) ──────────────────────────────────────────────
DAY_ROUTINE_MAP_CANDITO = {
    1: "969f09e8-1543-4223-bec2-f297165fd69f",  # Heavy Lower
    2: "870754f3-1dfc-4218-a53f-6d990529566c",  # Heavy Upper
    3: "21a96ce8-47a2-45dc-843a-cf14127e3ff5",  # Control Lower
    4: "1707512c-8873-462c-a8b2-477e9626b19d",  # Control Upper
}

# ── Day Configuration ────────────────────────────────────────────────
DAY_CONFIG_CANDITO = {
    1: {
        "name": "Heavy Lower",
        "type": "heavy",
        "focus": "lower",
        "emoji": "🦵",
    },
    2: {
        "name": "Heavy Upper",
        "type": "heavy",
        "focus": "upper",
        "emoji": "💪",
    },
    3: {
        "name": "Control Lower",
        "type": "control",
        "focus": "lower",
        "emoji": "🎯",
    },
    4: {
        "name": "Control Upper",
        "type": "control",
        "focus": "upper",
        "emoji": "🎯",
    },
}

# ── Starting Weights (Week 0) ───────────────────────────────────────
# Calculated from 531 session data (March 2026).
# Heavy: ~75-77% of e1RM. Control: ~65% of e1RM (pause variants).
STARTING_WEIGHTS = {
    # Heavy day compounds (3×6 or 2×6)
    "zercher_squat":    60.0,
    "deadlift":         115.0,
    "bench":            82.5,
    "pendlay_row":      65.0,
    "ohp":              47.5,
    # Control day pause variants (6×4 or 3×4)
    "pause_zercher":    52.5,
    "pause_deadlift":   105.0,
    "spoto_press":      72.5,
    "pause_pendlay":    57.5,
    # Accessories (static starting weights)
    "shrug":            80.0,
    "farmer_walk":      30.0,
    "lateral_raise":    10.0,
    "skullcrusher":     30.0,
    "barbell_curl":     30.0,
    "face_pull":        30.0,
    "hammer_curl":      14.0,
}

# ── Progression Rules ────────────────────────────────────────────────
# "auto": system checks if all prescribed reps were completed.
# If yes → suggest increment. If no → keep weight.
# If 2 consecutive sessions at same weight with incomplete reps → flag stall.
PROGRESSION_INCREMENT = {
    # Upper body: +2.5 kg/week
    "bench":          2.5,
    "ohp":            2.5,
    "pendlay_row":    2.5,
    "spoto_press":    2.5,
    "pause_pendlay":  2.5,
    # Lower body: +5 kg/week
    "zercher_squat":  5.0,
    "deadlift":       5.0,
    "pause_zercher":  5.0,
    "pause_deadlift": 5.0,
}

# ── Exercise Database ────────────────────────────────────────────────
# Keyed by exercise_template_id (Hevy).
EXERCISE_DB_CANDITO = {
    # ── Heavy Lower (Day 1) ──────────────────────────────────────
    "40C6A9FC": {
        "name": "Zercher Squat",
        "day": 1,
        "role": "main",
        "lift_key": "zercher_squat",
        "muscle_group": "Piernas",
        "prescribed": {"sets": 3, "reps": 6},
        "is_compound": True,
    },
    "C6272009": {
        "name": "Deadlift (Barbell)",
        "day": 1,
        "role": "main",
        "lift_key": "deadlift",
        "muscle_group": "Espalda Baja",
        "prescribed": {"sets": 2, "reps": 6},
        "is_compound": True,
    },
    "0B841777": {
        "name": "Shrug (Barbell)",
        "day": [1, 3],
        "role": "optional",
        "lift_key": "shrug",
        "muscle_group": "Traps",
        "prescribed": {"sets": 3, "reps": 10},
        "is_compound": False,
    },
    "50C613D0": {
        "name": "Farmers Walk",
        "day": 1,
        "role": "optional",
        "lift_key": "farmer_walk",
        "muscle_group": "Agarre",
        "prescribed": {"sets": 3, "reps": 1},
        "is_compound": True,
    },

    # ── Heavy Upper (Day 2) ──────────────────────────────────────
    "E644F828": {
        "name": "Bench Press - Wide Grip (Barbell)",
        "day": 2,
        "role": "main",
        "lift_key": "bench",
        "muscle_group": "Pecho",
        "prescribed": {"sets": 3, "reps": 6},
        "is_compound": True,
    },
    "018ADC12": {
        "name": "Pendlay Row (Barbell)",
        "day": 2,
        "role": "main",
        "lift_key": "pendlay_row",
        "muscle_group": "Espalda",
        "prescribed": {"sets": 3, "reps": 6},
        "is_compound": True,
    },
    "073032BB": {
        "name": "OHP (Barbell)",
        "day": 2,
        "role": "secondary",
        "lift_key": "ohp",
        "muscle_group": "Hombros",
        "prescribed": {"sets": 1, "reps": 6},
        "is_compound": True,
    },
    "1B2B1E7C": {
        "name": "Pull Up",
        "day": 2,
        "role": "secondary",
        "lift_key": "pullup",
        "muscle_group": "Espalda",
        "prescribed": {"sets": 1, "reps": 6},
        "is_compound": True,
    },
    "422B08F1": {
        "name": "Lateral Raise (Dumbbell)",
        "day": 2,
        "role": "optional",
        "lift_key": "lateral_raise",
        "muscle_group": "Hombros",
        "prescribed": {"sets": 3, "reps": 12},
        "is_compound": False,
    },
    "875F585F": {
        "name": "Skullcrusher (Barbell)",
        "day": 2,
        "role": "optional",
        "lift_key": "skullcrusher",
        "muscle_group": "Tríceps",
        "prescribed": {"sets": 3, "reps": 10},
        "is_compound": False,
    },

    # ── Control Lower (Day 3) ────────────────────────────────────
    "f1f57ae8-c50a-4cec-90c2-021bf945074b": {
        "name": "Pause Zercher Squat",
        "day": 3,
        "role": "main",
        "lift_key": "pause_zercher",
        "muscle_group": "Piernas",
        "prescribed": {"sets": 6, "reps": 4},
        "is_compound": True,
    },
    "fbca8cd7-d4d6-4da5-8172-c52db7ec52f5": {
        "name": "Pause Deadlift (Barbell)",
        "day": 3,
        "role": "main",
        "lift_key": "pause_deadlift",
        "muscle_group": "Espalda Baja",
        "prescribed": {"sets": 3, "reps": 4},
        "is_compound": True,
    },
    # Shrug (0B841777) also on Day 3 — handled via day=[1,3]
    "A5AC6449": {
        "name": "Barbell Curl",
        "day": 3,
        "role": "optional",
        "lift_key": "barbell_curl",
        "muscle_group": "Bíceps",
        "prescribed": {"sets": 3, "reps": 10},
        "is_compound": False,
    },

    # ── Control Upper (Day 4) ────────────────────────────────────
    "700f3066-0a0d-4775-91c7-5acdc8806295": {
        "name": "Spoto Press (Barbell)",
        "day": 4,
        "role": "main",
        "lift_key": "spoto_press",
        "muscle_group": "Pecho",
        "prescribed": {"sets": 6, "reps": 4},
        "is_compound": True,
    },
    "cf43f778-cb52-4370-9658-122c665abc45": {
        "name": "Pause Pendlay Row (Barbell)",
        "day": 4,
        "role": "main",
        "lift_key": "pause_pendlay",
        "muscle_group": "Espalda",
        "prescribed": {"sets": 6, "reps": 4},
        "is_compound": True,
    },
    "BE640BA0": {
        "name": "Face Pull",
        "day": 4,
        "role": "optional",
        "lift_key": "face_pull",
        "muscle_group": "Hombros",
        "prescribed": {"sets": 3, "reps": 15},
        "is_compound": False,
    },
    "7E3BC8B6": {
        "name": "Hammer Curl (Dumbbell)",
        "day": 4,
        "role": "optional",
        "lift_key": "hammer_curl",
        "muscle_group": "Bíceps",
        "prescribed": {"sets": 3, "reps": 10},
        "is_compound": False,
    },
}

# ── Main lift template IDs (for quick lookups) ──────────────────────
MAIN_LIFT_TIDS = {
    "zercher_squat":  "40C6A9FC",
    "deadlift":       "C6272009",
    "bench":          "E644F828",
    "pendlay_row":    "018ADC12",
    "ohp":            "073032BB",
    "pause_zercher":  "f1f57ae8-c50a-4cec-90c2-021bf945074b",
    "pause_deadlift": "fbca8cd7-d4d6-4da5-8172-c52db7ec52f5",
    "spoto_press":    "700f3066-0a0d-4775-91c7-5acdc8806295",
    "pause_pendlay":  "cf43f778-cb52-4370-9658-122c665abc45",
}

# Reverse: tid → lift_key
TID_TO_LIFT = {v: k for k, v in MAIN_LIFT_TIDS.items()}

# ── Strength Standards (multiples of BW) ────────────────────────────
STRENGTH_STANDARDS_CANDITO = {
    "zercher_squat":  {"beginner": 0.50, "intermediate": 0.85, "advanced": 1.25, "elite": 1.60},
    "deadlift":       {"beginner": 1.00, "intermediate": 1.50, "advanced": 2.00, "elite": 2.50},
    "bench":          {"beginner": 0.50, "intermediate": 1.00, "advanced": 1.50, "elite": 2.00},
    "pendlay_row":    {"beginner": 0.50, "intermediate": 0.85, "advanced": 1.20, "elite": 1.50},
    "ohp":            {"beginner": 0.35, "intermediate": 0.65, "advanced": 1.00, "elite": 1.25},
    "spoto_press":    {"beginner": 0.45, "intermediate": 0.90, "advanced": 1.35, "elite": 1.80},
    "pause_deadlift": {"beginner": 0.85, "intermediate": 1.30, "advanced": 1.80, "elite": 2.25},
}

# ── Compound pairs (Heavy ↔ Control) ────────────────────────────────
LIFT_PAIRS = {
    "zercher_squat":  "pause_zercher",
    "deadlift":       "pause_deadlift",
    "bench":          "spoto_press",
    "pendlay_row":    "pause_pendlay",
}


def round_to_plate(weight: float) -> float:
    """Round weight to nearest 2.5kg (Juan's gym plates)."""
    return round(weight / 2.5) * 2.5
