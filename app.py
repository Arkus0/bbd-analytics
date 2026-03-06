"""
🔥 BBD Analytics v2 — Streamlit Dashboard
Run: streamlit run app.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from src.hevy_client import fetch_bbd_workouts, workouts_to_dataframe, fetch_all_workouts
from src.analytics_531 import (
    fetch_bbb_workouts as _fetch_bbb_workouts,
    workouts_to_dataframe_531, add_cycle_info,
    global_summary_531, amrap_tracking, bbb_compliance,
    accessory_volume, accessory_summary, tm_progression,
    session_summary_531, pr_table_531, lift_progression,
    strength_level_531, weekly_volume_531, muscle_volume_531,
    next_session_plan, full_week_plan,
    joker_sets_summary, validate_tm, cycle_comparison,
    fsl_compliance,
    training_calendar, build_annual_calendar,
    amrap_performance_index, tm_sustainability, joker_analysis,
    bbb_fatigue_trend, true_1rm_trend,
)
from src.config_531 import (
    DAY_CONFIG_531, TRAINING_MAX, CYCLE_WEEKS, STRENGTH_STANDARDS_531,
    PROGRAM_START_531, EXERCISE_DB_531,
)
from src.analytics import (
    add_derived_columns, global_summary, weekly_breakdown,
    pr_table, pr_history, muscle_volume, weekly_muscle_volume,
    session_summary, session_detail, key_lifts_progression,
    recovery_indicators, day_adherence, vs_targets,
    # v2 — new
    relative_intensity, bbd_ratios, estimate_dl_1rm, dominadas_progress,
    intra_session_fatigue, fatigue_trend,
    session_density, density_trend,
    strength_standards, dots_coefficient,
    # v3 — Phase 1
    plateau_detection, acwr, mesocycle_summary, calc_mesocycle,
    strength_profile, historical_comparison,
    # Gamification
    gamification_status,
)
from src.config import DAY_CONFIG, MUSCLE_GROUP_COLORS, KEY_LIFTS, KEY_LIFT_IDS, PROGRAM_START, NOTION_TOKEN, NOTION_HALL_OF_TITANS_DB, BODYWEIGHT, EXERCISE_DB
from src.shared_analytics import (
    detect_unknown_exercises,
    workout_quality_531, workout_quality_bbd, quality_trend,
    generate_workout_card, build_card_data_531, build_card_data_bbd,
)
import requests as _requests
import re as _re

# ── Page Config ──────────────────────────────────────────────────────
st.set_page_config(page_title="BBD Analytics", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

@st.cache_data(ttl=120)
def _notion_last_edit() -> pd.Timestamp | None:
    """Check when the Notion analytics page was last updated (= last successful cron)."""
    try:
        token = NOTION_TOKEN or st.secrets.get("NOTION_TOKEN", "")
        if not token:
            return None
        r = _requests.get(
            "https://api.notion.com/v1/pages/306cbc499cfe81b08aedce82d40289f6",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
            },
            timeout=5,
        )
        if r.ok:
            return pd.Timestamp(r.json()["last_edited_time"])
    except Exception:
        pass
    return None


@st.cache_data(ttl=120)
def load_hall_of_titans() -> list[dict]:
    """Fetch Hall of Titans entries from Notion database."""
    token = NOTION_TOKEN or st.secrets.get("NOTION_TOKEN", "")
    if not token or not NOTION_HALL_OF_TITANS_DB:
        return []
    try:
        r = _requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_HALL_OF_TITANS_DB}/query",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={"sorts": [{"property": "Fecha", "direction": "descending"}]},
            timeout=10,
        )
        if not r.ok:
            return []
        entries = []
        for page in r.json().get("results", []):
            props = page.get("properties", {})
            title_parts = props.get("Lift", {}).get("title", [])
            title = title_parts[0]["plain_text"] if title_parts else ""
            url_obj = props.get("YouTube URL", {}).get("url")
            peso = props.get("Peso (kg)", {}).get("number")
            fecha_obj = props.get("Fecha", {}).get("date")
            fecha = fecha_obj.get("start") if fecha_obj else None
            ejercicio_obj = props.get("Ejercicio", {}).get("select")
            ejercicio = ejercicio_obj.get("name") if ejercicio_obj else ""
            epico_obj = props.get("Épico", {}).get("select")
            epico = epico_obj.get("name") if epico_obj else ""
            comment_parts = props.get("Comentario", {}).get("rich_text", [])
            comentario = comment_parts[0]["plain_text"] if comment_parts else ""
            bw_ratio_obj = props.get("×BW", {}).get("formula")
            bw_ratio = bw_ratio_obj.get("number") if bw_ratio_obj else None

            if url_obj:
                entries.append({
                    "title": title, "url": url_obj, "peso": peso,
                    "fecha": fecha, "ejercicio": ejercicio, "epico": epico,
                    "comentario": comentario, "bw_ratio": bw_ratio,
                })
        return entries
    except Exception:
        return []


def _youtube_embed_url(url: str) -> str | None:
    """Extract YouTube video ID and return embed URL."""
    if not url:
        return None
    patterns = [
        r"(?:youtu\.be/|youtube\.com/watch\?v=|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = _re.search(pattern, url)
        if match:
            return f"https://www.youtube.com/embed/{match.group(1)}"
    return None


def render_monthly_calendar(cal_data: dict):
    """Render annual calendar as pure HTML tables — works correctly on mobile."""
    from calendar import monthcalendar
    from datetime import date

    weeks = cal_data["weeks"]
    year = cal_data.get("year", 2026)
    week_data = {w["abs_week"]: w for w in weeks}

    color_map = {
        "5s": "#3b82f6",
        "3s": "#f59e0b",
        "531": "#ef4444",
        "deload": "#22c55e",
    }

    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    days_header = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    program_start = date(year, 1, 1)

    is_mobile = st.toggle("📱 Vista compacta (1 mes)", value=False, key="mobile_mode")

    if is_mobile:
        month_idx = st.selectbox("Mes", range(12), format_func=lambda x: month_names[x], key="month_selector")
        months_to_show = [month_idx]
    else:
        months_to_show = range(12)

    th_style = (
        "text-align:center;padding:4px 2px;font-size:0.72rem;"
        "color:#a8a29e;font-weight:600;width:14.28%;"
    )

    for month_idx in months_to_show:
        month_name = month_names[month_idx]
        cal_matrix = monthcalendar(year, month_idx + 1)

        html = (
            f'<div style="margin-bottom:24px;">'
            f'<div style="font-size:1rem;font-weight:700;margin-bottom:8px;color:#fafaf9;">'
            f'{month_name} {year}</div>'
            f'<table style="border-collapse:collapse;width:100%;table-layout:fixed;">'
            f'<thead><tr>'
        )
        for d in days_header:
            html += f'<th style="{th_style}">{d}</th>'
        html += '</tr></thead><tbody>'

        for week in cal_matrix:
            html += '<tr>'
            for day in week:
                if day == 0:
                    html += '<td style="padding:3px;"></td>'
                else:
                    current_date = date(year, month_idx + 1, day)
                    days_since_start = (current_date - program_start).days
                    abs_week = (days_since_start // 7) + 1

                    if abs_week in week_data:
                        w = week_data[abs_week]
                        color = color_map.get(w["type"], "#6b7280")
                        is_current = w["status"] == "current"
                        border = "3px solid #2563eb" if is_current else f"2px solid {color}"
                        html += (
                            f'<td style="padding:3px;text-align:center;">'
                            f'<div style="width:30px;height:30px;border-radius:50%;'
                            f'background:{color};border:{border};'
                            f'display:flex;align-items:center;justify-content:center;'
                            f'margin:0 auto;font-size:11px;font-weight:bold;'
                            f'color:white;text-shadow:0 0 2px black;">{day}</div>'
                            f'<div style="font-size:8px;color:#a8a29e;margin-top:1px;'
                            f'font-family:monospace;">W{abs_week}</div>'
                            f'</td>'
                        )
                    else:
                        html += (
                            f'<td style="padding:3px;text-align:center;">'
                            f'<div style="width:30px;height:30px;border-radius:50%;'
                            f'background:#1f2937;border:1px solid #374151;'
                            f'display:flex;align-items:center;justify-content:center;'
                            f'margin:0 auto;font-size:11px;color:#6b7280;">{day}</div>'
                            f'</td>'
                        )
            html += '</tr>'

        html += '</tbody></table></div>'
        st.markdown(html, unsafe_allow_html=True)

    # Legend — flexbox HTML avoids mobile column-stacking issues
    st.markdown("### Leyenda")
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:14px;margin-top:4px;">'
        '<div style="display:flex;align-items:center;gap:5px;">'
        '<div style="width:14px;height:14px;border-radius:50%;background:#3b82f6;flex-shrink:0;"></div>'
        '<span>5s</span></div>'
        '<div style="display:flex;align-items:center;gap:5px;">'
        '<div style="width:14px;height:14px;border-radius:50%;background:#f59e0b;flex-shrink:0;"></div>'
        '<span>3s</span></div>'
        '<div style="display:flex;align-items:center;gap:5px;">'
        '<div style="width:14px;height:14px;border-radius:50%;background:#ef4444;flex-shrink:0;"></div>'
        '<span>531</span></div>'
        '<div style="display:flex;align-items:center;gap:5px;">'
        '<div style="width:14px;height:14px;border-radius:50%;background:#22c55e;flex-shrink:0;"></div>'
        '<span>Deload</span></div>'
        '<div style="display:flex;align-items:center;gap:5px;">'
        '<div style="width:14px;height:14px;border-radius:50%;background:#6b7280;'
        'border:3px solid #2563eb;flex-shrink:0;"></div>'
        '<span>Semana actual</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )


_CSS_LOADED = False

def _inject_base_css():
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    _CSS_LOADED = True
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        .stApp { font-family: 'Space Grotesk', sans-serif; }
        code, .stCode { font-family: 'JetBrains Mono', monospace; }
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #1e3a5f; border-radius: 12px; padding: 16px;
        }
        div[data-testid="stMetric"] label { color: #94a3b8 !important; font-size: 0.85rem; }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f1f5f9 !important; }
        h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; }
        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
            div[data-testid="stHorizontalBlock"] > div {
                flex: 1 1 100% !important; min-width: 100% !important;
            }
            .stApp h1 { font-size: 1.4rem !important; }
            .stApp h2 { font-size: 1.2rem !important; }
            .stApp h3 { font-size: 1.05rem !important; }
            div[data-testid="stMetric"] { padding: 10px !important; }
            iframe { max-height: 220px !important; }
            div[data-testid="stExpander"] summary { font-size: 0.9rem !important; }
        }
    </style>
    """, unsafe_allow_html=True)


_531_CSS_LOADED = False

