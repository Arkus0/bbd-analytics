"""
BBD Analytics — Configuration v3 (template_id based)

ALL exercise matching uses exercise_template_id from Hevy API.
No more dependency on localized (Spanish) exercise names.
Names are only used for display, never for lookup.

Template IDs extracted from Hevy routines API 2026-02-13.
"""
import os

# ── API Keys ─────────────────────────────────────────────────────────
HEVY_API_KEY = os.environ.get("HEVY_API_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

# ── Notion IDs ───────────────────────────────────────────────────────
NOTION_BBD_LOGBOOK_DB = os.environ.get(
    "NOTION_BBD_LOGBOOK_DB", "ac92ba6b-bc18-464f-9f2b-2a7f82e6c443"
)
NOTION_ANALYTICS_PAGE = os.environ.get(
    "NOTION_ANALYTICS_PAGE", "306cbc49-9cfe-81b0-8aed-ce82d40289f6"
)
NOTION_SEGUIMIENTO_DB = os.environ.get(
    "NOTION_SEGUIMIENTO_DB", "63970d73-50f7-451b-8aed-10418a9f9c42"
)
NOTION_HALL_OF_TITANS_DB = os.environ.get(
    "NOTION_HALL_OF_TITANS_DB", "34d21307-2fb1-4686-910d-35f3fec1062f"
)

# ── Program Config ───────────────────────────────────────────────────
PROGRAM_START = "2026-02-12"
BODYWEIGHT = 86.0  # Default — overridden by get_bodyweight() if Seguimiento DB available

_cached_bodyweight: float | None = None


def get_bodyweight() -> float:
    """
    Get current bodyweight, trying Notion Seguimiento DB first.

    Falls back to hardcoded BODYWEIGHT if DB is not shared with integration
    or has no entries. Caches result for the process lifetime.
    """
    global _cached_bodyweight
    if _cached_bodyweight is not None:
        return _cached_bodyweight

    if NOTION_TOKEN and NOTION_SEGUIMIENTO_DB:
        try:
            import requests
            r = requests.post(
                f"https://api.notion.com/v1/databases/{NOTION_SEGUIMIENTO_DB}/query",
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={
                    "page_size": 1,
                    "sorts": [{"property": "Fecha", "direction": "descending"}],
                },
                timeout=5,
            )
            if r.ok:
                results = r.json().get("results", [])
                if results:
                    props = results[0].get("properties", {})
                    # Try common property names for weight
                    for name in ["Peso (kg)", "Peso", "Weight", "BW"]:
                        if name in props and props[name].get("number") is not None:
                            bw = props[name]["number"]
                            if 40 < bw < 200:  # sanity check
                                _cached_bodyweight = bw
                                return bw
        except Exception:
            pass

    _cached_bodyweight = BODYWEIGHT
    return BODYWEIGHT

DAY_CONFIG = {
    1: {"name": "Día 1 - Deadlift", "focus": "Deadlift + Piernas", "color": "#ef4444"},
    2: {"name": "Día 2 - Press", "focus": "Press + Hombros", "color": "#f97316"},
    3: {"name": "Día 3 - Brazos", "focus": "Brazos (opcional)", "color": "#eab308"},
    4: {"name": "Día 4 - Espalda", "focus": "Espalda + Trapecios", "color": "#3b82f6"},
    5: {"name": "Día 5 - Piernas", "focus": "Piernas", "color": "#22c55e"},
    6: {"name": "Día 6 - Press/Pecho", "focus": "Press + Pecho + Tríceps", "color": "#a855f7"},
}

# ═════════════════════════════════════════════════════════════════════
# EXERCISE DATABASE — keyed by exercise_template_id
#
# This is the SINGLE SOURCE OF TRUTH for all exercise metadata.
# Template IDs are stable across languages and never change.
# The "name" field is just a fallback label (English from routines).
# The actual display name comes from the workout data at runtime.
# ═════════════════════════════════════════════════════════════════════

EXERCISE_DB = {
    # ── Day 1 — Deadlift + Legs ─────────────────────────────────────
    "C6272009": {
        "name": "Deadlift (Barbell)",
        "day": 1,
        "muscle_group": "Espalda Baja",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 1.5, "adv": 2.0, "elite": 2.5},  # Conventional DL standards
    },
    "2B4B7310": {
        "name": "Peso Muerto Rumano (Barra)",
        "day": 1,
        "muscle_group": "Espalda Baja",
        "is_key_lift": False,  # Demoted: historical data only (replaced by conventional DL)
        "is_compound": True,
        "strength_std": {"int": 1.05, "adv": 1.5, "elite": 1.8},
    },
    "d2c10c97-2d54-4159-abd3-a46404710d65": {
        "name": "Reverse Deadlift (Bob Peoples)",
        "day": 1,
        "muscle_group": "Espalda Baja",
        "is_key_lift": False,
        "is_compound": True,
    },
    "70D4EBBF": {
        "name": "Jump Squat",
        "day": 1,
        "muscle_group": "Piernas",
        "is_key_lift": False,
        "is_compound": False,
    },
    "83c10d44-2992-4635-843f-fa0619eca37a": {
        "name": "Deadlift Static Hold",
        "day": 1,
        "muscle_group": "Agarre",
        "is_key_lift": False,
        "is_compound": False,
    },
    "B8127AD1": {
        "name": "Lying Leg Curl (Machine)",
        "day": 1,
        "muscle_group": "Isquios",
        "is_key_lift": False,
        "is_compound": True,
        "strength_std": {"int": 0.5, "adv": 0.75, "elite": 1.0},
    },
    "E05C2C38": {
        "name": "Standing Calf Raise (Machine)",
        "day": 1,
        "muscle_group": "Gemelos",
        "is_key_lift": False,
        "is_compound": False,
    },
    "99D5F10E": {
        "name": "Ab Wheel",
        "day": 1,
        "muscle_group": "Core",
        "is_key_lift": False,
        "is_compound": False,
    },

    # ── Day 2 — Press + Shoulders ───────────────────────────────────
    "073032BB": {
        "name": "Standing Military Press (Barbell)",
        "day": 2,
        "muscle_group": "Hombros",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 0.65, "adv": 1.0, "elite": 1.25},
        "bbd_ratio": {"label": "OHP / DL", "range": (20, 30)},
    },
    "50DFDFAB": {
        "name": "Incline Bench Press (Barbell)",
        "day": 2,
        "muscle_group": "Pecho",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 1.0, "adv": 1.5, "elite": 1.75},
    },
    "6AC96645": {
        "name": "Overhead Press (Dumbbell)",
        "day": 2,
        "muscle_group": "Hombros",
        "is_key_lift": False,
        "is_compound": True,
    },
    "E644F828": {
        "name": "Bench Press - Wide Grip (Barbell)",
        "day": 2,
        "muscle_group": "Pecho",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 1.1, "adv": 1.5, "elite": 2.0},
    },
    "b2f6fd25-c32e-4686-9939-0e55d501d0d2": {
        "name": "Bradford Press",
        "day": 2,
        "muscle_group": "Hombros",
        "is_key_lift": False,
        "is_compound": True,
    },
    "60c9c36b-f128-494c-bc59-d4d09e7b2c29": {
        "name": "Straight-Arm Overhead Lateral",
        "day": 2,
        "muscle_group": "Hombros",
        "is_key_lift": False,
        "is_compound": False,
    },

    # ── Day 3 — Arms (optional) ─────────────────────────────────────
    "875F585F": {
        "name": "Skullcrusher (Barbell)",
        "day": 3,
        "muscle_group": "Tríceps",
        "is_key_lift": False,
        "is_compound": True,
        "strength_std": {"int": 0.5, "adv": 0.75, "elite": 1.0},
    },
    "112FC6B7": {
        "name": "Reverse Curl (Barbell)",
        "day": 3,
        "muscle_group": "Bíceps",
        "is_key_lift": False,
        "is_compound": False,
    },
    "552AB030": {
        "name": "Single Arm Triceps Pushdown (Cable)",
        "day": 3,
        "muscle_group": "Tríceps",
        "is_key_lift": False,
        "is_compound": False,
    },
    "724CDE60": {
        "name": "Concentration Curl",
        "day": 3,
        "muscle_group": "Bíceps",
        "is_key_lift": False,
        "is_compound": False,
    },
    "B5EFBF9C": {
        "name": "Overhead Triceps Extension (Cable)",
        "day": 3,
        "muscle_group": "Tríceps",
        "is_key_lift": False,
        "is_compound": False,
    },
    "234897AB": {
        "name": "Rope Cable Curl",
        "day": 3,
        "muscle_group": "Bíceps",
        "is_key_lift": False,
        "is_compound": False,
    },

    # ── Day 4 — Back + Traps ────────────────────────────────────────
    "0B841777": {
        "name": "Shrug (Barbell)",
        "day": 4,
        "muscle_group": "Trapecios",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 1.0, "adv": 1.5, "elite": 2.0},
        "bbd_ratio": {"label": "Shrug / DL", "range": (50, 65)},
    },
    "018ADC12": {
        "name": "Pendlay Row (Barbell)",
        "day": 4,
        "muscle_group": "Espalda",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 0.75, "adv": 1.25, "elite": 1.5},
        "bbd_ratio": {"label": "Pendlay / DL", "range": (25, 35)},
    },
    "F1E57334": {
        "name": "Dumbbell Row",
        "day": 4,
        "muscle_group": "Espalda",
        "is_key_lift": False,
        "is_compound": True,
    },
    "1B2B1E7C": {
        "name": "Pull Up",
        "day": 4,
        "muscle_group": "Espalda",
        "is_key_lift": True,
        "is_compound": True,
    },
    "F1D60854": {
        "name": "Seated Cable Row - Bar Grip",
        "day": 4,
        "muscle_group": "Espalda",
        "is_key_lift": False,
        "is_compound": True,
        "strength_std": {"int": 0.8, "adv": 1.2, "elite": 1.5},
    },

    # ── Day 5 — Legs ────────────────────────────────────────────────
    "40C6A9FC": {
        "name": "Zercher Squat",
        "day": 5,
        "muscle_group": "Cuádriceps",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 0.85, "adv": 1.25, "elite": 1.6},
        "bbd_ratio": {"label": "Zercher / DL", "range": (30, 45)},
    },
    "5046D0A9": {
        "name": "Front Squat",
        "day": 5,
        "muscle_group": "Cuádriceps",
        "is_key_lift": False,  # Demoted: historical data only (replaced by Zercher Squat)
        "is_compound": True,
        "strength_std": {"int": 1.25, "adv": 1.75, "elite": 2.25},
    },
    "c7949429-2829-4898-9cbc-5e16bb7aa893": {
        "name": "Quarter Squat",
        "day": 5,
        "muscle_group": "Cuádriceps",
        "is_key_lift": True,
        "is_compound": True,
    },
    "B537D09F": {
        "name": "Lunge (Dumbbell)",
        "day": 5,
        "muscle_group": "Piernas",
        "is_key_lift": False,
        "is_compound": True,
    },
    "68B83EE0": {
        "name": "Glute Ham Raise",
        "day": 5,
        "muscle_group": "Isquios",
        "is_key_lift": False,
        "is_compound": True,
    },
    "06745E58": {
        "name": "Standing Calf Raise",
        "day": 5,
        "muscle_group": "Gemelos",
        "is_key_lift": False,
        "is_compound": False,
    },

    # ── Day 6 — Press/Chest + Triceps ───────────────────────────────
    "7bedf18e-cc6c-447f-8f65-93a7ec7cee0b": {
        "name": "Klokov Press",
        "day": 6,
        "muscle_group": "Hombros",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 0.45, "adv": 0.65, "elite": 0.85},
        "bbd_ratio": {"label": "Klokov / DL", "range": (15, 22)},
    },
    "35B51B87": {
        "name": "Bench Press - Close Grip (Barbell)",
        "day": 6,
        "muscle_group": "Pecho",
        "is_key_lift": True,
        "is_compound": True,
        "strength_std": {"int": 1.1, "adv": 1.5, "elite": 2.0},
    },
    "DE68C825": {
        "name": "Single Arm Lateral Raise (Cable)",
        "day": 6,
        "muscle_group": "Hombros",
        "is_key_lift": False,
        "is_compound": False,
    },
    "12017185": {
        "name": "Chest Fly (Dumbbell)",
        "day": 6,
        "muscle_group": "Pecho",
        "is_key_lift": False,
        "is_compound": False,
    },

    # ── General (all days) ──────────────────────────────────────────
    "F8A0FCCA": {
        "name": "Kettlebell Swing",
        "day": 0,
        "muscle_group": "Posterior",
        "is_key_lift": False,
        "is_compound": True,
    },
}


