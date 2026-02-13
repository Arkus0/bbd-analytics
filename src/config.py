"""
BBD Analytics — Configuration (FIXED: exercise names match Hevy API)

Changes from original:
  - MUSCLE_MAP: Fixed 4 exercise names to match actual Hevy names
    - "Sentadilla Frontal (Barra)" → "Sentadilla Delantera"
    - "Curl de Pierna Tumbado (Máquina)" → "Curl de Piernas Acostado (Máquina)"
    - "Glute Ham Raise" → "Elevación de glúteos y femorales"
    - "Zancada con Mancuernas" → "Zancada (Mancuerna)"
  - KEY_LIFTS: Added Quarter Squat + fixed Sentadilla Delantera name
  - STRENGTH_EXERCISES: New constant, all compound lifts for DOTS scoring
  - BBD_RATIOS: Fixed Front Squat exercise name
"""
import os

# ── API Keys ─────────────────────────────────────────────────────────
HEVY_API_KEY = os.environ.get("HEVY_API_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

# ── Notion IDs ───────────────────────────────────────────────────────
NOTION_BBD_LOGBOOK_DB = os.environ.get(
    "NOTION_BBD_LOGBOOK_DB", "1de4d50e-f986-4595-a5d4-225463906de7"
)
NOTION_ANALYTICS_PAGE = os.environ.get(
    "NOTION_ANALYTICS_PAGE", "306cbc49-9cfe-81b0-8aed-ce82d40289f6"
)
NOTION_SEGUIMIENTO_DB = os.environ.get(
    "NOTION_SEGUIMIENTO_DB", "d5b662b8-a68a-4ed0-9237-8540cc3c2d47"
)

# ── Program Config ───────────────────────────────────────────────────
PROGRAM_START = "2026-02-12"
BODYWEIGHT = 86.0

DAY_CONFIG = {
    1: {"name": "Día 1 - Deadlift", "focus": "Deadlift + Piernas", "color": "#ef4444"},
    2: {"name": "Día 2 - Press", "focus": "Press + Hombros", "color": "#f97316"},
    3: {"name": "Día 3 - Brazos", "focus": "Brazos (opcional)", "color": "#eab308"},
    4: {"name": "Día 4 - Espalda", "focus": "Espalda + Trapecios", "color": "#3b82f6"},
    5: {"name": "Día 5 - Piernas", "focus": "Piernas", "color": "#22c55e"},
    6: {"name": "Día 6 - Press/Pecho", "focus": "Press + Pecho + Tríceps", "color": "#a855f7"},
}

# ── Muscle Group Mapping ─────────────────────────────────────────────
# Maps Hevy exercise names (ACTUAL names from API) → muscle group
MUSCLE_MAP = {
    # Day 4
    "Encogimiento de Hombros (Barra)": "Trapecios",
    "Remo Pendlay (Barra)": "Espalda",
    "Remo con Mancuerna": "Espalda",
    "Dominada": "Espalda",
    "Remo Sentado con Cable": "Espalda",
    # Day 1
    "Reverse Deadlift (Bob Peoples)": "Espalda Baja",
    "Peso Muerto (Barra)": "Espalda Baja",
    "Sentadilla con Salto": "Piernas",
    "Deadlift Static Hold": "Agarre",
    "Curl de Piernas Acostado (Máquina)": "Isquios",       # FIXED (was "Curl de Pierna Tumbado")
    "Elevación de Talones de Pie (Máquina)": "Gemelos",
    "Elevación de Talones Sentado (Máquina)": "Gemelos",
    "Ab Wheel": "Core",
    "Abdominal Corto con Cable": "Core",
    # Day 2
    "Press Militar (Barra)": "Hombros",
    "Press de Banca Inclinado (Barra)": "Pecho",
    "Press de Hombros (Mancuerna)": "Hombros",
    "Press de Banca (Barra)": "Pecho",
    "Bradford Press": "Hombros",
    "Straight-Arm Overhead Lateral": "Hombros",
    "Elevación Lateral (Mancuerna)": "Hombros",
    # Day 3
    "Press Francés (Barra)": "Tríceps",
    "Curl Inverso (Barra)": "Bíceps",
    "Extensión de Tríceps en Polea": "Tríceps",
    "Curl Concentrado (Mancuerna)": "Bíceps",
    "Curl de Bíceps (Cable)": "Bíceps",
    # Day 5
    "Sentadilla Delantera": "Cuádriceps",                   # FIXED (was "Sentadilla Frontal (Barra)")
    "Quarter Squat": "Cuádriceps",
    "Zancada (Mancuerna)": "Piernas",                       # FIXED (was "Zancada con Mancuernas")
    "Elevación de glúteos y femorales": "Isquios",           # FIXED (was "Glute Ham Raise")
    "Extensión de Pierna": "Cuádriceps",
    # Day 6
    "Klokov Press": "Hombros",
    "Press de Banca - Agarre Cerrado (Barra)": "Pecho",
    "Elevación Lateral con Cable": "Hombros",
    "Aperturas con Cable": "Pecho",
    "Aperturas Inclinadas (Mancuerna)": "Pecho",
    # General
    "Swing con Pesa Rusa": "Posterior",
    "Hang Clean": "Olímpico",
}

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

# ── Key Lifts to Track Progression (ALL 6 DAYS) ─────────────────────
KEY_LIFTS = [
    # Day 1
    "Reverse Deadlift (Bob Peoples)",
    "Peso Muerto (Barra)",
    # Day 2
    "Press Militar (Barra)",
    "Press de Banca Inclinado (Barra)",
    "Press de Banca (Barra)",
    # Day 4
    "Encogimiento de Hombros (Barra)",
    "Remo Pendlay (Barra)",
    "Dominada",
    # Day 5
    "Sentadilla Delantera",                    # FIXED name
    "Quarter Squat",                            # ADDED
    # Day 6
    "Klokov Press",
    "Press de Banca - Agarre Cerrado (Barra)",
]

# ── Strength Standards — All compound lifts for DOTS scoring ─────────
# NEW: Previously only checked KEY_LIFTS, now includes all compounds
STRENGTH_EXERCISES = [
    "Encogimiento de Hombros (Barra)",
    "Remo Sentado con Cable",
    "Remo Pendlay (Barra)",
    "Sentadilla Delantera",
    "Quarter Squat",
    "Curl de Piernas Acostado (Máquina)",
    "Reverse Deadlift (Bob Peoples)",
    "Peso Muerto (Barra)",
    "Press Militar (Barra)",
    "Press de Banca Inclinado (Barra)",
    "Press de Banca (Barra)",
    "Klokov Press",
    "Press de Banca - Agarre Cerrado (Barra)",
    "Press Francés (Barra)",
]

# ── BBD Ratio Targets (exercise → %DL 1RM range) ────────────────────
BBD_RATIOS = {
    "Encogimiento de Hombros (Barra)": {"label": "Shrug / DL", "range": (85, 100)},
    "Remo Pendlay (Barra)": {"label": "Pendlay / DL", "range": (45, 55)},
    "Sentadilla Delantera": {"label": "Front Squat / DL", "range": (55, 70)},  # FIXED name
    "Press Militar (Barra)": {"label": "OHP / DL", "range": (35, 45)},
    "Klokov Press": {"label": "Klokov / DL", "range": (25, 35)},
}

# ── Weekly Targets (based on BBD program) ────────────────────────────
WEEKLY_TARGETS = {
    "sessions": (5, 6),
    "total_sets": (140, 170),
    "total_volume_kg": (70_000, 90_000),
}