def _inject_531_css():
    """Inject Skull Forge aesthetic — brutalist/industrial identity for 531."""
    global _531_CSS_LOADED
    if _531_CSS_LOADED:
        return
    _531_CSS_LOADED = True
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        /* ── 531 SKULL FORGE IDENTITY ─────────────────────── */
        h1, h2, h3 {
            font-family: 'Oswald', sans-serif !important;
            text-transform: uppercase !important;
            letter-spacing: 1.5px !important;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, #1c1917 0%, #0c0a09 100%) !important;
            border: 1px solid #44403c !important;
            border-top: 3px solid #dc2626 !important;
            border-radius: 2px !important;
            padding: 18px !important;
        }
        div[data-testid="stMetric"] label {
            font-family: 'Oswald', sans-serif !important;
            text-transform: uppercase !important;
            letter-spacing: 1px !important;
            color: #a8a29e !important;
            font-size: 0.78rem !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-family: 'IBM Plex Mono', monospace !important;
            color: #fafaf9 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            font-family: 'IBM Plex Mono', monospace !important;
        }

        .stTabs [data-baseweb="tab-list"] { gap: 0 !important; }
        .stTabs [data-baseweb="tab"] {
            font-family: 'Oswald', sans-serif !important;
            text-transform: uppercase !important;
            letter-spacing: 1px !important;
            font-size: 0.85rem !important;
        }
        .stTabs [aria-selected="true"] {
            border-bottom-color: #dc2626 !important;
        }

        div[data-testid="stExpander"] summary {
            font-family: 'Oswald', sans-serif !important;
            letter-spacing: 0.5px !important;
        }

        /* ── Skull Forge components ─────────────────────── */
        .sf-header {
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #fafaf9;
            font-size: 1.6rem;
            font-weight: 700;
            border-bottom: 3px solid #dc2626;
            padding-bottom: 10px;
            margin: 0 0 20px 0;
        }
        .sf-subheader {
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: #e7e5e4;
            font-size: 1.1rem;
            font-weight: 600;
            margin: 20px 0 12px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .sf-caption {
            font-family: 'IBM Plex Mono', monospace;
            color: #78716c;
            font-size: 0.78rem;
            margin-top: 4px;
        }
        .sf-card {
            background: linear-gradient(145deg, #1c1917 0%, #0c0a09 100%);
            border: 1px solid #44403c;
            border-left: 4px solid #dc2626;
            padding: 16px 20px;
            margin: 8px 0;
            border-radius: 2px;
        }
        .sf-card-muted {
            background: #1c1917;
            border: 1px solid #292524;
            border-left: 4px solid #44403c;
            padding: 16px 20px;
            margin: 8px 0;
            border-radius: 2px;
        }

        /* ── Set rows (planner) ─────────────────────── */
        .sf-set {
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 10px 16px;
            margin: 3px 0;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.88rem;
            color: #e7e5e4;
            background: #1c1917;
            border-left: 3px solid #44403c;
            transition: background 0.15s;
        }
        .sf-set:hover { background: #292524; }
        .sf-set.amrap {
            border-left: 3px solid #dc2626;
            background: linear-gradient(90deg, #1c1917 0%, #201210 100%);
        }
        .sf-set.warmup { border-left: 3px solid #64748b; opacity: 0.85; }
        .sf-set.bbb { border-left: 3px solid #3b82f6; }
        .sf-set.fsl { border-left: 3px solid #8b5cf6; }
        .sf-set .w { font-weight: 600; color: #fafaf9; min-width: 80px; }
        .sf-set .r { color: #a8a29e; min-width: 60px; }
        .sf-set .p { color: #78716c; font-size: 0.78rem; min-width: 40px; }
        .sf-set .plates { color: #fbbf24; font-size: 0.78rem; }
        .sf-tag {
            display: inline-block;
            padding: 2px 10px;
            font-size: 0.65rem;
            font-weight: 700;
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            border-radius: 1px;
        }
        .sf-tag.amrap { background: #dc2626; color: #fff; }
        .sf-tag.bbb { background: #1e40af; color: #93c5fd; }
        .sf-tag.fsl { background: #5b21b6; color: #c4b5fd; }
        .sf-tag.joker { background: #b45309; color: #fde68a; }
        .sf-tag.ok { background: #166534; color: #86efac; }
        .sf-tag.warn { background: #92400e; color: #fde68a; }
        .sf-tag.fail { background: #991b1b; color: #fca5a5; }

        /* ── Week overview grid ─────────────────────── */
        .sf-week-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin: 12px 0;
        }
        @media (max-width: 768px) {
            .sf-week-grid { grid-template-columns: repeat(2, 1fr); }
        }
        .sf-week-card {
            background: #1c1917;
            border: 1px solid #44403c;
            padding: 14px;
            border-radius: 2px;
            min-height: 150px;
        }
        .sf-week-card.active {
            border: 2px solid #dc2626;
            box-shadow: 0 0 24px rgba(220,38,38,0.12);
        }
        .sf-week-card .name {
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            color: #fafaf9;
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }
        .sf-week-card .line {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.78rem;
            color: #a8a29e;
            margin: 2px 0;
        }
        .sf-week-card .line.amrap-l { color: #dc2626; font-weight: 600; }
        .sf-week-card .bbb-line {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.72rem;
            color: #64748b;
            margin-top: 6px;
            padding-top: 6px;
            border-top: 1px solid #292524;
        }

        /* ── AMRAP cards ─────────────────────── */
        .sf-amrap-row {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 12px 16px;
            margin: 5px 0;
            background: #1c1917;
            border-radius: 2px;
            border-left: 4px solid #44403c;
        }
        .sf-amrap-row.green { border-left-color: #22c55e; }
        .sf-amrap-row.yellow { border-left-color: #fbbf24; }
        .sf-amrap-row.red { border-left-color: #ef4444; }
        .sf-amrap-row .dot {
            width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
        }
        .sf-amrap-row .dot.green { background: #22c55e; }
        .sf-amrap-row .dot.yellow { background: #fbbf24; }
        .sf-amrap-row .dot.red { background: #ef4444; }
        .sf-amrap-row .lift {
            font-family: 'Oswald', sans-serif;
            font-weight: 600;
            color: #fafaf9;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            min-width: 90px;
        }
        .sf-amrap-row .stats {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.85rem;
            color: #a8a29e;
        }
        .sf-amrap-row .e1rm {
            font-family: 'IBM Plex Mono', monospace;
            font-weight: 600;
            color: #fafaf9;
            margin-left: auto;
        }

        /* ── Strength bar ─────────────────────── */
        .sf-bar-track {
            background: #292524;
            height: 8px;
            border-radius: 1px;
            overflow: hidden;
            margin: 6px 0 4px 0;
        }
        .sf-bar-fill {
            height: 100%;
            border-radius: 1px;
            transition: width 0.4s ease;
        }
        .sf-bar-label {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.72rem;
            color: #78716c;
            display: flex;
            justify-content: space-between;
        }

        /* ── Intelligence cards ─────────────────────── */
        .sf-intel-card {
            background: linear-gradient(145deg, #1c1917 0%, #0c0a09 100%);
            border: 1px solid #44403c;
            padding: 20px;
            margin: 8px 0;
            border-radius: 2px;
        }
        .sf-intel-card .title {
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #fafaf9;
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .sf-intel-card .verdict {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.85rem;
            color: #a8a29e;
            line-height: 1.5;
        }

        /* ── Health gauge ─────────────────────── */
        .sf-gauge {
            text-align: center;
            padding: 20px;
            margin: 12px 0;
        }
        .sf-gauge .pct {
            font-family: 'Oswald', sans-serif;
            font-size: 3rem;
            font-weight: 700;
            letter-spacing: 2px;
            line-height: 1;
        }
        .sf-gauge .pct.good { color: #22c55e; }
        .sf-gauge .pct.mid { color: #fbbf24; }
        .sf-gauge .pct.bad { color: #ef4444; }
        .sf-gauge .label {
            font-family: 'Oswald', sans-serif;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #78716c;
            font-size: 0.75rem;
            margin-top: 4px;
        }

        /* ── Context bar (cycle/week info) ─────────────────────── */
        .sf-context {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            margin: 8px 0 16px 0;
        }
        .sf-ctx-chip {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.75rem;
            padding: 4px 10px;
            background: #292524;
            border: 1px solid #44403c;
            color: #a8a29e;
            border-radius: 1px;
        }
        .sf-ctx-chip.accent {
            border-color: #dc2626;
            color: #fafaf9;
        }

        /* ── Override dataframe styling ─────────────────────── */
        .stDataFrame {
            font-family: 'IBM Plex Mono', monospace !important;
        }

        /* ── Mobile responsive ─────────────────────── */
        @media (max-width: 768px) {
            div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
            div[data-testid="stHorizontalBlock"] > div {
                flex: 1 1 100% !important; min-width: 100% !important;
            }
            .stApp h1 { font-size: 1.4rem !important; }
            .stApp h2 { font-size: 1.2rem !important; }
            .stApp h3 { font-size: 1.05rem !important; }
            div[data-testid="stMetric"] { padding: 10px !important; }
            iframe { max-height: 220px !important; }
            div[data-testid="stExpander"] summary { font-size: 0.9rem !important; }
            .sf-header { font-size: 1.2rem !important; }
            .sf-subheader { font-size: 0.95rem !important; }
            .sf-gauge .pct { font-size: 2.2rem !important; }
        }
    </style>
    """, unsafe_allow_html=True)


# ── 531 HTML Rendering Helpers ────────────────────────────────────────

def _sf_header(text: str, emoji: str = "💀"):
    """Render a Skull Forge section header."""
    st.markdown(f'<div class="sf-header">{emoji} {text}</div>', unsafe_allow_html=True)


def _sf_sub(text: str, emoji: str = ""):
    """Render a Skull Forge sub-header."""
    st.markdown(f'<div class="sf-subheader">{emoji} {text}</div>', unsafe_allow_html=True)


def _sf_metrics_row(metrics: list[dict]):
    """Render a row of Skull Forge metric cards.
    Each dict: {label, value, delta?, icon?}
    """
    n = len(metrics)
    cols = st.columns(n)
    for i, m in enumerate(metrics):
        with cols[i]:
            delta = m.get("delta")
            icon = m.get("icon", "")
            label = f"{icon} {m['label']}" if icon else m["label"]
            if delta is not None:
                st.metric(label, m["value"], delta=delta)
            else:
                st.metric(label, m["value"])


def _sf_set_html(weight, reps, pct, plates_str, css_class="", tag=""):
    """Return HTML for a single set row."""
    pct_display = int(pct * 100) if isinstance(pct, float) and pct < 10 else int(pct)
    tag_html = f'<span class="sf-tag {tag.lower()}">{tag}</span>' if tag else ""
    return (
        f'<div class="sf-set {css_class}">'
        f'  <span class="w">{weight:g} kg</span>'
        f'  <span class="r">× {reps}</span>'
        f'  <span class="p">{pct_display}%</span>'
        f'  <span class="plates">🔩 {plates_str}</span>'
        f'  {tag_html}'
        f'</div>'
    )


def _sf_week_card_html(dp, is_next=False):
    """Return HTML for a week-overview card."""
    active = "active" if is_next else ""
    lines = ""
    if dp.get("tm"):
        for s in dp.get("sets", []):
            pct_d = int(s["pct"] * 100)
            cls = "amrap-l" if s["is_amrap"] else ""
            prefix = "🔴 " if s["is_amrap"] else ""
            lines += f'<div class="line {cls}">{prefix}{s["weight"]:g}kg × {s["reps"]} ({pct_d}%)</div>'
        bbb_w = dp.get("bbb_weight", "?")
        lines += f'<div class="bbb-line">BBB: {bbb_w}kg 5×10</div>'
    else:
        lines = '<div class="line">TM pendiente</div>'

    pointer = " ← 👈" if is_next else ""
    return (
        f'<div class="sf-week-card {active}">'
        f'  <div class="name">{dp["lift_label"]}{pointer}</div>'
        f'  {lines}'
        f'</div>'
    )


def _sf_amrap_status_html(lift_label, weight, reps, min_reps, over, e1rm):
    """Return HTML for an AMRAP status row."""
    if over >= 3:
        cls, dot = "green", "green"
    elif over >= 0:
        cls, dot = "yellow", "yellow"
    else:
        cls, dot = "red", "red"
    return (
        f'<div class="sf-amrap-row {cls}">'
        f'  <span class="dot {dot}"></span>'
        f'  <span class="lift">{lift_label}</span>'
        f'  <span class="stats">{weight}kg × <b>{reps}</b> (mín: {min_reps}, +{over})</span>'
        f'  <span class="e1rm">e1RM: {e1rm}kg</span>'
        f'</div>'
    )


def _sf_progress_bar(current, target, prev=0, color="#dc2626", label_left="", label_right=""):
    """Return HTML for a custom progress bar."""
    progress = (current - prev) / (target - prev) if target > prev else 1.0
    progress = max(0, min(progress, 1.0))
    pct = progress * 100
    return (
        f'<div class="sf-bar-track">'
        f'  <div class="sf-bar-fill" style="width:{pct:.0f}%; background:{color};"></div>'
        f'</div>'
        f'<div class="sf-bar-label">'
        f'  <span>{label_left}</span>'
        f'  <span>{label_right}</span>'
        f'</div>'
    )

PL = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk", color="#e2e8f0"), margin=dict(l=40, r=20, t=40, b=40),
)

PL_531 = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Oswald, sans-serif", color="#e7e5e4", size=13),
    margin=dict(l=40, r=20, t=50, b=40),
    title_font=dict(family="Oswald, sans-serif", size=16, color="#fafaf9"),
    legend=dict(font=dict(family="IBM Plex Mono, monospace", size=11)),
    colorway=["#dc2626", "#3b82f6", "#fbbf24", "#22c55e", "#8b5cf6", "#ec4899", "#f97316"],
)

# ── Data Loading ─────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_raw_data():
    """Cache raw Hevy data only — derived columns computed fresh each time."""
    workouts = fetch_bbd_workouts()
    return workouts_to_dataframe(workouts)


@st.cache_data(ttl=120)
def load_531_data():
    """Cache 531 BBB data."""
    workouts = _fetch_bbb_workouts()
    if not workouts:
        return pd.DataFrame()
    df = workouts_to_dataframe_531(workouts)
    if not df.empty:
        df = add_cycle_info(df)
    return df

_bbd_error = None
_531_error = None

try:
    raw_df = load_raw_data()
    df = add_derived_columns(raw_df)  # includes cycle-aware week assignment
except Exception as e:
    _bbd_error = str(e)
    df = pd.DataFrame()

last_sync = pd.Timestamp.now(tz="Europe/Madrid")

# ── Sidebar ──────────────────────────────────────────────────────────
# Detect which program has the most recent session
_last_bbd = df["date"].max() if not df.empty else pd.Timestamp.min
try:
    _df_531_check = load_531_data()
    _last_531 = _df_531_check["date"].max() if not _df_531_check.empty else pd.Timestamp.min
except Exception as e:
    _531_error = str(e)
    _last_531 = pd.Timestamp.min
_default_idx = 1 if _last_531 > _last_bbd else 0

with st.sidebar:
    st.markdown("# 🔥 BBD Analytics")
    program = st.selectbox("Programa", ["🔥 BBD", "💀 531 BBB"], index=_default_idx, label_visibility="collapsed")
    is_531 = program == "💀 531 BBB"
    if is_531:
        st.markdown(
            f'<div style="font-family:Oswald,sans-serif;text-transform:uppercase;'
            f'letter-spacing:1px;color:#78716c;font-size:0.75rem;">'
            f'Wendler\'s 531 Boring But Big<br>'
            f'desde {pd.Timestamp(PROGRAM_START_531).strftime("%d %b %Y")}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(f"Backed by Deadlifts — desde {pd.Timestamp(PROGRAM_START).strftime('%d %b %Y')}")
    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    now = pd.Timestamp.now(tz="Europe/Madrid")
    mins_ago = int((now - last_sync).total_seconds() // 60)
    if mins_ago < 1:
        st.caption("📡 Datos actualizados ahora")
    else:
        st.caption(f"📡 Última carga: hace {mins_ago} min")

    # Session count indicator
    if is_531:
        try:
            _dbg = load_531_data()
            _n = _dbg["hevy_id"].nunique() if not _dbg.empty else 0
            st.caption(f"📦 {_n} sesiones 531 cargadas")
        except Exception:
            pass

    # Cron health: check Notion analytics page last edit
    notion_edit = _notion_last_edit()
    if notion_edit is not None:
        hours_since = (now - notion_edit.tz_convert("Europe/Madrid")).total_seconds() / 3600
        if hours_since > 24:
            st.error(f"⚠️ Notion sync hace {int(hours_since)}h — revisa GitHub Actions")
        else:
            st.caption(f"✅ Notion sync: hace {int(hours_since)}h")

    st.divider()
    if is_531:
        page = st.radio("Sección", [
            "📋 Hoy te toca",
            "📊 Dashboard",
            "🎯 AMRAP Tracker",
            "📈 Progresión",
            "🧠 Inteligencia",
            "⭐ Quality Score",
            "🏋️ Strength Standards",
            "💪 Sesiones",
            "🏆 PRs",
            "📸 Workout Card",
            "🔍 Sustituciones",
            "📅 Calendario",
            "🗓️ Vista Anual",
            "🗺️ Plan Forever",
        ], label_visibility="collapsed")
    else:
        page = st.radio("Sección", [
        "📊 Dashboard",
        "📈 Progresión",
        "🎯 Ratios BBD",
        "🔬 Fatiga Intra-sesión",
        "⚡ Densidad",
        "🏋️ Strength Standards",
        "🧠 Inteligencia",
        "⭐ Quality Score",
        "🎮 Niveles",
        "🏛️ Hall of Titans",
        "💪 Sesiones",
        "🏆 PRs",
        "📸 Workout Card",
        "🔍 Sustituciones",
        "🎯 Adherencia",
    ], label_visibility="collapsed")

# ══════════════════════════════════════════════════════════════════════
# 💀 531 BBB DASHBOARD
# ══════════════════════════════════════════════════════════════════════
if is_531:
    _inject_531_css()
    if _531_error:
        st.error(f"❌ Error cargando datos 531: {_531_error}")
        st.info("Puedes cambiar a BBD en el sidebar mientras se resuelve.")
        st.stop()
    df_531 = load_531_data()

    # Planner works even with no data
    if page == "📋 Hoy te toca":
        plan = next_session_plan(df_531)

        # ── Header ──
        _sf_header(f"Hoy te toca — {plan['lift_label']}", "📋")

        # ── Context chips ──
        chips_html = (
            f'<div class="sf-context">'
            f'  <span class="sf-ctx-chip accent">Ciclo {plan["cycle_num"]}</span>'
            f'  <span class="sf-ctx-chip accent">{plan["week_name"]}</span>'
            f'  <span class="sf-ctx-chip">Día {plan["day_num"]}</span>'
            f'  <span class="sf-ctx-chip">{plan["focus"]}</span>'
            f'</div>'
        )
        st.markdown(chips_html, unsafe_allow_html=True)

        if plan["tm"] is None:
            st.warning(f"⚠️ Training Max de {plan['lift_label']} no configurado. Dime tu TM y lo actualizo.")
        else:
            st.markdown(
                f'<div class="sf-caption">Training Max: <b style="color:#fafaf9">{plan["tm"]} kg</b></div>',
                unsafe_allow_html=True,
            )

            # ── Warmup ──
            _sf_sub("Calentamiento", "🔥")
            warmup_html = ""
            for s in plan["warmup"]:
                warmup_html += _sf_set_html(s["weight"], s["reps"], s["pct"], s["plates_str"], css_class="warmup")
            st.markdown(warmup_html, unsafe_allow_html=True)

            # ── Working sets ──
            _sf_sub("Series de trabajo", "💀")
            working_html = ""
            for s in plan["working_sets"]:
                tag = "AMRAP" if s["is_amrap"] else ""
                cls = "amrap" if s["is_amrap"] else ""
                working_html += _sf_set_html(s["weight"], s["reps"], s["pct"], s["plates_str"], css_class=cls, tag=tag)
            st.markdown(working_html, unsafe_allow_html=True)

            # ── BBB Supplemental ──
            bbb = plan["bbb"]
            if bbb:
                _sf_sub("BBB Supplemental", "📦")
                pct_display = int(bbb["pct_tm"] * 100)
                bbb_html = _sf_set_html(
                    bbb["weight"], f'{bbb["reps"]} × {bbb["sets"]} sets',
                    pct_display, bbb["plates_str"], css_class="bbb", tag="BBB"
                )
                st.markdown(bbb_html, unsafe_allow_html=True)

            # ── Full week overview (HTML grid) ──
            _sf_sub("Esta semana completa", "📅")
            week_plans = full_week_plan(df_531)
            grid_html = '<div class="sf-week-grid">'
            for dp in week_plans:
                is_next = (dp["day_num"] == plan["day_num"])
                grid_html += _sf_week_card_html(dp, is_next=is_next)
            grid_html += '</div>'
            st.markdown(grid_html, unsafe_allow_html=True)

        st.stop()

    if df_531.empty:
        st.warning("No hay entrenamientos 531 BBB registrados todavía.")
        st.info("Asegúrate de iniciar el workout desde la rutina BBB en Hevy para que se detecte automáticamente.")
        st.stop()

    summary_531 = global_summary_531(df_531)

    if page == "📊 Dashboard":
        _sf_header("531 BBB — Dashboard", "💀")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💀 Sesiones", summary_531.get("total_sessions", 0))
        c2.metric("⚖️ Volumen", f"{summary_531.get('total_volume_kg', 0):,} kg")
        c3.metric("📊 Sets", summary_531.get("total_sets", 0))
        c4.metric("🎯 AMRAPs", summary_531.get("amrap_count", 0))

        # ── Training Maxes as styled cards ──
        _sf_sub("Training Maxes", "🎯")
        lift_labels = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
        lift_emojis = {"ohp": "🏋️", "deadlift": "💀", "bench": "🪑", "squat": "🦵"}
        lift_colors = {"ohp": "#f59e0b", "deadlift": "#dc2626", "bench": "#3b82f6", "squat": "#22c55e"}

        tm_cols = st.columns(4)
        for i, (lift, label) in enumerate(lift_labels.items()):
            tm = TRAINING_MAX.get(lift)
            with tm_cols[i]:
                if tm:
                    st.metric(f"{lift_emojis[lift]} {label}", f"{tm} kg")
                else:
                    st.metric(f"{lift_emojis[lift]} {label}", "TBD")

        # ── AMRAP summary — styled cards ──
        amraps = amrap_tracking(df_531)
        if not amraps.empty:
            amraps = amraps.sort_values("date").groupby("lift").tail(1)
            _sf_sub("Últimos AMRAPs", "🎯")
            amrap_html = ""
            for _, row in amraps.iterrows():
                lift_label = lift_labels.get(row["lift"], row["lift"])
                over = row["reps_over_min"]
                amrap_html += _sf_amrap_status_html(
                    lift_label, row["weight_kg"], row["reps"],
                    row["min_reps"], over, row["e1rm"]
                )
            st.markdown(amrap_html, unsafe_allow_html=True)

        # ── BBB compliance — styled cards ──
        bbb = bbb_compliance(df_531)
        if not bbb.empty:
            bbb = bbb.sort_values("date").groupby("lift").tail(1)
            _sf_sub("BBB Supplemental", "📦")
            bbb_html = ""
            for _, row in bbb.iterrows():
                lift_label = lift_labels.get(row["lift"], str(row["lift"]))
                ok = row["sets_ok"] and row["reps_ok"]
                tag_cls = "ok" if ok else "warn"
                tag_text = "OK" if ok else "⚠️"
                pct = f" ({row['pct_of_tm']}% TM)" if row["pct_of_tm"] else ""
                bbb_html += (
                    f'<div class="sf-card{"" if ok else "-muted"}">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;">{lift_label}</span>'
                    f'  <span class="sf-tag {tag_cls}">{tag_text}</span>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#a8a29e;margin-top:6px;">'
                    f'    {row["weight_kg"]}kg{pct} · {row["n_sets"]} sets × {row["avg_reps"]} reps avg '
                    f'    (total: {row["total_reps"]})'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown(bbb_html, unsafe_allow_html=True)

        # ── FSL compliance ──
        fsl = fsl_compliance(df_531)
        if not fsl.empty:
            fsl = fsl.sort_values("date").groupby("lift").tail(1)
            _sf_sub("FSL (First Set Last)", "🔁")
            fsl_html = ""
            for _, row in fsl.iterrows():
                lift_label = lift_labels.get(row["lift"], str(row["lift"]))
                ok = row["sets_ok"] and row["reps_ok"]
                tag_cls = "ok" if ok else "warn"
                tag_text = "OK" if ok else "⚠️"
                pct = f" ({row['pct_of_tm']}% TM)" if row["pct_of_tm"] else ""
                fsl_html += (
                    f'<div class="sf-card-muted">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;">{lift_label}</span>'
                    f'  <span class="sf-tag {tag_cls}">{tag_text}</span>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#a8a29e;margin-top:6px;">'
                    f'    {row["weight_kg"]}kg{pct} · {row["n_sets"]} sets × {row["avg_reps"]} reps avg'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown(fsl_html, unsafe_allow_html=True)

        # ── Joker sets ──
        jokers = joker_sets_summary(df_531)
        if not jokers.empty:
            jokers = jokers.sort_values("date").groupby("lift").tail(1)
            _sf_sub("Joker Sets", "🃏")
            jk_cols = st.columns(2)
            jk_cols[0].metric("Total Joker Sets", int(jokers["total_sets"].sum()))
            jk_cols[1].metric("Mejor e1RM (Joker)", f"{jokers['best_e1rm'].max():.1f} kg")
            joker_html = ""
            for _, jrow in jokers.iterrows():
                lift_label = lift_labels.get(jrow["lift"], str(jrow["lift"]))
                joker_html += (
                    f'<div class="sf-card-muted" style="border-left-color:#f59e0b;">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;">{lift_label}</span>'
                    f'  <span class="sf-tag joker">JOKER</span>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#a8a29e;margin-top:6px;">'
                    f'    {jrow["date"].strftime("%d %b")} · '
                    f'    {jrow["weight_kg"]}kg × {jrow["best_reps"]} ({jrow["total_sets"]} sets) → '
                    f'    e1RM: <b style="color:#fafaf9">{jrow["best_e1rm"]:.1f}kg</b>'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown(joker_html, unsafe_allow_html=True)

        # ── Accessory summary ──
        acc = accessory_summary(df_531)
        if not acc.empty:
            _sf_sub("Accesorios", "🔧")
            acc_html = ""
            for _, row in acc.iterrows():
                acc_html += (
                    f'<div class="sf-card-muted" style="border-left-color:#22c55e;">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;">{row["muscle_group"]}</span>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#a8a29e;margin-top:4px;">'
                    f'    {row["total_sets"]} sets · {row["total_reps"]} reps · {row["total_volume"]:,.0f} kg'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown(acc_html, unsafe_allow_html=True)

    elif page == "🎯 AMRAP Tracker":
        _sf_header("AMRAP Tracker", "🎯")
        st.markdown(
            '<div class="sf-caption">La serie AMRAP es el pulso de tu progresión en 531.</div>',
            unsafe_allow_html=True,
        )

        # TM Validation alerts — styled cards
        tm_val = validate_tm(df_531)
        if tm_val:
            _sf_sub("Estado del Training Max", "⚙️")
            for lift, info in tm_val.items():
                lift_label = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}.get(lift, lift)
                if info["status"] == "too_light":
                    tag_cls, tag_text = "warn", "⬆️ SUBIR"
                    detail = (
                        f'TM parece bajo — promedio +{info["avg_reps_over_min"]} reps sobre mínimo. '
                        f'TM actual: {info["current_tm"]}kg → Recomendado: <b>{info["recommended_tm"]}kg</b> '
                        f'(+{info["tm_delta"]}kg)'
                    )
                elif info["status"] == "too_heavy":
                    tag_cls, tag_text = "fail", "⬇️ BAJAR"
                    detail = (
                        f'TM parece alto — promedio {info["avg_reps_over_min"]} reps sobre mínimo. '
                        f'TM actual: {info["current_tm"]}kg → Recomendado: <b>{info["recommended_tm"]}kg</b> '
                        f'({info["tm_delta"]}kg)'
                    )
                else:
                    tag_cls, tag_text = "ok", "✅ OK"
                    detail = (
                        f'TM calibrado — +{info["avg_reps_over_min"]} reps/AMRAP. '
                        f'e1RM: {info["latest_e1rm"]}kg, TM: {info["current_tm"]}kg'
                    )
                border_color = {"ok": "#22c55e", "warn": "#fbbf24", "fail": "#ef4444"}[tag_cls]
                st.markdown(
                    f'<div class="sf-card" style="border-left-color:{border_color};">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;">{lift_label}</span>'
                    f'  <span class="sf-tag {tag_cls}">{tag_text}</span>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.82rem;'
                    f'color:#a8a29e;margin-top:8px;line-height:1.5;">{detail}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        amraps = amrap_tracking(df_531)
        if amraps.empty:
            st.info("Sin datos de AMRAP aún.")
        else:
            # AMRAP history as styled rows
            _sf_sub("Historial AMRAP", "📋")
            lift_labels_map = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            for _, row in amraps.sort_values("date", ascending=False).iterrows():
                ll = lift_labels_map.get(row["lift"], row["lift"])
                amrap_row = _sf_amrap_status_html(
                    f'{row["date"].strftime("%d/%m")} · {ll}',
                    row["weight_kg"], row["reps"], row["min_reps"],
                    row["reps_over_min"], row["e1rm"]
                )
                st.markdown(amrap_row, unsafe_allow_html=True)

            # AMRAP e1RM chart with 531 plotly theme
            _sf_sub("e1RM desde AMRAPs", "📈")
            prog = lift_progression(df_531)
            if not prog.empty:
                prog_display = prog.copy()
                prog_display["lift"] = prog_display["lift"].map(lift_labels_map)
                fig = px.line(
                    prog_display, x="date", y="e1rm", color="lift",
                    markers=True,
                    labels={"date": "", "e1rm": "e1RM (kg)", "lift": ""},
                )
                fig.update_layout(**PL_531, height=380)
                fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
                st.plotly_chart(fig, use_container_width=True)

        # Supplemental compliance section
        bbb = bbb_compliance(df_531)
        fsl = fsl_compliance(df_531)
        if not bbb.empty:
            _sf_sub("BBB Supplemental Compliance", "📦")
            bbb_display = bbb[["date", "lift", "weight_kg", "n_sets", "total_reps", "avg_reps", "pct_of_tm"]].copy()
            bbb_display["lift"] = bbb_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            bbb_display.columns = ["Fecha", "Lift", "Peso (kg)", "Sets", "Total Reps", "Avg Reps", "% TM"]
            st.dataframe(bbb_display, use_container_width=True, hide_index=True)
        if not fsl.empty:
            _sf_sub("FSL Compliance", "🔁")
            fsl_display = fsl[["date", "lift", "weight_kg", "n_sets", "total_reps", "avg_reps", "pct_of_tm"]].copy()
            fsl_display["lift"] = fsl_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            fsl_display.columns = ["Fecha", "Lift", "Peso (kg)", "Sets", "Total Reps", "Avg Reps", "% TM"]
            st.dataframe(fsl_display, use_container_width=True, hide_index=True)
        if bbb.empty and fsl.empty:
            st.info("Sin datos de suplementario aún.")

    elif page == "📈 Progresión":
        _sf_header("Progresión", "📈")

        # TM progression
        _sf_sub("Training Max vs Estimated", "🎯")
        tm_prog = tm_progression(df_531)
        if not tm_prog.empty:
            tm_display = tm_prog.copy()
            tm_display["lift"] = tm_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            tm_display = tm_display[["lift", "date", "amrap_weight", "amrap_reps", "e1rm", "estimated_tm", "current_tm"]]
            tm_display.columns = ["Lift", "Fecha", "AMRAP Peso", "AMRAP Reps", "e1RM", "TM Estimado", "TM Actual"]
            st.dataframe(tm_display, use_container_width=True, hide_index=True)
        else:
            st.info("Se necesitan más datos para mostrar progresión de TM.")

        # Volume by week
        _sf_sub("Volumen Semanal", "📊")
        wv = weekly_volume_531(df_531)
        if not wv.empty:
            fig = px.bar(
                wv, x="week_start", y="total_volume", color="set_type",
                labels={"week_start": "", "total_volume": "Volumen (kg)", "set_type": "Tipo"},
                color_discrete_map={
                    "warmup": "#64748b", "working_531": "#dc2626",
                    "amrap": "#fbbf24", "bbb": "#3b82f6", "fsl": "#8b5cf6",
                    "joker": "#f59e0b", "accessory": "#22c55e",
                },
            )
            fig.update_layout(**PL_531, height=380)
            st.plotly_chart(fig, use_container_width=True)

        # Cycle comparison
        _sf_sub("Ciclo vs Ciclo", "🔄")
        cyc = cycle_comparison(df_531)
        if not cyc.empty and cyc["cycle_num"].nunique() >= 1:
            cyc_display = cyc.copy()
            cyc_display["lift"] = cyc_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            cols_show = ["cycle_num", "lift", "amrap_avg_reps", "amrap_best_e1rm", "bbb_total_volume"]
            col_names = ["Ciclo", "Lift", "AMRAP Reps (avg)", "Mejor e1RM", "BBB Volumen"]
            if "e1rm_delta" in cyc_display.columns:
                cols_show.append("e1rm_delta")
                col_names.append("Δ e1RM (kg)")
            display_df = cyc_display[cols_show].copy()
            display_df.columns = col_names
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            if cyc["cycle_num"].nunique() >= 2:
                cyc_chart = cyc.copy()
                cyc_chart["lift"] = cyc_chart["lift"].map(
                    {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
                )
                cyc_chart["cycle_label"] = "Ciclo " + cyc_chart["cycle_num"].astype(str)
                fig = px.bar(
                    cyc_chart, x="lift", y="amrap_best_e1rm", color="cycle_label",
                    barmode="group",
                    labels={"lift": "", "amrap_best_e1rm": "e1RM (kg)", "cycle_label": ""},
                )
                fig.update_layout(**PL_531, height=380)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Se necesita al menos 1 ciclo completo para comparar.")

        # Muscle volume
        _sf_sub("Distribución Muscular", "💪")
        mv = muscle_volume_531(df_531)
        if not mv.empty:
            fig = px.pie(mv, values="total_volume", names="muscle_group")
            fig.update_layout(**PL_531, height=380)
            st.plotly_chart(fig, use_container_width=True)

    elif page == "🏋️ Strength Standards":
        _sf_header("Strength Standards", "🏋️")

        levels = strength_level_531(df_531)
        lift_labels = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
        level_colors_map = {
            "Elite": "#a855f7", "Avanzado": "#3b82f6", "Intermedio": "#22c55e",
            "Principiante": "#fbbf24", "Novato": "#78716c", "Sin datos": "#44403c",
        }

        for lift, label in lift_labels.items():
            info = levels.get(lift, {})
            e1rm = info.get("e1rm")
            ratio = info.get("ratio_bw")
            level = info.get("level", "Sin datos")
            color = level_colors_map.get(level, "#44403c")

            if e1rm:
                # Card with progress bar
                stds = STRENGTH_STANDARDS_531[lift]
                levels_order = ["beginner", "intermediate", "advanced", "elite"]
                target_label, target_kg, prev_kg = "", 0, 0
                reached_max = True
                for j, lvl in enumerate(levels_order):
                    if ratio < stds[lvl]:
                        target_kg = stds[lvl] * BODYWEIGHT
                        prev_kg = stds[levels_order[j-1]] * BODYWEIGHT if j > 0 else 0
                        target_label = f"{levels_order[j].title()}: {target_kg:.0f}kg ({stds[lvl]}×BW)"
                        reached_max = False
                        break

                progress_html = ""
                if not reached_max:
                    progress_html = _sf_progress_bar(
                        e1rm, target_kg, prev_kg, color=color,
                        label_left=f"{e1rm}kg", label_right=target_label,
                    )
                else:
                    progress_html = _sf_progress_bar(
                        1, 1, 0, color="#a855f7",
                        label_left=f"{e1rm}kg", label_right="🏆 Elite alcanzado",
                    )

                st.markdown(
                    f'<div class="sf-card" style="border-left-color:{color};">'
                    f'  <div style="display:flex;align-items:center;justify-content:space-between;">'
                    f'    <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#fafaf9;font-weight:600;font-size:1.05rem;">{label}</span>'
                    f'    <span class="sf-tag" style="background:{color};color:#fff;">{level}</span>'
                    f'  </div>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#a8a29e;margin-top:6px;">e1RM: {e1rm}kg · {ratio}×BW</div>'
                    f'  {progress_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="sf-card-muted">'
                    f'  <span style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#78716c;font-weight:600;">{label}</span>'
                    f'  <span style="font-family:IBM Plex Mono,monospace;font-size:0.85rem;'
                    f'color:#44403c;margin-left:12px;">Sin datos</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    elif page == "💪 Sesiones":
        _sf_header("Sesiones", "💪")

        sessions = session_summary_531(df_531)
        if sessions.empty:
            st.info("Sin sesiones registradas.")
        else:
            for _, s in sessions.iterrows():
                lift_label = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}.get(s["main_lift"], s["main_lift"])
                with st.expander(f"📅 {s['date'].strftime('%d %b')} — {lift_label} | {s['total_volume']:,}kg"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("AMRAP", f"{s['amrap_weight']}kg × {s['amrap_reps']}")
                    c2.metric("BBB", f"{s['bbb_sets']} sets × {s['bbb_avg_reps']} reps")
                    c3.metric("Accesorios", f"{s['accessory_sets']} sets | {s['accessory_volume']:,}kg")

                    # Show individual accessory exercises
                    sess_acc = df_531[(df_531["hevy_id"] == s["hevy_id"]) & (~df_531["is_main_lift"])]
                    if not sess_acc.empty:
                        acc_rows = []
                        for ex_name, ex_grp in sess_acc.groupby("exercise", sort=False):
                            mg = ex_grp["muscle_group"].iloc[0]
                            n = len(ex_grp)
                            best_w = ex_grp["weight_kg"].max()
                            total_r = int(ex_grp["reps"].sum())
                            vol = int(ex_grp["volume_kg"].sum())
                            w_str = f"{best_w:.0f}kg" if best_w > 0 else "BW"
                            acc_rows.append({
                                "Ejercicio": ex_name,
                                "Grupo": mg,
                                "Sets": n,
                                "Reps": total_r,
                                "Peso": w_str,
                                "Vol (kg)": vol,
                            })
                        st.dataframe(
                            pd.DataFrame(acc_rows),
                            use_container_width=True, hide_index=True, height=min(35 + 35 * len(acc_rows), 250),
                        )

    elif page == "🏆 PRs":
        _sf_header("PRs", "🏆")

        prs = pr_table_531(df_531)
        if prs.empty:
            st.info("Sin PRs registrados aún.")
        else:
            st.dataframe(
                prs[["exercise", "max_weight", "max_e1rm", "best_date"]].rename(columns={
                    "exercise": "Ejercicio", "max_weight": "Peso Máx (kg)",
                    "max_e1rm": "e1RM (kg)", "best_date": "Fecha",
                }),
                use_container_width=True, hide_index=True,
            )

    elif page == "📅 Calendario":
        _sf_header("Calendario Beyond 5/3/1", "📅")

        weeks_ahead = st.slider("Semanas a proyectar", 4, 24, 16, key="cal_weeks")
        cal = training_calendar(df_531, weeks_ahead=weeks_ahead)

        if not cal:
            st.info("Sin datos para generar calendario.")
        else:
            # ── Current position ──
            current = next((w for w in cal if w["status"] == "current"), None)
            partial = next((w for w in cal if w["status"] == "partial"), None)
            active = partial or current
            if active:
                tms = active["tms"]
                st.markdown(
                    f"**Posición actual:** Macro {active['macro_num']} · "
                    f"Semana {active['week_in_macro']} ({active['week_name']}) · "
                    f"Mini-ciclo {'A' if active['mini_cycle'] == 1 else 'B' if active['mini_cycle'] == 2 else '–'} · "
                    f"TM bumps: {active['tm_bumps']}"
                )

            st.divider()

            # ── TM Progression Timeline ──
            st.markdown("### 📈 Progresión de TM")
            # Build a table showing TM at each bump point
            bump_points = []
            seen_bumps = set()
            for w in cal:
                b = w["tm_bumps"]
                if b not in seen_bumps:
                    seen_bumps.add(b)
                    tms = w["tms"]
                    bump_points.append({
                        "Bumps": b,
                        "Desde semana": f"W{w['abs_week']}",
                        "OHP": f"{tms['ohp']:.0f} kg",
                        "Deadlift": f"{tms['deadlift']:.0f} kg",
                        "Bench": f"{tms['bench']:.0f} kg",
                        "Squat": f"{tms['squat']:.0f} kg",
                    })
            if bump_points:
                st.dataframe(pd.DataFrame(bump_points), use_container_width=True, hide_index=True)

            st.divider()

            # ── Deload calendar ──
            deloads = [w for w in cal if w["is_deload"]]
            if deloads:
                st.markdown("### 🛌 Semanas de Deload")
                for d in deloads:
                    tms = d["tms"]
                    icon = "✅" if d["status"] == "completed" else "⬜"
                    st.markdown(
                        f"{icon} **Semana {d['abs_week']}** (Macro {d['macro_num']}) — "
                        f"TMs: OHP {tms['ohp']:.0f} · DL {tms['deadlift']:.0f} · "
                        f"B {tms['bench']:.0f} · S {tms['squat']:.0f}"
                    )
                st.divider()

            # ── Full timeline ──
            st.markdown("### 🗓️ Timeline completa")

            lift_labels = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}

            for w in cal:
                status = w["status"]
                if status == "completed":
                    icon = "✅"
                    color = "green"
                elif status == "partial":
                    icon = "🔶"
                    color = "orange"
                elif status == "current":
                    icon = "👉"
                    color = "blue"
                else:
                    icon = "⬜"
                    color = "gray"

                deload_tag = " 🛌 **DELOAD**" if w["is_deload"] else ""
                bump_tag = " ⬆️ *TM bump después*" if w["is_bump_week"] else ""

                tms = w["tms"]
                tm_str = " · ".join(f"{lift_labels[l]} {tms[l]:.0f}" for l in lift_labels)

                header = (
                    f"{icon} **W{w['abs_week']}** — M{w['macro_num']}·W{w['week_in_macro']} "
                    f"**{w['week_name']}** ({w['sessions_done']}/4){deload_tag}{bump_tag}"
                )

                with st.expander(header, expanded=(status in ("partial", "current"))):
                    st.caption(f"TMs: {tm_str}")

                    if w["sessions"]:
                        for s in w["sessions"]:
                            d = s["date"]
                            ds = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)[:10]
                            lift = lift_labels.get(s["lift"], s["lift"])
                            amrap = f" — AMRAP: **{s['amrap']}**" if s["amrap"] else ""
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;📌 {ds} **{lift}**{amrap}")
                    elif status == "upcoming":
                        if w["is_deload"]:
                            st.caption("Semana ligera: 40/50/60% × 5 reps")
                        else:
                            week_type = w["week_type"]
                            scheme = {1: "65/75/85% × 5", 2: "70/80/90% × 3", 3: "75/85/95% × 5/3/1+"}.get(week_type, "?")
                            st.caption(f"Esquema: {scheme}")

    # ══════════════════════════════════════════════════════════════════════
    # 🗓️ VISTA ANUAL
    # ══════════════════════════════════════════════════════════════════════
    elif page == "🗓️ Vista Anual":
        _sf_header("Calendario Anual 5/3/1", "🗓️")
        
        cal_data = build_annual_calendar(df_531, year=2026)
        
        if not cal_data["weeks"]:
            st.info("Sin datos para generar calendario.")
        else:
            # Summary
            current = next((w for w in cal_data["weeks"] if w["status"] == "current"), None)
            if current:
                st.markdown(
                    f"**Posición actual:** Macro {current['macro_num']} · "
                    f"Semana {current['week_in_macro']} ({current['week_name']}) · "
                    f"Semana {current['abs_week']} de 52"
                )
            
            st.divider()
            
            # Calendar
            render_monthly_calendar(cal_data)
            
            st.divider()
            
            # TM Progression table
            st.markdown("### 📈 Progresión de Training Maxes")
            bump_points = []
            seen_bumps = set()
            for w in cal_data["weeks"]:
                b = w["tm_bumps"]
                if b not in seen_bumps:
                    seen_bumps.add(b)
                    tms = w["tms"]
                    bump_points.append({
                        "Bumps": b,
                        "Desde": f"W{w['abs_week']}",
                        "OHP": f"{tms['ohp']:.0f}",
                        "DL": f"{tms['deadlift']:.0f}",
                        "Bench": f"{tms['bench']:.0f}",
                        "Squat": f"{tms['squat']:.0f}",
                    })
            if bump_points:
                st.dataframe(pd.DataFrame(bump_points), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # 🗺️ PLAN FOREVER
    # ══════════════════════════════════════════════════════════════════════
    elif page == "🗺️ Plan Forever":
        from src.config_531 import (
            get_plan_position, YEARLY_PLAN, get_block_weeks,
            SUPPLEMENTAL_TEMPLATES, MAIN_WORK_MODES,
            PLAN_START_SESSION, SESSIONS_PER_WEEK,
        )

        _sf_header("Plan Anual — Forever 5/3/1", "🗺️")

        total_sessions = df_531["hevy_id"].nunique() if not df_531.empty else 0
        pos = get_plan_position(total_sessions)
        phase = pos.get("phase", "pre_plan")

        # ── Current Position Card ──
        if phase == "pre_plan":
            sessions_left = PLAN_START_SESSION - total_sessions
            weeks_left = sessions_left // SESSIONS_PER_WEEK
            st.markdown(
                f'<div style="background:linear-gradient(135deg,#1e293b,#334155);padding:20px;border-radius:12px;border-left:4px solid #f59e0b;margin-bottom:20px;">'
                f'<div style="color:#f59e0b;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Pre-Plan · Beyond 5/3/1</div>'
                f'<div style="color:#f1f5f9;font-size:22px;font-weight:700;margin-top:6px;">{pos.get("week_name","?")} · Macro {pos.get("macro_num",1)}</div>'
                f'<div style="color:#94a3b8;font-size:14px;margin-top:8px;">'
                f'{total_sessions} sesiones completadas · {sessions_left} restantes para el plan Forever ({weeks_left} semanas)'
                f'</div></div>', unsafe_allow_html=True
            )
        else:
            block = pos.get("block", {})
            block_name = block.get("name", "?") if block else "?"
            block_num = pos.get("block_num", 0)
            supp_key = pos.get("supplemental_template", "?")
            main_key = pos.get("main_work_mode", "?")
            supp_tmpl = SUPPLEMENTAL_TEMPLATES.get(supp_key, {})
            main_mode = MAIN_WORK_MODES.get(main_key, {})

            phase_colors = {
                "leader": ("#dc2626", "Leader"),
                "anchor": ("#2563eb", "Anchor"),
                "7th_week_deload": ("#f59e0b", "7th Week Deload"),
                "7th_week_tm_test": ("#8b5cf6", "7th Week TM Test"),
            }
            color, phase_label = phase_colors.get(phase, ("#64748b", phase))

            cycle_str = f" · Ciclo {pos.get('cycle_in_phase', '')}" if pos.get("cycle_in_phase") else ""

            st.markdown(
                f'<div style="background:linear-gradient(135deg,#1e293b,#334155);padding:20px;border-radius:12px;border-left:4px solid {color};margin-bottom:20px;">'
                f'<div style="color:{color};font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;">Bloque {block_num} · {phase_label}{cycle_str}</div>'
                f'<div style="color:#f1f5f9;font-size:22px;font-weight:700;margin-top:6px;">{block_name}</div>'
                f'<div style="color:#94a3b8;font-size:14px;margin-top:8px;">'
                f'{pos.get("week_name","?")} · Semana {pos.get("week_in_block","?")} del bloque · TM bumps: {pos.get("tm_bumps_total",0)}'
                f'</div>'
                f'<div style="color:#cbd5e1;font-size:13px;margin-top:12px;display:flex;gap:16px;">'
                f'<span>🏋️ {supp_tmpl.get("name", supp_key)}</span>'
                f'<span>💪 {main_mode.get("name", main_key)}</span>'
                f'<span>📊 TM {block.get("tm_pct", 85) if block else 85}%</span>'
                f'</div></div>', unsafe_allow_html=True
            )

        st.divider()

        # ── Block Progress Bar ──
        st.markdown("### 📊 Progreso del plan")
        cumulative = 0
        for block in YEARLY_PLAN:
            weeks = get_block_weeks(block)
            sessions_in_block = weeks * SESSIONS_PER_WEEK
            block_start = PLAN_START_SESSION + cumulative
            block_end = block_start + sessions_in_block

            if total_sessions < PLAN_START_SESSION:
                progress = 0.0
                status_icon = "⬜"
            elif total_sessions >= block_end:
                progress = 1.0
                status_icon = "✅"
            elif total_sessions >= block_start:
                progress = (total_sessions - block_start) / sessions_in_block
                status_icon = "▶️"
            else:
                progress = 0.0
                status_icon = "⬜"

            lt = SUPPLEMENTAL_TEMPLATES.get(block["leader_template"], {})
            at = SUPPLEMENTAL_TEMPLATES.get(block["anchor_template"], {})
            leader_main = MAIN_WORK_MODES.get(block["leader_main_work"], {})
            anchor_main = MAIN_WORK_MODES.get(block["anchor_main_work"], {})

            bar_color = "#dc2626" if progress > 0 and progress < 1 else "#22c55e" if progress == 1 else "#334155"
            pct_display = int(progress * 100)

            st.markdown(
                f'<div style="background:#1e293b;border-radius:10px;padding:16px;margin-bottom:12px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<span style="font-size:16px;font-weight:700;color:#f1f5f9;">{status_icon} Bloque {block["block"]}: {block["name"]}</span>'
                f'<span style="color:#64748b;font-size:12px;margin-left:12px;">{weeks} semanas · TM {block["tm_pct"]}%</span>'
                f'</div>'
                f'<span style="color:{bar_color};font-weight:600;">{pct_display}%</span>'
                f'</div>'
                f'<div style="background:#0f172a;height:6px;border-radius:3px;margin-top:8px;">'
                f'<div style="background:{bar_color};height:6px;border-radius:3px;width:{pct_display}%;"></div>'
                f'</div>'
                f'<div style="color:#94a3b8;font-size:12px;margin-top:8px;display:flex;gap:20px;">'
                f'<span>Leader: {lt.get("name","?")} + {leader_main.get("name","?")}</span>'
                f'<span>Anchor: {at.get("name","?")} + {anchor_main.get("name","?")}</span>'
                f'</div>'
                f'</div>', unsafe_allow_html=True
            )

            cumulative += sessions_in_block

        st.divider()

        # ── Block Detail Cards ──
        st.markdown("### 📋 Detalle por bloque")

        for block in YEARLY_PLAN:
            lt = SUPPLEMENTAL_TEMPLATES.get(block["leader_template"], {})
            at = SUPPLEMENTAL_TEMPLATES.get(block["anchor_template"], {})
            weeks = get_block_weeks(block)
            leader_weeks = block["leader_cycles"] * 3
            anchor_weeks = block["anchor_cycles"] * 3

            with st.expander(f"Bloque {block['block']}: {block['name']} ({weeks} semanas)"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**🔴 Leader** ({leader_weeks} semanas)")
                    st.markdown(f"Template: **{lt.get('name', '?')}**")
                    st.markdown(f"Main work: **{block['leader_main_work']}**")
                    if "pct_by_week" in lt:
                        pcts = lt["pct_by_week"]
                        pct_str = " / ".join(f"{v*100:.0f}%" if v else "FSL" for v in pcts.values())
                        st.markdown(f"Supp %: {pct_str}")
                    if "pct_by_cycle" in lt:
                        pcts = lt["pct_by_cycle"]
                        pct_str = " → ".join(f"{v*100:.0f}%" for v in pcts.values())
                        st.markdown(f"Progresión: {pct_str}")
                    st.caption(f"{lt.get('sets_per_session', '?')}×{lt.get('reps_per_set', '?')} por sesión")

                with col2:
                    st.markdown(f"**🔵 Anchor** ({anchor_weeks} semanas)")
                    st.markdown(f"Template: **{at.get('name', '?')}**")
                    st.markdown(f"Main work: **{block['anchor_main_work']}**")
                    if "pct_by_week" in at:
                        pcts = at["pct_by_week"]
                        pct_str = " / ".join(f"{v*100:.0f}%" if v else "FSL" for v in pcts.values())
                        st.markdown(f"Supp %: {pct_str}")
                    st.caption(f"{at.get('sets_per_session', '?')}×{at.get('reps_per_set', '?')} por sesión")

                st.markdown(f"TM: **{block['tm_pct']}%** · +1 deload · +1 TM test")
                if block.get("notes"):
                    st.caption(block["notes"])

        st.divider()

        # ── TM Projection Table ──
        st.markdown("### 📈 Proyección de TMs")
        from src.config_531 import get_effective_tm
        rows = []
        cumul_bumps = 0
        # Pre-plan bumps
        pre_macros = PLAN_START_SESSION // (7 * SESSIONS_PER_WEEK)
        cumul_bumps = pre_macros * 2

        rows.append({
            "Momento": "Inicio plan",
            "Bumps": cumul_bumps,
            "OHP": f"{get_effective_tm('ohp', cumul_bumps):.0f} kg",
            "DL": f"{get_effective_tm('deadlift', cumul_bumps):.0f} kg",
            "Bench": f"{get_effective_tm('bench', cumul_bumps):.0f} kg",
            "Squat": f"{get_effective_tm('squat', cumul_bumps):.0f} kg",
        })

        for block in YEARLY_PLAN:
            bumps_in_block = block["leader_cycles"] + block["anchor_cycles"]
            cumul_bumps += bumps_in_block
            rows.append({
                "Momento": f"Fin Bloque {block['block']}",
                "Bumps": cumul_bumps,
                "OHP": f"{get_effective_tm('ohp', cumul_bumps):.0f} kg",
                "DL": f"{get_effective_tm('deadlift', cumul_bumps):.0f} kg",
                "Bench": f"{get_effective_tm('bench', cumul_bumps):.0f} kg",
                "Squat": f"{get_effective_tm('squat', cumul_bumps):.0f} kg",
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Proyección asumiendo todos los TM bumps se aplican. Los TM tests pueden bajar estos valores.")

    # ══════════════════════════════════════════════════════════════════════
    # 🧠 INTELIGENCIA 531
    # ══════════════════════════════════════════════════════════════════════
    elif page == "🧠 Inteligencia":
        _sf_header("Inteligencia 5/3/1", "🧠")

        if df_531.empty or df_531[df_531["set_type"] == "amrap"].empty:
            st.info("Necesitas al menos 1 AMRAP registrado para ver métricas de inteligencia.")
        else:
            lift_names = {"ohp": "OHP", "deadlift": "Peso Muerto", "bench": "Banca", "squat": "Sentadilla"}

            tab_tm, tab_perf, tab_joker, tab_bbb, tab_1rm = st.tabs([
                "🎯 Sostenibilidad TM",
                "📊 AMRAP Performance",
                "⚡ Joker Sets",
                "🏋️ Fatiga BBB",
                "📈 1RM Estimado",
            ])

            # ── Tab 1: TM Sustainability ──
            with tab_tm:
                _sf_sub("¿Tu Training Max es sostenible?", "🎯")
                st.markdown(
                    '<div class="sf-caption">Basado en reps AMRAP vs mínimos de Wendler. '
                    'Si no llegas al mínimo, el TM es demasiado alto.</div>',
                    unsafe_allow_html=True,
                )

                sus = tm_sustainability(df_531)

                if sus["system_health"] is not None:
                    health = sus["system_health"]
                    if health >= 0.8:
                        cls = "good"
                    elif health >= 0.4:
                        cls = "mid"
                    else:
                        cls = "bad"
                    st.markdown(
                        f'<div class="sf-gauge">'
                        f'  <div class="pct {cls}">{health:.0%}</div>'
                        f'  <div class="label">Salud del sistema</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                cols = st.columns(len(sus["lifts"]) or 1)
                for i, (lift, data) in enumerate(sus["lifts"].items()):
                    with cols[i % len(cols)]:
                        trend_icon = {"declining": "📉", "improving": "📈"}.get(data["trend"], "➡️")
                        trend_color = {"declining": "#ef4444", "improving": "#22c55e"}.get(data["trend"], "#78716c")
                        st.markdown(
                            f'<div class="sf-intel-card">'
                            f'  <div class="title">{lift_names.get(lift, lift)}</div>'
                            f'  <div class="verdict">{data["verdict"]}</div>'
                            f'  <div style="margin-top:8px;font-family:IBM Plex Mono,monospace;'
                            f'font-size:0.8rem;color:{trend_color};">'
                            f'    {trend_icon} Reps {"en descenso" if data["trend"] == "declining" else "mejorando" if data["trend"] == "improving" else "estables"}'
                            f'  </div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if data["alerts"]:
                            for alert in data["alerts"]:
                                st.warning(alert)

                # TM recommendations table
                _sf_sub("Recomendaciones TM", "⚙️")
                vtm = validate_tm(df_531)
                if vtm:
                    vtm_rows = []
                    for lift, info in vtm.items():
                        vtm_rows.append({
                            "Lift": lift_names.get(lift, lift),
                            "Estado": "✅" if info["status"] == "ok" else ("⬆️ Subir" if info["status"] == "too_light" else "⬇️ Bajar"),
                            "TM Actual": f"{info['current_tm']:.0f} kg",
                            "TM Recomendado": f"{info['recommended_tm']:.0f} kg",
                            "Delta": f"{info['tm_delta']:+.0f} kg",
                            "Avg Reps +Min": f"{info['avg_reps_over_min']:+.1f}",
                        })
                    st.dataframe(pd.DataFrame(vtm_rows), use_container_width=True, hide_index=True)

            # ── Tab 2: AMRAP Performance Index ──
            with tab_perf:
                _sf_sub("Rendimiento AMRAP — Misma semana, ¿más reps?", "📊")
                st.markdown(
                    '<div class="sf-caption">Compara tus AMRAP en el mismo tipo de semana (5s/3s/531) '
                    'a lo largo de los ciclos. Mantener o subir reps con más peso = progreso real.</div>',
                    unsafe_allow_html=True,
                )

                api = amrap_performance_index(df_531)
                if api.empty:
                    st.info("Necesitas al menos 2 ciclos para comparar.")
                else:
                    for lift in api["lift"].unique():
                        _sf_sub(lift_names.get(lift, lift), "")
                        lift_api = api[api["lift"] == lift].copy()

                        import plotly.express as px
                        fig = px.scatter(
                            lift_api, x="date", y="e1rm",
                            color="week_label", size="reps",
                            hover_data=["weight_kg", "reps", "reps_delta", "e1rm_delta"],
                            labels={"e1rm": "e1RM (kg)", "date": "", "week_label": "Semana"},
                        )
                        fig.update_layout(**PL_531, height=320)
                        fig.update_traces(marker=dict(line=dict(width=1, color="white")))
                        st.plotly_chart(fig, use_container_width=True)

                        display = lift_api[["date", "week_label", "weight_kg", "reps",
                                           "e1rm", "reps_delta", "e1rm_delta"]].copy()
                        display.columns = ["Fecha", "Semana", "Peso", "Reps", "e1RM",
                                          "Δ Reps", "Δ e1RM"]
                        display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
                        st.dataframe(display, use_container_width=True, hide_index=True)

            # ── Tab 3: Joker Analysis ──
            with tab_joker:
                _sf_sub("Joker Sets — Uso y tendencia", "⚡")
                st.markdown(
                    '<div class="sf-caption">Singles/doubles pesados después del AMRAP. '
                    'Bien usados aprovechan días buenos. Abusados acumulan fatiga.</div>',
                    unsafe_allow_html=True,
                )

                ja = joker_analysis(df_531)
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Joker Sets", ja["total_joker_sets"])
                c2.metric("Sesiones con Jokers", f"{ja['sessions_with_jokers']}/{ja['total_sessions']}")
                c3.metric("Frecuencia", f"{ja['frequency_pct']}%")

                # Assessment as styled card
                st.markdown(
                    f'<div class="sf-card">'
                    f'  <div style="font-family:Oswald,sans-serif;text-transform:uppercase;'
                    f'letter-spacing:1px;color:#a8a29e;font-size:0.75rem;margin-bottom:6px;">Valoración</div>'
                    f'  <div style="font-family:IBM Plex Mono,monospace;font-size:0.9rem;'
                    f'color:#fafaf9;">{ja["assessment"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                if ja["per_lift"]:
                    for lift, data in ja["per_lift"].items():
                        with st.expander(f"{lift_names.get(lift, lift)} — {data['count']} joker sets"):
                            jc1, jc2, jc3 = st.columns(3)
                            jc1.metric("Mejor peso", f"{data['best_weight']:.0f} kg")
                            jc2.metric("Mejor e1RM", f"{data['best_e1rm']:.0f} kg")
                            if data['avg_pct_of_tm']:
                                jc3.metric("Media %TM", f"{data['avg_pct_of_tm']:.0f}%")

            # ── Tab 4: BBB Fatigue ──
            with tab_bbb:
                _sf_sub("Fatiga en BBB 5×10", "🏋️")
                st.markdown(
                    '<div class="sf-caption">¿Pierdes reps en las últimas series del 5×10? '
                    'Si el dropoff es alto, el % BBB puede ser excesivo.</div>',
                    unsafe_allow_html=True,
                )

                bf = bbb_fatigue_trend(df_531)
                if bf.empty:
                    st.info("Sin datos BBB registrados.")
                else:
                    avg_dropoff = bf["rep_dropoff"].mean()
                    pct_perfect = (bf["all_tens"].sum() / len(bf) * 100)
                    bc1, bc2, bc3 = st.columns(3)
                    bc1.metric("Drop-off medio", f"{avg_dropoff:+.1f} reps")
                    bc2.metric("5×10 completas", f"{pct_perfect:.0f}%")
                    bc3.metric("Sesiones BBB", len(bf))

                    for lift in bf["lift"].unique():
                        lf = bf[bf["lift"] == lift].sort_values("date")
                        _sf_sub(lift_names.get(lift, lift), "")

                        display = lf[["date", "weight_kg", "reps_list", "avg_reps",
                                      "rep_dropoff", "pct_of_tm", "fatigue_status"]].copy()
                        display.columns = ["Fecha", "Peso", "Reps", "Media", "Dropoff",
                                          "%TM", "Estado"]
                        display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
                        display["Reps"] = display["Reps"].apply(lambda x: ", ".join(str(r) for r in x))
                        st.dataframe(display, use_container_width=True, hide_index=True)

            # ── Tab 5: True 1RM Trend ──
            with tab_1rm:
                _sf_sub("1RM Real Estimado", "📈")
                st.markdown(
                    '<div class="sf-caption">Tu 1RM real estimado desde AMRAPs — NO es tu Training Max. '
                    'El TM debería ser ~85-90% de este valor.</div>',
                    unsafe_allow_html=True,
                )

                t1rm = true_1rm_trend(df_531)
                if t1rm.empty:
                    st.info("Sin AMRAPs para estimar.")
                else:
                    import plotly.graph_objects as go

                    for lift in t1rm["lift"].unique():
                        lt = t1rm[t1rm["lift"] == lift].sort_values("date")
                        _sf_sub(lift_names.get(lift, lift), "")

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=lt["date"], y=lt["estimated_1rm"],
                            mode="lines+markers", name="e1RM estimado",
                            line=dict(color="#dc2626", width=2.5),
                            marker=dict(size=8),
                        ))
                        fig.add_trace(go.Scatter(
                            x=lt["date"], y=lt["running_max"],
                            mode="lines", name="Máximo histórico",
                            line=dict(color="#fbbf24", dash="dot", width=1.5),
                        ))
                        if lt["effective_tm"].notna().any():
                            fig.add_trace(go.Scatter(
                                x=lt["date"], y=lt["effective_tm"],
                                mode="lines", name="Training Max",
                                line=dict(color="#64748b", dash="dash", width=1.5),
                            ))
                        fig.update_layout(**PL_531, height=320, showlegend=True)
                        fig.update_layout(legend=dict(orientation="h", y=-0.15))
                        st.plotly_chart(fig, use_container_width=True)

                        latest = lt.iloc[-1]
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("e1RM actual", f"{latest['estimated_1rm']:.0f} kg",
                                  delta=f"{latest['e1rm_delta']:+.0f} kg" if pd.notna(latest.get("e1rm_delta")) else None)
                        rc2.metric("Running max", f"{latest['running_max']:.0f} kg")
                        if pd.notna(latest.get("tm_as_pct_of_1rm")):
                            pct = latest["tm_as_pct_of_1rm"]
                            rc3.metric("TM como % de 1RM",
                                      f"{pct:.0f}%",
                                      delta="OK" if 82 <= pct <= 92 else ("Alto" if pct > 92 else "Bajo"),
                                      delta_color="normal" if 82 <= pct <= 92 else "inverse")

    # ══════════════════════════════════════════════════════════════════════
    # ⭐ QUALITY SCORE — 531
    # ══════════════════════════════════════════════════════════════════════
    elif page == "⭐ Quality Score":
        _sf_header("Quality Score", "⭐")
        st.markdown(
            '<div class="sf-caption">Puntuación compuesta: AMRAP (40%) + BBB (30%) + Accesorios (15%) + Volumen (15%)</div>',
            unsafe_allow_html=True,
        )

        qdf = workout_quality_531(df_531)
        if qdf.empty:
            st.info("Sin datos suficientes para calcular quality score.")
        else:
            qt = quality_trend(qdf)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💀 Media", f"{qt['avg']:.0f}/100")
            c2.metric("🔥 Mejor", f"{qt['best']}/100")
            c3.metric("💀 Peor", f"{qt['worst']}/100")
            trend_emoji = {"improving": "📈", "declining": "📉", "stable": "➡️"}
            c4.metric("📊 Tendencia", trend_emoji.get(qt["trend"], "➡️"))

            fig = px.bar(
                qdf, x="date", y="quality_score", color="grade",
                color_discrete_map={"S": "#fbbf24", "A": "#22c55e", "B": "#3b82f6",
                                    "C": "#8b5cf6", "D": "#f97316", "F": "#dc2626"},
                hover_data=["lift", "amrap_score", "bbb_score", "acc_score", "vol_score"],
                labels={"quality_score": "Score", "date": "", "grade": "Nota"},
            )
            fig.update_layout(**PL_531, height=380, showlegend=True)
            fig.add_hline(y=qt["avg"], line_dash="dot", line_color="#78716c",
                         annotation_text=f"Media: {qt['avg']:.0f}",
                         annotation_font=dict(family="IBM Plex Mono", size=11, color="#a8a29e"))
            st.plotly_chart(fig, use_container_width=True)

            display = qdf[["date", "lift", "quality_score", "grade",
                          "amrap_score", "bbb_score", "acc_score", "vol_score"]].copy()
            display.columns = ["Fecha", "Lift", "Score", "Nota",
                             "AMRAP /40", "BBB /30", "Acc /15", "Vol /15"]
            display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
            lift_names = {"ohp": "OHP", "deadlift": "Peso Muerto", "bench": "Banca", "squat": "Sentadilla"}
            display["Lift"] = display["Lift"].map(lift_names).fillna(display["Lift"])
            st.dataframe(display.sort_values("Fecha", ascending=False),
                        use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # 📸 WORKOUT CARD — 531
    # ══════════════════════════════════════════════════════════════════════
    elif page == "📸 Workout Card":
        _sf_header("Workout Card", "📸")
        st.markdown(
            '<div class="sf-caption">Genera una tarjeta PNG compartible de cualquier sesión.</div>',
            unsafe_allow_html=True,
        )

        sessions = (
            df_531.drop_duplicates("hevy_id")
            .sort_values("date", ascending=False)[["date", "hevy_id", "workout_title"]]
            .head(20)
        )
        if sessions.empty:
            st.info("Sin sesiones disponibles.")
        else:
            options = {
                f"{row['date'].strftime('%d/%m')} — {row['workout_title']}": row["hevy_id"]
                for _, row in sessions.iterrows()
            }
            selected = st.selectbox("Selecciona sesión", list(options.keys()))
            hid = options[selected]

            # Build card data
            card_data = build_card_data_531(df_531, hid)
            if card_data:
                # Add quality score if available
                qdf = workout_quality_531(df_531)
                if not qdf.empty:
                    q_row = qdf[qdf["hevy_id"] == hid]
                    if not q_row.empty:
                        card_data["quality_score"] = int(q_row["quality_score"].iloc[0])
                        card_data["grade"] = q_row["grade"].iloc[0]

                try:
                    png_bytes = generate_workout_card(card_data, program="531")
                    st.image(png_bytes, use_container_width=True)
                    st.download_button(
                        "⬇️ Descargar PNG",
                        data=png_bytes,
                        file_name=f"workout_card_{card_data['date'].strftime('%Y%m%d')}.png",
                        mime="image/png",
                    )
                except ImportError:
                    st.error("Pillow no instalado. Necesario para generar cards.")

    # ══════════════════════════════════════════════════════════════════════
    # 🔍 SUSTITUCIONES — 531
    # ══════════════════════════════════════════════════════════════════════
    elif page == "🔍 Sustituciones":
        _sf_header("Ejercicios No Registrados", "🔍")
        st.markdown(
            '<div class="sf-caption">Ejercicios en tus sesiones que no están en la config de 531. '
            'Posibles sustituciones que necesitan mapear.</div>',
            unsafe_allow_html=True,
        )

        unknowns = detect_unknown_exercises(df_531, EXERCISE_DB_531, program_name="531")
        if unknowns.empty:
            st.success("✅ Todos los ejercicios están mapeados en la config.")
        else:
            st.warning(f"⚠️ {len(unknowns)} ejercicio(s) desconocido(s) detectados")
            for _, row in unknowns.iterrows():
                with st.expander(f"**{row['hevy_name']}** — {row['session_count']} sesiones"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Sesiones", row["session_count"])
                    c2.metric("Total sets", row["total_sets"])
                    c3.metric("Grupo muscular", row["suggested_muscle_group"])
                    st.code(f"Template ID: {row['template_id']}", language=None)
                    st.caption(f"Visto: {row['first_seen'].strftime('%d/%m')} → {row['last_seen'].strftime('%d/%m')}")
                    if row["appears_on"]:
                        st.caption(f"Aparece en: {row['appears_on']}")

    st.stop()  # Don't fall through to BBD sections

# ══════════════════════════════════════════════════════════════════════
# 🔥 BBD DASHBOARD (existing code below — unchanged)
# ══════════════════════════════════════════════════════════════════════
_inject_base_css()

if _bbd_error and not is_531:
    st.error(f"❌ Error cargando datos BBD: {_bbd_error}")
    st.info("Puedes cambiar a 531 BBB en el sidebar mientras se resuelve.")
    st.stop()

if df.empty:
    st.warning("No hay entrenamientos BBD registrados.")
    st.stop()

summary = global_summary(df)


# ══════════════════════════════════════════════════════════════════════
# 📊 DASHBOARD
# ══════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.markdown("## 📊 Dashboard General")

    # ── Week selector (always visible) ──
    all_weeks = sorted(int(w) for w in df["week"].unique())
    current_week = max(all_weeks) if all_weeks else 1

    week_labels = [f"Sem {w}" for w in all_weeks]
    default_idx = len(all_weeks) - 1  # last = current
    chosen_label = st.radio(
        "📅 Semana", week_labels, index=default_idx, horizontal=True,
    )
    sel_week = all_weeks[week_labels.index(chosen_label)]

    wk_df = df[df["week"] == sel_week]
    n_sess = int(wk_df["hevy_id"].nunique())
    vol = int(wk_df["volume_kg"].sum())
    sets = int(wk_df["n_sets"].sum())
    dur_mean = int(wk_df.groupby("hevy_id")["duration_min"].first().mean()) if n_sess > 0 else 0

    dl_1rm = estimate_dl_1rm(df)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sesiones", n_sess)
    c2.metric("Volumen", f"{vol:,} kg")
    c3.metric("Series", sets)
    c4.metric("Duración Media", f"{dur_mean} min")
    c5.metric("Semana", f"{sel_week} / {current_week}")
    c6.metric("DL 1RM est.", f"{dl_1rm:.0f} kg")

    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### Volumen Semanal")
        wk = weekly_breakdown(df)
        if not wk.empty:
            colors = ["#ef4444" if int(w) == sel_week else "#7f1d1d" for w in wk["week"]]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=wk["week"].apply(lambda w: f"Sem {int(w)}"), y=wk["total_volume"],
                marker_color=colors, text=wk["total_volume"].apply(lambda v: f"{v:,.0f}"),
                textposition="outside",
            ))
            fig.update_layout(**PL, yaxis_title="Volumen (kg)", showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True, key="chart_1")

    with col_right:
        st.markdown("### Volumen por Músculo")
        mv = muscle_volume(wk_df)
        if not mv.empty:
            fig = px.pie(mv, values="total_volume", names="muscle_group",
                         color="muscle_group",
                         color_discrete_map={r["muscle_group"]: r["color"] for _, r in mv.iterrows()},
                         hole=0.45)
            fig.update_layout(**PL, height=350, showlegend=True)
            fig.update_traces(textposition="inside", textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True, key="chart_2")

    # Density sparkline — selected week
    st.markdown("### ⚡ Densidad por Sesión (kg/min)")
    dens = session_density(wk_df)
    if not dens.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dens["date"].dt.strftime("%d %b"), y=dens["density_kg_min"],
            mode="lines+markers+text", text=dens["density_kg_min"],
            textposition="top center", line=dict(color="#fbbf24", width=3),
            marker=dict(size=10),
        ))
        fig.update_layout(**PL, height=250, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key="chart_3")

    # Targets — selected week
    st.markdown(f"### 🎯 vs Objetivos — Sem {sel_week}")
    wk_targets = vs_targets(wk_df)
    tc1, tc2, tc3 = st.columns(3)
    for col, t in zip([tc1, tc2, tc3], wk_targets):
        pct = min(t["pct"], 100)
        status = "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
        col.metric(f"{status} {t['metric']}", t["actual"], f"Obj: {t['target']}")


# ══════════════════════════════════════════════════════════════════════
# 📈 PROGRESIÓN
# ══════════════════════════════════════════════════════════════════════
elif page == "📈 Progresión":
    st.markdown("## 📈 Progresión de Ejercicios Clave")

    # Match key lifts by template_id (language-independent)
    key_df = df[df["exercise_template_id"].isin(KEY_LIFT_IDS)]
    available = sorted(key_df["exercise"].unique().tolist()) if not key_df.empty else []
    if not available:
        available = sorted(df[df["e1rm"] > 0]["exercise"].unique())

    selected = st.selectbox("Ejercicio", available)
    if selected:
        hist = pr_history(df, selected)
        if not hist.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=hist["date"], y=hist["e1rm"], mode="lines+markers",
                                         name="e1RM", line=dict(color="#ef4444", width=3), marker=dict(size=10)))
                fig.add_trace(go.Scatter(x=hist["date"], y=hist["running_max_e1rm"], mode="lines",
                                         name="Máximo", line=dict(color="#fbbf24", width=2, dash="dot")))
                prs_df = hist[hist["is_pr"]]
                if not prs_df.empty:
                    fig.add_trace(go.Scatter(x=prs_df["date"], y=prs_df["e1rm"], mode="markers",
                                             name="🏆 PR", marker=dict(color="#fbbf24", size=16, symbol="star")))
                fig.update_layout(**PL, title=f"e1RM — {selected}", yaxis_title="e1RM (kg)", height=400)
                st.plotly_chart(fig, use_container_width=True, key="chart_4")
            with col2:
                st.markdown("#### Historial")
                disp = hist[["date", "max_weight", "max_reps_at_max", "e1rm", "is_pr"]].copy()
                disp.columns = ["Fecha", "Peso", "Reps", "e1RM", "PR"]
                disp["Fecha"] = disp["Fecha"].dt.strftime("%d %b")
                disp["PR"] = disp["PR"].map({True: "🏆", False: ""})
                st.dataframe(disp, hide_index=True, use_container_width=True)

    # Weekly muscle volume stacked
    st.divider()
    st.markdown("### Volumen Semanal por Grupo Muscular")
    wmv = weekly_muscle_volume(df)
    if not wmv.empty:
        fig = go.Figure()
        for muscle in wmv.columns:
            color = MUSCLE_GROUP_COLORS.get(muscle, "#666")
            fig.add_trace(go.Bar(x=wmv.index.map(lambda w: f"Sem {w}"), y=wmv[muscle],
                                  name=muscle, marker_color=color))
        fig.update_layout(**PL, barmode="stack", yaxis_title="Volumen (kg)", height=400)
        st.plotly_chart(fig, use_container_width=True, key="chart_5")

    # Recovery
    st.markdown("### 🩺 Indicadores de Recuperación")
    rec = recovery_indicators(df)
    if not rec.empty:
        disp = rec[["week", "sessions", "total_volume", "vol_delta_pct",
                     "avg_fatigue", "adherence_pct", "alert"]].copy()
        disp.columns = ["Semana", "Sesiones", "Volumen", "Δ Vol %", "Fatiga Media %", "Adherencia %", "Estado"]
        disp["Volumen"] = disp["Volumen"].apply(lambda v: f"{v:,.0f}")
        disp["Δ Vol %"] = disp["Δ Vol %"].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
        disp["Fatiga Media %"] = disp["Fatiga Media %"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
        st.dataframe(disp, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# 🎯 RATIOS BBD (NEW)
# ══════════════════════════════════════════════════════════════════════
elif page == "🎯 Ratios BBD":
    st.markdown("## 🎯 Ratios BBD — Intensidad Relativa")

    dl_1rm = estimate_dl_1rm(df)
    st.metric("Deadlift 1RM estimado", f"{dl_1rm:.0f} kg",
              help="e1RM del peso muerto convencional, o inferido de Shrugs")

    st.divider()

    # BBD Ratio gauges
    st.markdown("### Cargas vs Prescripción BBD")
    st.caption("El programa BBD prescribe cargas relativas al peso muerto 1RM. ¿Estás cargando lo que deberías?")

    ratios = bbd_ratios(df)
    if not ratios.empty:
        cols = st.columns(len(ratios))
        for col, (_, row) in zip(cols, ratios.iterrows()):
            with col:
                st.markdown(f"**{row['label']}**")
                if row["current_weight"] > 0:
                    # Gauge chart
                    fig = go.Figure(go.Indicator(
                        mode="gauge+number",
                        value=row["pct_of_dl"],
                        number={"suffix": "%", "font": {"size": 32, "color": "#f1f5f9"}},
                        gauge={
                            "axis": {"range": [0, 120], "tickcolor": "#4a5568"},
                            "bar": {"color": "#ef4444"},
                            "bgcolor": "#1a1a2e",
                            "steps": [
                                {"range": [row["target_low"], row["target_high"]], "color": "rgba(34, 197, 94, 0.19)"},
                            ],
                            "threshold": {
                                "line": {"color": "#22c55e", "width": 3},
                                "value": (row["target_low"] + row["target_high"]) / 2,
                            },
                        },
                    ))
                    fig.update_layout(height=200, margin=dict(l=20, r=20, t=20, b=20),
                                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"))
                    st.plotly_chart(fig, use_container_width=True, key=f'gauge_{row["label"]}')
                    st.caption(f"{row['current_weight']}kg · Rango: {row['target_low']}-{row['target_high']}%")
                    st.markdown(row["status"])
                else:
                    st.markdown("⬜ Sin datos aún")
    else:
        st.info("No hay datos suficientes. Necesito al menos una sesión con peso muerto o shrugs.")

    # Dominadas progress
    st.divider()
    st.markdown("### 🏊 Dominadas — Objetivo: 75 reps/sesión")
    dom = dominadas_progress(df)
    if dom["best"] > 0:
        st.progress(min(dom["pct"] / 100, 1.0), text=f"{dom['best']}/{dom['target']} reps (mejor sesión)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Mejor sesión", f"{dom['best']} reps")
        c2.metric("Última sesión", f"{dom['last']} reps")
        c3.metric("Faltan", f"{dom['target'] - dom['best']} reps")
    else:
        st.info("Aún no hay sesiones con dominadas registradas.")

    # Relative intensity per exercise
    st.divider()
    st.markdown("### Intensidad Relativa por Ejercicio")
    df_ri = relative_intensity(df)
    if not df_ri.empty:
        ri_display = df_ri[df_ri["e1rm"] > 0][
            ["date", "exercise", "max_weight", "e1rm", "pct_of_pr", "pct_of_dl"]
        ].copy()
        ri_display.columns = ["Fecha", "Ejercicio", "Peso (kg)", "e1RM", "% de PR", "% de DL 1RM"]
        ri_display["Fecha"] = ri_display["Fecha"].dt.strftime("%d %b")
        st.dataframe(ri_display.sort_values("% de DL 1RM", ascending=False),
                     hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# 🔬 FATIGA INTRA-SESIÓN (NEW)
# ══════════════════════════════════════════════════════════════════════
elif page == "🔬 Fatiga Intra-sesión":
    st.markdown("## 🔬 Análisis de Fatiga Intra-sesión")
    st.caption("Dropoff de repeticiones dentro de las series de un mismo ejercicio. "
               "Si haces 8×8 Shrugs y acabas haciendo 8,8,8,7,6,5 → fatiga alta.")

    fatigue = intra_session_fatigue(df)
    if fatigue.empty:
        st.info("Se necesitan ejercicios con ≥3 series para analizar fatiga.")
        st.stop()

    # Summary cards
    c1, c2, c3 = st.columns(3)
    c1.metric("Fatiga Media", f"{fatigue['fatigue_pct'].mean():.1f}%")
    c2.metric("CV Reps Medio", f"{fatigue['cv_reps'].mean():.1f}%",
              help="Coeficiente de variación — mayor = más inconsistente")
    stable = (fatigue["pattern"].str.contains("Estable")).sum()
    c3.metric("Ejercicios Estables", f"{stable}/{len(fatigue)}")

    st.divider()

    # Fatigue by exercise
    st.markdown("### Fatiga por Ejercicio")
    fig = go.Figure()
    colors = fatigue["pattern"].map({"🟢 Estable": "#22c55e", "🟡 Moderada": "#f59e0b", "🔴 Alta": "#ef4444"})
    fig.add_trace(go.Bar(
        x=fatigue["exercise"], y=fatigue["fatigue_pct"],
        marker_color=colors, text=fatigue["pattern"],
        hovertemplate="%{x}<br>Fatiga: %{y:.1f}%<br>%{text}<extra></extra>",
    ))
    fig.add_hline(y=10, line_dash="dot", line_color="#22c55e", annotation_text="Umbral estable (10%)")
    fig.add_hline(y=25, line_dash="dot", line_color="#ef4444", annotation_text="Umbral alto (25%)")
    fig.update_layout(**PL, height=350, showlegend=False, yaxis_title="Fatiga (%)")
    st.plotly_chart(fig, use_container_width=True, key="chart_7")

    # Rep curves
    st.markdown("### Curvas de Repeticiones")
    for _, row in fatigue.iterrows():
        reps = row["reps_list"]
        with st.expander(f"{row['exercise']} — {row['weight']}kg · {row['pattern']} · Fatiga {row['fatigue_pct']}%"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(range(1, len(reps) + 1)), y=reps,
                mode="lines+markers+text", text=reps, textposition="top center",
                line=dict(color="#ef4444" if row["fatigue_pct"] > 25 else "#fbbf24" if row["fatigue_pct"] > 10 else "#22c55e", width=3),
                marker=dict(size=12),
            ))
            fig.add_hline(y=reps[0], line_dash="dot", line_color="#4a5568",
                          annotation_text=f"Serie 1: {reps[0]} reps")
            fig.update_layout(**PL, height=200, xaxis_title="Serie #", yaxis_title="Reps", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f'fatigue_{row["exercise"]}_{row["date"]}')

    # Weekly fatigue trend
    ft = fatigue_trend(df)
    if not ft.empty and len(ft) > 1:
        st.divider()
        st.markdown("### Tendencia Semanal de Fatiga")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ft["week"].apply(lambda w: f"Sem {w}"), y=ft["avg_fatigue"],
                                  mode="lines+markers", name="Media", line=dict(color="#f59e0b", width=3)))
        fig.add_trace(go.Scatter(x=ft["week"].apply(lambda w: f"Sem {w}"), y=ft["max_fatigue"],
                                  mode="lines+markers", name="Máxima", line=dict(color="#ef4444", width=2, dash="dot")))
        fig.update_layout(**PL, height=300, yaxis_title="Fatiga (%)")
        st.plotly_chart(fig, use_container_width=True, key="chart_9")


# ══════════════════════════════════════════════════════════════════════
# ⚡ DENSIDAD (NEW)
# ══════════════════════════════════════════════════════════════════════
elif page == "⚡ Densidad":
    st.markdown("## ⚡ Densidad de Entrenamiento")
    st.caption("Volumen por minuto — mide eficiencia y capacidad de trabajo. "
               "Más kg/min = mejor condición y descansos más productivos.")

    dens = session_density(df)
    if dens.empty:
        st.info("No hay sesiones registradas.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Densidad Media", f"{dens['density_kg_min'].mean():.0f} kg/min")
    c2.metric("Mejor Sesión", f"{dens['density_kg_min'].max():.0f} kg/min")
    c3.metric("Sets/min Media", f"{dens['sets_per_min'].mean():.2f}")

    st.divider()

    # Density per session
    st.markdown("### Densidad por Sesión")
    fig = go.Figure()
    colors = [DAY_CONFIG.get(d, {}).get("color", "#666") for d in dens["day_num"]]
    fig.add_trace(go.Bar(
        x=dens["date"].dt.strftime("%d %b") + " — " + dens["day_name"],
        y=dens["density_kg_min"],
        marker_color=colors,
        text=dens["density_kg_min"].apply(lambda v: f"{v:.0f}"),
        textposition="outside",
    ))
    fig.update_layout(**PL, height=350, yaxis_title="kg/min", showlegend=False)
    st.plotly_chart(fig, use_container_width=True, key="chart_10")

    # Breakdown table
    st.markdown("### Detalle")
    disp = dens[["date", "day_name", "duration_min", "total_volume", "total_sets",
                  "density_kg_min", "sets_per_min", "reps_per_min"]].copy()
    disp.columns = ["Fecha", "Día", "Duración (min)", "Volumen", "Series", "kg/min", "Sets/min", "Reps/min"]
    disp["Fecha"] = disp["Fecha"].dt.strftime("%d %b %Y")
    disp["Volumen"] = disp["Volumen"].apply(lambda v: f"{v:,.0f}")
    st.dataframe(disp, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════
# 🏋️ STRENGTH STANDARDS (NEW)
# ══════════════════════════════════════════════════════════════════════
elif page == "🏋️ Strength Standards":
    st.markdown("## 🏋️ Strength Standards — DOTS")
    st.caption(f"Nivel de fuerza ajustado por peso corporal ({BODYWEIGHT}kg). "
               "DOTS es el estándar de la IPF para comparaciones de fuerza relativa.")

    bw = st.number_input("Peso corporal (kg)", value=BODYWEIGHT, min_value=40.0, max_value=200.0, step=0.5)
    standards = strength_standards(df, bw)

    if standards.empty:
        st.info("No hay datos de ejercicios principales.")
        st.stop()

    # Level badges
    st.divider()
    for _, row in standards.iterrows():
        col1, col2, col3, col4 = st.columns([3, 1, 1, 2])
        with col1:
            st.markdown(f"**{row['exercise'][:35]}**")
            st.caption(f"e1RM: {row['best_e1rm']}kg · {row['bw_ratio']}×BW · DOTS: {row['dots_score']}")
        with col2:
            st.markdown(f"### {row['level']}")
        with col3:
            st.metric("Percentil", f"~{row['percentile']}%")
        with col4:
            if row["kg_to_next"] > 0:
                st.metric("Siguiente nivel", row["next_threshold"],
                          delta=f"+{row['kg_to_next']:.0f} kg")
            else:
                st.markdown("### 🏆")

    # Bar chart
    st.divider()
    st.markdown("### Ratio Peso/BW por Ejercicio")
    fig = go.Figure()
    colors = ["#22c55e" if "Avanzado" in r["level"] or "Elite" in r["level"]
              else "#f59e0b" if "Intermedio" in r["level"]
              else "#94a3b8" for _, r in standards.iterrows()]
    fig.add_trace(go.Bar(
        x=standards["exercise"].apply(lambda x: x[:20]),
        y=standards["bw_ratio"],
        marker_color=colors,
        text=standards["bw_ratio"].apply(lambda v: f"{v:.2f}×"),
        textposition="outside",
    ))
    fig.add_hline(y=1.0, line_dash="dot", line_color="#4a5568", annotation_text="1×BW")
    fig.add_hline(y=2.0, line_dash="dot", line_color="#f59e0b", annotation_text="2×BW")
    fig.update_layout(**PL, height=350, yaxis_title="×BW", showlegend=False)
    st.plotly_chart(fig, use_container_width=True, key="chart_11")


# ══════════════════════════════════════════════════════════════════════
# 🧠 INTELIGENCIA — Phase 1 (Plateau, ACWR, Mesociclos, Yo vs Yo)
# ══════════════════════════════════════════════════════════════════════
elif page == "🧠 Inteligencia":
    st.markdown("## 🧠 Inteligencia de Entrenamiento")
    st.caption("Detección de estancamiento, carga aguda/crónica, mesociclos y comparativas históricas.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "🔴 Estancamiento", "⚖️ ACWR", "📦 Mesociclos", "🕐 Yo vs Yo"
    ])

    # ── Tab 1: Plateau Detection ──
    with tab1:
        st.markdown("### 🔴 Detección de Estancamiento")
        st.caption("Si un ejercicio no mejora su e1RM en 3+ semanas → alerta de plateau.")

        plateaus = plateau_detection(df)
        if plateaus.empty:
            st.info("Se necesitan ≥2 semanas de datos por ejercicio para detectar estancamientos.")
        else:
            # Summary cards
            stuck = (plateaus["status"].str.contains("Estancado")).sum()
            watch = (plateaus["status"].str.contains("Vigilar")).sum()
            rising = (plateaus["status"].str.contains("Subiendo")).sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("🔴 Estancados", stuck)
            c2.metric("🟡 Vigilar", watch)
            c3.metric("🟢 Progresando", rising + (plateaus["status"].str.contains("Estable")).sum())

            st.divider()

            # Table
            disp = plateaus[["exercise", "pr_e1rm", "last_e1rm", "pct_of_pr",
                             "weeks_since_pr", "trend_slope", "status"]].copy()
            disp.columns = ["Ejercicio", "PR (e1RM)", "Último e1RM", "% del PR",
                            "Sem. sin PR", "Tendencia", "Estado"]

            # Color-code rows via status
            st.dataframe(disp, hide_index=True, use_container_width=True)

            # Alerts
            stale = plateaus[plateaus["status"].str.contains("Estancado")]
            if not stale.empty:
                st.warning(
                    "⚠️ **Ejercicios estancados:** "
                    + ", ".join(f"{r['exercise']} ({r['weeks_since_pr']} sem sin PR)" for _, r in stale.iterrows())
                    + "\n\nConsidera: variar reps/series, deload, o cambiar variante."
                )

    # ── Tab 2: ACWR ──
    with tab2:
        st.markdown("### ⚖️ Acute:Chronic Workload Ratio")
        st.caption("Compara volumen reciente vs media de últimas 4 semanas. "
                   "Zona segura: 0.8–1.3. Sobre 1.5 = riesgo de lesión/overtraining.")

        acwr_df = acwr(df)
        if acwr_df.empty or acwr_df["acwr"].isna().all():
            st.info("Se necesitan al menos 2 semanas de datos para calcular ACWR.")
        else:
            valid = acwr_df.dropna(subset=["acwr"])
            if not valid.empty:
                latest = valid.iloc[-1]

                # Big ACWR gauge
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=latest["acwr"],
                    number={"font": {"size": 48, "color": "#f1f5f9"}},
                    delta={"reference": 1.0, "position": "bottom"},
                    gauge={
                        "axis": {"range": [0.4, 2.0], "tickcolor": "#4a5568"},
                        "bar": {"color": "#ef4444"},
                        "bgcolor": "#1a1a2e",
                        "steps": [
                            {"range": [0.4, 0.8], "color": "rgba(59, 130, 246, 0.2)"},
                            {"range": [0.8, 1.3], "color": "rgba(34, 197, 94, 0.2)"},
                            {"range": [1.3, 1.5], "color": "rgba(234, 179, 8, 0.2)"},
                            {"range": [1.5, 2.0], "color": "rgba(239, 68, 68, 0.2)"},
                        ],
                    },
                ))
                fig.update_layout(
                    height=250, margin=dict(l=30, r=30, t=30, b=10),
                    paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e2e8f0"),
                )
                st.plotly_chart(fig, use_container_width=True, key="acwr_gauge")
                st.markdown(f"**Semana {int(latest['week'])}:** {latest['acwr_zone']}")

                # ACWR trend line
                st.divider()
                st.markdown("### Tendencia ACWR")
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=valid["week"].apply(lambda w: f"Sem {int(w)}"), y=valid["acwr"],
                    mode="lines+markers+text", text=valid["acwr"].apply(lambda v: f"{v:.2f}"),
                    textposition="top center", line=dict(color="#ef4444", width=3),
                    marker=dict(size=10),
                ))
                # Zone bands
                fig2.add_hrect(y0=0.8, y1=1.3, fillcolor="rgba(34,197,94,0.08)", line_width=0,
                               annotation_text="Zona segura", annotation_position="top left")
                fig2.add_hrect(y0=1.3, y1=1.5, fillcolor="rgba(234,179,8,0.08)", line_width=0)
                fig2.add_hrect(y0=1.5, y1=2.0, fillcolor="rgba(239,68,68,0.08)", line_width=0)
                fig2.add_hline(y=1.0, line_dash="dot", line_color="#4a5568")
                fig2.update_layout(**PL, height=300, yaxis_title="ACWR", showlegend=False)
                st.plotly_chart(fig2, use_container_width=True, key="acwr_trend")

                # Table
                disp = valid[["week", "acute_volume", "chronic_volume", "acwr", "acwr_zone", "sessions"]].copy()
                disp.columns = ["Semana", "Vol. Agudo", "Vol. Crónico", "ACWR", "Zona", "Sesiones"]
                disp["Vol. Agudo"] = disp["Vol. Agudo"].apply(lambda v: f"{v:,.0f}")
                disp["Vol. Crónico"] = disp["Vol. Crónico"].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
                st.dataframe(disp, hide_index=True, use_container_width=True)

    # ── Tab 3: Mesocycles ──
    with tab3:
        st.markdown("### 📦 Mesociclos — Bloques de 4 Semanas")
        st.caption("Agrupación automática del programa BBD en mesociclos de 4 semanas con comparativas.")

        meso = mesocycle_summary(df)
        if meso.empty or len(meso) < 1:
            st.info("Se necesita al menos 1 mesociclo completo (4 semanas) para análisis significativo.")
        else:
            # Mesocycle cards
            for _, m in meso.iterrows():
                weeks_label = f"Sem {int(m['week_start'])}–{int(m['week_end'])}"
                vol_delta = f" ({m['vol_delta_pct']:+.1f}%)" if pd.notna(m["vol_delta_pct"]) else ""
                fat_str = f"{m['avg_fatigue']:.1f}%" if pd.notna(m["avg_fatigue"]) else "—"

                with st.expander(
                    f"📦 Mesociclo {int(m['mesocycle'])} — {weeks_label} | "
                    f"{int(m['total_sessions'])} sesiones · "
                    f"{m['avg_weekly_volume']:,.0f} kg/sem{vol_delta}"
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Sesiones", int(m["total_sessions"]))
                    c2.metric("Vol. medio/sem", f"{m['avg_weekly_volume']:,.0f} kg",
                              delta=f"{m['vol_delta_pct']:+.1f}%" if pd.notna(m["vol_delta_pct"]) else None)
                    c3.metric("e1RM medio", f"{m['avg_e1rm']:.1f} kg",
                              delta=f"{m['e1rm_delta']:+.1f}" if pd.notna(m["e1rm_delta"]) else None)
                    c4.metric("Fatiga media", fat_str,
                              delta=f"{m['fatigue_delta']:+.1f}pp" if pd.notna(m["fatigue_delta"]) else None,
                              delta_color="inverse")

            # Mesocycle comparison chart
            if len(meso) >= 2:
                st.divider()
                st.markdown("### Evolución por Mesociclo")
                fig = go.Figure()
                x_labels = [f"Meso {int(m)}" for m in meso["mesocycle"]]
                fig.add_trace(go.Bar(
                    x=x_labels, y=meso["avg_weekly_volume"],
                    name="Vol. medio/sem", marker_color="#ef4444",
                    text=meso["avg_weekly_volume"].apply(lambda v: f"{v:,.0f}"),
                    textposition="outside",
                ))
                fig.update_layout(**PL, height=300, yaxis_title="Volumen (kg/sem)", showlegend=False)
                st.plotly_chart(fig, use_container_width=True, key="meso_vol")

    # ── Tab 4: Historical Comparison ──
    with tab4:
        st.markdown("### 🕐 Yo vs Yo — Comparativa Histórica")

        weeks_options = [2, 4, 8, 12]
        current_wk = summary.get("current_week", 1)
        available_weeks = [w for w in weeks_options if w < current_wk]

        if len(available_weeks) < 1:
            st.info(f"Llevas {current_wk} semana(s) de programa. "
                    "La comparativa histórica estará disponible a partir de la semana 3.")
        else:
            if len(available_weeks) == 1:
                weeks_ago = available_weeks[0]
                st.caption(f"Comparando vs hace {weeks_ago} semanas")
            else:
                weeks_ago = st.select_slider("Comparar vs hace X semanas", options=available_weeks,
                                             value=available_weeks[0])

            comp = historical_comparison(df, weeks_ago=weeks_ago)
            if "error" in comp:
                st.info(comp["error"])
            elif comp:
                # Volume comparison
                c1, c2, c3 = st.columns(3)
                c1.metric("Vol/sem ahora", f"{comp['volume_now']:,} kg",
                          delta=f"{comp['volume_delta_pct']:+.1f}%")
                c2.metric(f"Vol/sem hace {weeks_ago} sem", f"{comp['volume_then']:,} kg")
                c3.metric("Semana actual", comp["current_week"])

                # Exercise deltas
                if comp.get("exercise_deltas"):
                    st.divider()
                    st.markdown("### Progresión por Ejercicio")
                    ex_df = pd.DataFrame(comp["exercise_deltas"])
                    disp = ex_df[["exercise", "e1rm_then", "e1rm_now", "delta_kg", "delta_pct", "trend"]].copy()
                    disp.columns = ["Ejercicio", f"e1RM (sem {comp['compare_week']})",
                                    "e1RM actual", "Δ kg", "Δ %", ""]
                    st.dataframe(disp, hide_index=True, use_container_width=True)

                # Radar chart — strength profile
                if comp.get("profile_now") and comp.get("profile_then"):
                    st.divider()
                    st.markdown("### Perfil de Fuerza — Radar")
                    axes = list(comp["profile_now"].keys())
                    now_vals = [comp["profile_now"].get(a, 0) for a in axes]
                    then_vals = [comp["profile_then"].get(a, 0) for a in axes]

                    fig = go.Figure()
                    fig.add_trace(go.Scatterpolar(
                        r=now_vals + [now_vals[0]], theta=axes + [axes[0]],
                        fill="toself", name="Ahora",
                        fillcolor="rgba(239, 68, 68, 0.2)", line_color="#ef4444",
                    ))
                    fig.add_trace(go.Scatterpolar(
                        r=then_vals + [then_vals[0]], theta=axes + [axes[0]],
                        fill="toself", name=f"Hace {weeks_ago} sem",
                        fillcolor="rgba(59, 130, 246, 0.2)", line_color="#3b82f6",
                    ))
                    fig.update_layout(
                        polar=dict(
                            bgcolor="rgba(0,0,0,0)",
                            radialaxis=dict(range=[0, 100], showticklabels=True,
                                            gridcolor="#2d3748", tickfont=dict(color="#94a3b8")),
                            angularaxis=dict(gridcolor="#2d3748",
                                             tickfont=dict(color="#e2e8f0", size=12)),
                        ),
                        **PL, height=450, showlegend=True,
                        legend=dict(x=0.85, y=1.1),
                    )
                    st.plotly_chart(fig, use_container_width=True, key="radar_yo_vs_yo")
            else:
                st.info("No hay datos suficientes para la comparativa seleccionada.")


# ══════════════════════════════════════════════════════════════════════
# 🎮 NIVELES — RPG Gamification
# ══════════════════════════════════════════════════════════════════════
elif page == "🎮 Niveles":
    st.markdown("## 🎮 Niveles de Fuerza")
    st.caption("Sistema RPG: desbloquea logros para ganar XP y subir de nivel.")

    gam = gamification_status(df, BODYWEIGHT)

    # ── Level banner ──
    level_colors = {
        1: "#6b7280", 2: "#6b7280", 3: "#22c55e", 4: "#22c55e",
        5: "#3b82f6", 6: "#3b82f6", 7: "#a855f7", 8: "#f59e0b",
        9: "#ef4444", 10: "#ef4444",
    }
    color = level_colors.get(gam["level"], "#6b7280")

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 2px solid {color}; border-radius: 16px; padding: 24px; text-align: center;
        margin-bottom: 20px;">
        <div style="font-size: 3.5rem; margin-bottom: 4px;">⚔️</div>
        <div style="font-size: 2rem; font-weight: 700; color: {color};">
            Nivel {gam['level']} — {gam['title']}
        </div>
        <div style="color: #94a3b8; margin-top: 8px;">
            {gam['xp']} XP · {gam['unlocked']}/{gam['total']} logros desbloqueados
        </div>
    </div>
    """, unsafe_allow_html=True)

    # XP bar to next level
    if gam["level"] < 10:
        st.progress(min(gam["level_progress"], 1.0),
                     text=f"→ Nivel {gam['level']+1} ({gam['next_title']}): faltan {gam['xp_for_next']} XP")
    else:
        st.progress(1.0, text="🏆 Nivel máximo alcanzado")

    st.divider()

    # ── Achievement categories ──
    achievements = gam["achievements"]
    categories = {}
    for a in achievements:
        categories.setdefault(a["cat"], []).append(a)

    for cat_name, cat_achs in categories.items():
        unlocked_in_cat = sum(1 for a in cat_achs if a["unlocked"])
        st.markdown(f"### {cat_name}  ({unlocked_in_cat}/{len(cat_achs)})")

        cols_per_row = 3
        for i in range(0, len(cat_achs), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(cat_achs):
                    break
                a = cat_achs[idx]
                with col:
                    if a["unlocked"]:
                        border_color = "#22c55e"
                        icon = "✅"
                        opacity = "1"
                    else:
                        border_color = "#2d3748"
                        icon = "🔒"
                        opacity = "0.6"

                    pct = int(a["progress"] * 100)
                    bar_w = min(pct, 100)

                    st.markdown(f"""
                    <div style="background: #1a1a2e; border: 1px solid {border_color};
                        border-radius: 12px; padding: 14px; margin-bottom: 10px; opacity: {opacity};">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 600; color: #f1f5f9;">{icon} {a['name']}</span>
                            <span style="color: #fbbf24; font-size: 0.8rem; font-weight: 600;">{a['xp']} XP</span>
                        </div>
                        <div style="color: #94a3b8; font-size: 0.8rem; margin: 6px 0;">{a['desc']}</div>
                        <div style="background: #0f172a; border-radius: 4px; height: 8px; margin-top: 8px;">
                            <div style="background: {border_color}; width: {bar_w}%; height: 100%;
                                border-radius: 4px;"></div>
                        </div>
                        <div style="color: #64748b; font-size: 0.75rem; margin-top: 4px;">
                            {a['current']} · {pct}%
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # ── Level roadmap ──
    st.divider()
    st.markdown("### 🗺️ Roadmap de Niveles")
    from src.analytics import LEVEL_TABLE
    for lvl, xp_req, title in LEVEL_TABLE:
        if lvl <= gam["level"]:
            st.markdown(f"**✅ Nivel {lvl} — {title}** ({xp_req} XP)")
        elif lvl == gam["level"] + 1:
            st.markdown(f"**→ Nivel {lvl} — {title}** ({xp_req} XP) — *siguiente*")
        else:
            st.caption(f"🔒 Nivel {lvl} — {title} ({xp_req} XP)")


# ══════════════════════════════════════════════════════════════════════
# 🏛️ HALL OF TITANS
# ══════════════════════════════════════════════════════════════════════
elif page == "🏛️ Hall of Titans":
    st.markdown("## 🏛️ Hall of Titans")
    st.caption("Levantamientos épicos inmortalizados. Solo los dignos entran aquí.")

    titans = load_hall_of_titans()

    if not titans:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #2d3748; border-radius: 16px; padding: 40px; text-align: center;
            margin: 20px 0;">
            <div style="font-size: 4rem; margin-bottom: 12px;">⚔️</div>
            <div style="font-size: 1.4rem; font-weight: 600; color: #f1f5f9;">
                El Hall está vacío... por ahora
            </div>
            <div style="color: #94a3b8; margin-top: 12px; max-width: 500px; margin-left: auto; margin-right: auto;">
                Cuando hagas un levantamiento digno de ser recordado, grábalo, súbelo a YouTube
                (no listado) y añade una entrada en Notion.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown("### 📱 Cómo añadir un vídeo")
        st.markdown("""
1. **Graba** el levantamiento con el móvil
2. **Sube a YouTube** → Ajustes → Visibilidad: **No listado** → Publicar → Copia el enlace
3. **Abre Notion** → Base de datos **🏛️ Hall of Titans** → **+ Nuevo**
4. Rellena: **nombre** del lift, **YouTube URL**, **peso**, **ejercicio**, **tipo** (PR/Heavy/Grind...) y un **comentario** épico
5. El vídeo aparecerá aquí automáticamente en el próximo refresco ⚡
        """)
        st.link_button("📝 Abrir Hall of Titans en Notion",
                        "https://www.notion.so/34d213072fb14686910d35f3fec1062f",
                        use_container_width=True)

    else:
        # Stats bar
        total = len(titans)
        prs = sum(1 for t in titans if "PR" in t.get("epico", ""))
        heaviest = max((t["peso"] for t in titans if t.get("peso")), default=0)
        c1, c2, c3 = st.columns(3)
        c1.metric("⚔️ Hazañas", total)
        c2.metric("🔥 PRs grabados", prs)
        c3.metric("🏋️ Máximo registrado", f"{heaviest:.0f} kg" if heaviest else "—")

        st.link_button("➕ Añadir levantamiento",
                        "https://www.notion.so/34d213072fb14686910d35f3fec1062f",
                        use_container_width=True)

        st.divider()

        # Video grid
        for i in range(0, len(titans), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(titans):
                    break
                t = titans[idx]
                with col:
                    # Badge color
                    badge_colors = {
                        "🔥 PR": "#ef4444", "💪 Heavy": "#f59e0b",
                        "🎯 Técnica": "#3b82f6", "😤 Grind": "#a855f7",
                        "⭐ Hito": "#eab308",
                    }
                    badge_color = badge_colors.get(t["epico"], "#6b7280")

                    # Header
                    peso_str = f"{t['peso']:.0f}kg" if t.get("peso") else ""
                    bw_str = f" ({t['bw_ratio']:.2f}×BW)" if t.get("bw_ratio") else ""
                    fecha_str = t.get("fecha", "")

                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                        border: 1px solid #2d3748; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-weight: 700; font-size: 1.1rem; color: #f1f5f9;">
                                {t['title']}
                            </span>
                            <span style="background: {badge_color}; color: white; padding: 2px 10px;
                                border-radius: 12px; font-size: 0.8rem; font-weight: 600;">
                                {t['epico']}
                            </span>
                        </div>
                        <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 10px;">
                            {t['ejercicio']} · {peso_str}{bw_str} · {fecha_str}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Embed YouTube video
                    embed = _youtube_embed_url(t["url"])
                    if embed:
                        st.markdown(
                            f'<iframe width="100%" height="280" src="{embed}" '
                            f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; '
                            f'encrypted-media; gyroscope; picture-in-picture" '
                            f'allowfullscreen style="border-radius: 8px;"></iframe>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"[🔗 Ver vídeo]({t['url']})")

                    if t.get("comentario"):
                        st.caption(f'💬 "{t["comentario"]}"')


# ══════════════════════════════════════════════════════════════════════
# 💪 SESIONES
# ══════════════════════════════════════════════════════════════════════
elif page == "💪 Sesiones":
    st.markdown("## 💪 Historial de Sesiones")
    sessions = session_summary(df)
    if sessions.empty:
        st.info("No hay sesiones.")
    else:
        for _, s in sessions.iterrows():
            color = DAY_CONFIG.get(s["day_num"], {}).get("color", "#666")
            dens = s["total_volume"] / s["duration_min"] if s["duration_min"] > 0 else 0
            with st.expander(
                f"📅 {s['date'].strftime('%d %b %Y')} — {s['day_name']} | "
                f"{s['total_sets']} sets · {s['total_volume']:,.0f} kg · "
                f"{s['duration_min']} min · {dens:.0f} kg/min"
            ):
                detail = session_detail(df, s["hevy_id"])
                if s["description"]:
                    st.caption(f'💬 "{s["description"]}"')
                disp = detail[["exercise", "n_sets", "reps_str", "max_weight", "volume_kg", "top_set", "e1rm"]].copy()
                disp.columns = ["Ejercicio", "Series", "Reps", "Peso", "Volumen", "Top Set", "e1RM"]
                disp["Volumen"] = disp["Volumen"].apply(lambda v: f"{v:,.0f}" if v > 0 else "—")
                disp["e1RM"] = disp["e1RM"].apply(lambda v: f"{v:.1f}" if v > 0 else "—")
                disp["Peso"] = disp["Peso"].apply(lambda v: f"{v:.0f}" if v > 0 else "BW")
                st.dataframe(disp, hide_index=True, use_container_width=True)

                # Fatigue mini-analysis
                fatigue = intra_session_fatigue(detail)
                if not fatigue.empty:
                    st.markdown("**Análisis de fatiga:**")
                    for _, fr in fatigue.iterrows():
                        st.caption(f"  {fr['exercise']}: {fr['pattern']} (dropoff {fr['fatigue_pct']}%, CV {fr['cv_reps']}%)")


# ══════════════════════════════════════════════════════════════════════
# 🏆 PRs
# ══════════════════════════════════════════════════════════════════════
elif page == "🏆 PRs":
    st.markdown("## 🏆 Records Personales — BBD")
    prs = pr_table(df)
    if prs.empty:
        st.info("Aún no hay PRs.")
    else:
        top3 = prs.head(3)
        cols = st.columns(3)
        medals = ["🥇", "🥈", "🥉"]
        for i, (col, (_, row)) in enumerate(zip(cols, top3.iterrows())):
            with col:
                st.markdown(f"### {medals[i]} {row['exercise'][:25]}")
                st.metric("e1RM", f"{row['e1rm']} kg")
                bw_ratio = row["e1rm"] / BODYWEIGHT
                st.caption(f"{row['max_weight']}kg × {row['max_reps_at_max']} · {bw_ratio:.2f}×BW · {row['date'].strftime('%d %b')}")
        st.divider()
        disp = prs[["exercise", "max_weight", "max_reps_at_max", "e1rm", "date", "day_name"]].copy()
        disp.columns = ["Ejercicio", "Peso", "Reps", "e1RM", "Fecha", "Día"]
        disp["Fecha"] = disp["Fecha"].dt.strftime("%d %b %Y")
        disp["×BW"] = (disp["e1RM"] / BODYWEIGHT).round(2)
        st.dataframe(disp, hide_index=True, use_container_width=True, height=400)


# ══════════════════════════════════════════════════════════════════════
# 🎯 ADHERENCIA
# ══════════════════════════════════════════════════════════════════════
elif page == "🎯 Adherencia":
    st.markdown("## 🎯 Adherencia al Programa")
    adh = day_adherence(df)
    cols = st.columns(3)
    for i, (_, row) in enumerate(adh.iterrows()):
        with cols[i % 3]:
            color = DAY_CONFIG.get(row["day_num"], {}).get("color", "#666")
            last = row["last_date"].strftime("%d %b") if pd.notna(row["last_date"]) else "—"
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #1a1a2e, #16213e);
                border-left: 4px solid {color}; border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                <div style="font-size: 1.5rem;">{row['status']}</div>
                <div style="font-weight: 600; color: #f1f5f9;">{row['day_name']}</div>
                <div style="color: #94a3b8; font-size: 0.85rem;">{row['focus']}</div>
                <div style="color: #e2e8f0; margin-top: 8px;">{row['times_completed']}× · Última: {last}</div>
            </div>""", unsafe_allow_html=True)

    completed = adh["times_completed"].gt(0).sum()
    st.progress(completed / 6, text=f"Cobertura: {completed}/6 días completados al menos 1 vez")

    wk = weekly_breakdown(df)
    if not wk.empty:
        st.markdown("### Sesiones por Semana")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=wk["week"].apply(lambda w: f"Sem {w}"), y=wk["sessions"],
                              marker_color="#22c55e", text=wk["sessions"], textposition="outside"))
        fig.add_hline(y=5, line_dash="dot", line_color="#ef4444", annotation_text="Objetivo: 5-6")
        fig.update_layout(**PL, height=300, yaxis_title="Sesiones", showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key="chart_12")

# ══════════════════════════════════════════════════════════════════════
# ⭐ QUALITY SCORE — BBD
# ══════════════════════════════════════════════════════════════════════
elif page == "⭐ Quality Score":
    st.markdown("## ⭐ Quality Score")
    st.caption("Puntuación compuesta: Key Lift (35%) + Volumen (25%) + Cobertura (25%) + Consistencia (15%)")

    qdf = workout_quality_bbd(df, DAY_CONFIG, EXERCISE_DB)
    if qdf.empty:
        st.info("Sin datos suficientes.")
    else:
        qt = quality_trend(qdf)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Media", f"{qt['avg']:.0f}/100")
        c2.metric("Mejor", f"{qt['best']}/100")
        c3.metric("Peor", f"{qt['worst']}/100")
        trend_emoji = {"improving": "📈", "declining": "📉", "stable": "➡️"}
        c4.metric("Tendencia", trend_emoji.get(qt["trend"], "➡️"))

        fig = px.bar(
            qdf, x="date", y="quality_score", color="grade",
            color_discrete_map={"S": "#f59e0b", "A": "#10b981", "B": "#3b82f6",
                                "C": "#8b5cf6", "D": "#f97316", "F": "#ef4444"},
            hover_data=["day_name", "lift_score", "vol_score", "cov_score", "dur_score"],
            labels={"quality_score": "Score", "date": "", "grade": "Nota"},
        )
        fig.update_layout(**PL, height=350, showlegend=True)
        fig.add_hline(y=qt["avg"], line_dash="dot", line_color="#94a3b8",
                     annotation_text=f"Media: {qt['avg']:.0f}")
        st.plotly_chart(fig, use_container_width=True, key="chart_quality_bbd")

        display = qdf[["date", "day_name", "quality_score", "grade",
                      "lift_score", "vol_score", "cov_score", "dur_score"]].copy()
        display.columns = ["Fecha", "Día", "Score", "Nota",
                         "Lift /35", "Vol /25", "Cov /25", "Dur /15"]
        display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
        st.dataframe(display.sort_values("Fecha", ascending=False),
                    use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════
# 📸 WORKOUT CARD — BBD
# ══════════════════════════════════════════════════════════════════════
elif page == "📸 Workout Card":
    st.markdown("## 📸 Workout Card")
    st.caption("Genera una tarjeta PNG compartible de cualquier sesión.")

    sessions = (
        df.drop_duplicates("hevy_id")
        .sort_values("date", ascending=False)[["date", "hevy_id", "day_name"]]
        .head(20)
    )
    if sessions.empty:
        st.info("Sin sesiones disponibles.")
    else:
        options = {
            f"{row['date'].strftime('%d/%m')} — {row['day_name']}": row["hevy_id"]
            for _, row in sessions.iterrows()
        }
        selected = st.selectbox("Selecciona sesión", list(options.keys()))
        hid = options[selected]

        card_data = build_card_data_bbd(df, hid, EXERCISE_DB)
        if card_data:
            qdf = workout_quality_bbd(df, DAY_CONFIG, EXERCISE_DB)
            if not qdf.empty:
                q_row = qdf[qdf["hevy_id"] == hid]
                if not q_row.empty:
                    card_data["quality_score"] = int(q_row["quality_score"].iloc[0])
                    card_data["grade"] = q_row["grade"].iloc[0]

            try:
                png_bytes = generate_workout_card(card_data, program="BBD")
                st.image(png_bytes, use_container_width=True)
                st.download_button(
                    "⬇️ Descargar PNG",
                    data=png_bytes,
                    file_name=f"workout_card_{card_data['date'].strftime('%Y%m%d')}.png",
                    mime="image/png",
                )
            except ImportError:
                st.error("Pillow no instalado. Necesario para generar cards.")

# ══════════════════════════════════════════════════════════════════════
# 🔍 SUSTITUCIONES — BBD
# ══════════════════════════════════════════════════════════════════════
elif page == "🔍 Sustituciones":
    st.markdown("## 🔍 Ejercicios No Registrados")
    st.caption("Ejercicios en tus sesiones que no están en EXERCISE_DB. "
               "Posibles sustituciones que necesitan mapear.")

    unknowns = detect_unknown_exercises(df, EXERCISE_DB, program_name="BBD")
    if unknowns.empty:
        st.success("✅ Todos los ejercicios están mapeados en EXERCISE_DB.")
    else:
        st.warning(f"⚠️ {len(unknowns)} ejercicio(s) desconocido(s) detectados")
        for _, row in unknowns.iterrows():
            with st.expander(f"**{row['hevy_name']}** — {row['session_count']} sesiones"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Sesiones", row["session_count"])
                c2.metric("Total sets", row["total_sets"])
                c3.metric("Grupo muscular", row["suggested_muscle_group"])
                st.code(f"Template ID: {row['template_id']}", language=None)
                st.caption(f"Visto: {row['first_seen'].strftime('%d/%m')} → {row['last_seen'].strftime('%d/%m')}")
                if row["appears_on"]:
                    st.caption(f"Aparece en día(s): {row['appears_on']}")

# ── Footer ───────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    f"{summary.get('total_sessions', 0)} sesiones · "
    f"{summary.get('total_volume', 0):,} kg · "
    f"Sem {summary.get('current_week', '?')}"
)