# ═════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — derive lookups from EXERCISE_DB
# ═════════════════════════════════════════════════════════════════════

def get_muscle_group(template_id: str) -> str:
    """Get muscle group for an exercise by template_id."""
    entry = EXERCISE_DB.get(template_id)
    return entry["muscle_group"] if entry else "Otro"


def get_key_lift_ids() -> set:
    """Get set of template_ids that are key lifts."""
    return {tid for tid, e in EXERCISE_DB.items() if e.get("is_key_lift")}


def get_compound_ids() -> set:
    """Get set of template_ids that are compound movements."""
    return {tid for tid, e in EXERCISE_DB.items() if e.get("is_compound")}


def get_strength_standards() -> dict:
    """Get {template_id: {int, adv, elite}} for exercises with standards."""
    return {
        tid: e["strength_std"]
        for tid, e in EXERCISE_DB.items()
        if "strength_std" in e
    }


def get_bbd_ratios() -> dict:
    """Get {template_id: {label, range}} for BBD ratio exercises."""
    return {
        tid: e["bbd_ratio"]
        for tid, e in EXERCISE_DB.items()
        if e.get("bbd_ratio")
    }


# Deadlift reference exercise
DEADLIFT_TEMPLATE_ID = "C6272009"  # Conventional Deadlift (Barbell)
SHRUG_TEMPLATE_ID = "0B841777"
PULLUP_TEMPLATE_ID = "1B2B1E7C"


MUSCLE_GROUP_COLORS = {
    "Espalda": "#3b82f6",
    "Trapecios": "#8b5cf6",
    "Espalda Baja": "#6366f1",
    "Pecho": "#ef4444",
    "Hombros": "#f97316",
    "Cuádriceps": "#22c55e",
    "Piernas": "#16a34a",
    "Isquios": "#15803d",
    "Gemelos": "#4ade80",
    "Tríceps": "#f59e0b",
    "Bíceps": "#d946ef",
    "Core": "#64748b",
    "Agarre": "#78716c",
    "Posterior": "#a3a3a3",
    "Olímpico": "#0ea5e9",
}

WEEKLY_TARGETS = {
    "sessions": (5, 6),
    "total_sets": (140, 170),
    "total_volume_kg": (70_000, 90_000),
}


# Derived: list of key lift template IDs and their names
KEY_LIFT_IDS = get_key_lift_ids()
KEY_LIFTS = [e["name"] for e in EXERCISE_DB.values() if e.get("is_key_lift")]
