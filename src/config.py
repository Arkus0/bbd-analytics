"""
BBD Analytics — Configuration & Constants
"""
import os
from datetime import datetime

# ── API Keys (from environment) ─────────────────────────────────────
HEVY_API_KEY = os.environ.get("HEVY_API_KEY", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")

# ── Notion IDs ───────────────────────────────────────────────────────
NOTION_BBD_LOGBOOK_DB = os.environ.get(
    "NOTION_BBD_LOGBOOK_DB", "ac92ba6bbc18464f9f2b2a7f82e6c443"
)
NOTION_ANALYTICS_PAGE = os.environ.get(
    "NOTION_ANALYTICS_PAGE", "306cbc49-9cfe-81b0-8aed-ce82d40289f6"
)
NOTION_SEGUIMIENTO_DB = os.environ.get(
    "NOTION_SEGUIMIENTO_DB", "d5b662b8-a68a-4ed0-9237-8540cc3c2d47"
)

# ── Program Constants ────────────────────────────────────────────────
PROGRAM_START = datetime(2026, 2, 12)
PROGRAM_NAME = "Backed by Deadlifts"

# ── BBD Day Mapping ──────────────────────────────────────────────────
DAY_CONFIG = {
    1: {"name": "Día 1 - Deadlift", "focus": "Deadlift + Piernas", "color": "#ef4444"},
    2: {"name": "Día 2 - Press", "focus": "Press + Hombros", "color": "#f97316"},
    3: {"name": "Día 3 - Brazos", "focus": "Brazos (opcional)", "color": "#eab308"},
    4: {"name": "Día 4 - Espalda", "focus": "Espalda + Trapecios", "color": "#3b82f6"},
    5: {"name": "Día 5 - Piernas", "focus": "Piernas", "color": "#22c55e"},
    6: {"name": "Día 6 - Press/Pecho", "focus": "Press + Pecho + Tríceps", "color": "#a855f7"},
}

# ── Muscle Group Mapping ─────────────────────────────────────────────
# Maps Hevy exercise names (Spanish) → muscle group
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
    "Curl de Pierna Sentado (Máquina)": "Isquios",
    "Curl de Pierna Tumbado (Máquina)": "Isquios",
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
    "Sentadilla Frontal (Barra)": "Cuádriceps",
    "Quarter Squat": "Cuádriceps",
    "Zancada con Mancuernas": "Piernas",
    "Glute Ham Raise": "Isquios",
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

# Aggregate muscle groups for charts
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

# ── Key Lifts to Track Progression ──────────────────────────────────
KEY_LIFTS = [
    "Encogimiento de Hombros (Barra)",
    "Remo Pendlay (Barra)",
    "Dominada",
    "Peso Muerto (Barra)",
    "Reverse Deadlift (Bob Peoples)",
    "Press Militar (Barra)",
    "Sentadilla Frontal (Barra)",
    "Klokov Press",
    "Press de Banca - Agarre Cerrado (Barra)",
]

# ── Weekly Targets (based on BBD program) ────────────────────────────
WEEKLY_TARGETS = {
    "sessions": (5, 6),
    "total_sets": (140, 170),
    "total_volume_kg": (70_000, 90_000),
}
