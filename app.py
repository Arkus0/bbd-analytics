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
    """Render Google Calendar style monthly view with mobile support."""
    from calendar import monthrange, monthcalendar
    from datetime import date
    
    weeks = cal_data["weeks"]
    year = cal_data.get("year", 2026)
    
    # Map weeks to their data
    week_data = {w["abs_week"]: w for w in weeks}
    
    # Color mapping
    color_map = {
        "5s": "#3b82f6",
        "3s": "#f59e0b", 
        "531": "#ef4444",
        "deload": "#22c55e",
    }
    
    # Month names
    month_names = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    # Days of week
    days_header = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    
    # Program start
    program_start = date(year, 1, 1)
    
    # Detect mobile using streamlit's query params or session state
    # Simple detection: check screen width via JavaScript or use a toggle
    is_mobile = st.toggle("📱 Modo móvil (mostrar 1 mes)", value=False, key="mobile_mode")
    
    if is_mobile:
        # Mobile: show month selector
        month_idx = st.selectbox("Mes", range(12), format_func=lambda x: month_names[x], key="month_selector")
        months_to_show = [month_idx]
    else:
        # Desktop: show all months
        months_to_show = range(12)
    
    for month_idx in months_to_show:
        month_name = month_names[month_idx]
        
        # Get calendar matrix for this month
        cal_matrix = monthcalendar(year, month_idx + 1)
        
        st.markdown(f"### {month_name} {year}")
        
        # Header row with days of week
        header_cols = st.columns(7)
        for i, day_name in enumerate(days_header):
            with header_cols[i]:
                st.markdown(f"**{day_name}**")
        
        # Each week row
        for week in cal_matrix:
            week_cols = st.columns(7)
            for day_idx, day in enumerate(week):
                with week_cols[day_idx]:
                    if day == 0:
                        st.markdown("")
                    else:
                        current_date = date(year, month_idx + 1, day)
                        days_since_start = (current_date - program_start).days
                        abs_week = (days_since_start // 7) + 1
                        
                        if abs_week in week_data:
                            w = week_data[abs_week]
                            color = color_map.get(w["type"], "#6b7280")
                            is_current = w["status"] == "current"
                            border_color = "#2563eb" if is_current else color
                            border_width = "3px" if is_current else "2px"
                            
                            st.markdown(
                                f"""
                                <div style="
                                    width: 32px;
                                    height: 32px;
                                    border-radius: 50%;
                                    background-color: {color};
                                    border: {border_width} solid {border_color};
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    margin: 0 auto;
                                    font-size: 12px;
                                    font-weight: bold;
                                    color: white;
                                    text-shadow: 0 0 2px black;
                                ">{day}</div>
                                """,
                                unsafe_allow_html=True
                            )
                            st.caption(f"W{abs_week}")
                        else:
                            st.markdown(
                                f"""
                                <div style="
                                    width: 32px;
                                    height: 32px;
                                    border-radius: 50%;
                                    background-color: #e5e7eb;
                                    border: 2px solid #d1d5db;
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    margin: 0 auto;
                                    font-size: 12px;
                                    color: #6b7280;
                                ">{day}</div>
                                """,
                                unsafe_allow_html=True
                            )
        
        st.markdown("---")
    
    # Legend
    st.markdown("### Leyenda")
    cols = st.columns(6)
    with cols[0]: 
        st.markdown("""
        <div style="display:flex;align-items:center;gap:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;"></div>
            <span>5s</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[1]: 
        st.markdown("""
        <div style="display:flex;align-items:center;gap:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:#f59e0b;"></div>
            <span>3s</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[2]: 
        st.markdown("""
        <div style="display:flex;align-items:center;gap:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:#ef4444;"></div>
            <span>531</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[3]: 
        st.markdown("""
        <div style="display:flex;align-items:center;gap:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:#22c55e;"></div>
            <span>Deload</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[4]: 
        st.markdown("""
        <div style="display:flex;align-items:center;gap:5px;">
            <div style="width:16px;height:16px;border-radius:50%;background:#6b7280;border:3px solid #2563eb;"></div>
            <span>Actual</span>
        </div>
        """, unsafe_allow_html=True)


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
    /* Mobile responsive */
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

PL = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk", color="#e2e8f0"), margin=dict(l=40, r=20, t=40, b=40),
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
        st.caption(f"Wendler's 531 Boring But Big — desde {pd.Timestamp(PROGRAM_START_531).strftime('%d %b %Y')}")
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
    if _531_error:
        st.error(f"❌ Error cargando datos 531: {_531_error}")
        st.info("Puedes cambiar a BBD en el sidebar mientras se resuelve.")
        st.stop()
    df_531 = load_531_data()

    # Planner works even with no data
    if page == "📋 Hoy te toca":
        plan = next_session_plan(df_531)

        # Header with cycle/week context
        st.markdown(f"## 📋 Hoy te toca — {plan['lift_label']}")
        st.markdown(
            f"**Ciclo {plan['cycle_num']}** · **{plan['week_name']}** · "
            f"Día {plan['day_num']}: {plan['focus']}"
        )

        if plan["tm"] is None:
            st.warning(f"⚠️ Training Max de {plan['lift_label']} no configurado. Dime tu TM y lo actualizo.")
        else:
            st.caption(f"TM: {plan['tm']} kg")
            st.divider()

            # ── Warmup ──
            st.markdown("### 🔥 Calentamiento")
            for s in plan["warmup"]:
                pct_display = int(s["pct"] * 100)
                st.markdown(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;`{s['weight']:g} kg` × {s['reps']} &nbsp;&nbsp;"
                    f"({pct_display}%) &nbsp;&nbsp;→ &nbsp;&nbsp;🔩 **{s['plates_str']}**"
                )

            st.divider()

            # ── Working sets (the main event) ──
            st.markdown("### 💀 Series de trabajo")
            for s in plan["working_sets"]:
                pct_display = int(s["pct"] * 100)
                reps_display = s["reps"]
                if s["is_amrap"]:
                    st.markdown(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;🔴 `{s['weight']:g} kg` × **{reps_display}** &nbsp;&nbsp;"
                        f"({pct_display}%) &nbsp;&nbsp;→ &nbsp;&nbsp;🔩 **{s['plates_str']}** &nbsp;&nbsp;⚡ **AMRAP**"
                    )
                else:
                    st.markdown(
                        f"&nbsp;&nbsp;&nbsp;&nbsp;⚪ `{s['weight']:g} kg` × {reps_display} &nbsp;&nbsp;"
                        f"({pct_display}%) &nbsp;&nbsp;→ &nbsp;&nbsp;🔩 **{s['plates_str']}**"
                    )

            st.divider()

            # ── BBB ──
            bbb = plan["bbb"]
            if bbb:
                pct_display = int(bbb["pct_tm"] * 100)
                st.markdown("### 📦 BBB Supplemental")
                st.markdown(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;`{bbb['weight']:g} kg` × {bbb['reps']} × {bbb['sets']} sets &nbsp;&nbsp;"
                    f"({pct_display}% TM) &nbsp;&nbsp;→ &nbsp;&nbsp;🔩 **{bbb['plates_str']}**"
                )

            st.divider()

            # ── Full week overview ──
            st.markdown("### 📅 Esta semana completa")
            week_plans = full_week_plan(df_531)
            cols = st.columns(4)
            for i, dp in enumerate(week_plans):
                with cols[i]:
                    is_next = (dp["day_num"] == plan["day_num"])
                    marker = " ← 👈" if is_next else ""
                    st.markdown(f"**{dp['lift_label']}**{marker}")
                    if dp["tm"]:
                        for s in dp["sets"]:
                            pct_d = int(s["pct"] * 100)
                            reps_d = s["reps"]
                            if s["is_amrap"]:
                                st.markdown(f"🔴 {s['weight']:g}kg × {reps_d}")
                            else:
                                st.caption(f"{s['weight']:g}kg × {reps_d} ({pct_d}%)")
                        st.caption(f"BBB: {dp.get('bbb_weight', '?')}kg 5×10")
                    else:
                        st.caption("TM pendiente")

        st.stop()

    if df_531.empty:
        st.warning("No hay entrenamientos 531 BBB registrados todavía.")
        st.info("Asegúrate de iniciar el workout desde la rutina BBB en Hevy para que se detecte automáticamente.")
        st.stop()

    summary_531 = global_summary_531(df_531)

    if page == "📊 Dashboard":
        st.markdown("## 💀 531 BBB — Dashboard")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sesiones", summary_531.get("total_sessions", 0))
        c2.metric("Volumen Total", f"{summary_531.get('total_volume_kg', 0):,} kg")
        c3.metric("Sets Totales", summary_531.get("total_sets", 0))
        c4.metric("AMRAPs", summary_531.get("amrap_count", 0))

        st.divider()

        # Training Maxes
        st.markdown("### 🎯 Training Maxes")
        tm_cols = st.columns(4)
        lift_labels = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
        lift_emojis = {"ohp": "🏋️", "deadlift": "💀", "bench": "🪑", "squat": "🦵"}
        for i, (lift, label) in enumerate(lift_labels.items()):
            tm = TRAINING_MAX.get(lift)
            if tm:
                tm_cols[i].metric(f"{lift_emojis[lift]} {label}", f"{tm} kg")
            else:
                tm_cols[i].metric(f"{lift_emojis[lift]} {label}", "TBD")

        st.divider()

        # AMRAP summary — latest per lift only
        amraps = amrap_tracking(df_531)
        if not amraps.empty:
            amraps = amraps.sort_values("date").groupby("lift").tail(1)
            st.markdown("### 🎯 Últimos AMRAPs")
            for _, row in amraps.iterrows():
                lift_label = lift_labels.get(row["lift"], row["lift"])
                over = row["reps_over_min"]
                emoji = "🟢" if over >= 3 else "🟡" if over >= 0 else "🔴"
                st.markdown(
                    f"{emoji} **{lift_label}** — {row['weight_kg']}kg × **{row['reps']}** reps "
                    f"(mín: {row['min_reps']}, +{over}) → e1RM: **{row['e1rm']}kg**"
                )

        st.divider()

        # BBB compliance — latest per lift only
        bbb = bbb_compliance(df_531)
        if not bbb.empty:
            bbb = bbb.sort_values("date").groupby("lift").tail(1)
            st.markdown("### 📦 BBB Supplemental")
            for _, row in bbb.iterrows():
                lift_label = lift_labels.get(row["lift"], str(row["lift"]))
                status = "✅" if row["sets_ok"] and row["reps_ok"] else "⚠️"
                pct = f" ({row['pct_of_tm']}% TM)" if row["pct_of_tm"] else ""
                st.markdown(
                    f"{status} **{lift_label}** — {row['weight_kg']}kg{pct} | "
                    f"{row['n_sets']} sets × {row['avg_reps']} reps avg (total: {row['total_reps']})"
                )

        # FSL compliance — latest per lift only
        fsl = fsl_compliance(df_531)
        if not fsl.empty:
            fsl = fsl.sort_values("date").groupby("lift").tail(1)
            st.markdown("### 🔁 FSL (First Set Last)")
            st.caption("Suplementario con el peso del primer working set — 3-5 sets × 5-8 reps.")
            for _, row in fsl.iterrows():
                lift_label = lift_labels.get(row["lift"], str(row["lift"]))
                status = "✅" if row["sets_ok"] and row["reps_ok"] else "⚠️"
                pct = f" ({row['pct_of_tm']}% TM)" if row["pct_of_tm"] else ""
                st.markdown(
                    f"{status} **{lift_label}** — {row['weight_kg']}kg{pct} | "
                    f"{row['n_sets']} sets × {row['avg_reps']} reps avg"
                )

        # Joker sets — latest per lift only
        jokers = joker_sets_summary(df_531)
        if not jokers.empty:
            jokers = jokers.sort_values("date").groupby("lift").tail(1)
            st.divider()
            st.markdown("### 🃏 Joker Sets")
            st.caption("Sets pesados extra post-AMRAP — singles/doubles/triples por encima del top set.")
            jk_cols = st.columns(2)
            jk_cols[0].metric("Total Joker Sets", int(jokers["total_sets"].sum()))
            jk_cols[1].metric("Mejor e1RM (Joker)", f"{jokers['best_e1rm'].max():.1f} kg")
            for _, jrow in jokers.iterrows():
                lift_label = lift_labels.get(jrow["lift"], str(jrow["lift"]))
                st.markdown(
                    f"🃏 **{lift_label}** — {jrow['date'].strftime('%d %b')} — "
                    f"{jrow['weight_kg']}kg × {jrow['best_reps']} ({jrow['total_sets']} sets) → "
                    f"e1RM: **{jrow['best_e1rm']:.1f}kg**"
                )

        # Accessory summary
        acc = accessory_summary(df_531)
        if not acc.empty:
            st.markdown("### 🔧 Accesorios")
            for _, row in acc.iterrows():
                st.markdown(
                    f"**{row['muscle_group']}** — {row['total_sets']} sets, "
                    f"{row['total_reps']} reps, {row['total_volume']:,.0f} kg"
                )

    elif page == "🎯 AMRAP Tracker":
        st.markdown("## 🎯 AMRAP Tracker")
        st.caption("La serie AMRAP es el pulso de tu progresión en 531.")

        # TM Validation alerts
        tm_val = validate_tm(df_531)
        if tm_val:
            for lift, info in tm_val.items():
                lift_label = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}.get(lift, lift)
                if info["status"] == "too_light":
                    st.warning(
                        f"⚠️ **{lift_label}**: TM parece bajo — promedio +{info['avg_reps_over_min']} reps sobre mínimo. "
                        f"TM actual: {info['current_tm']}kg → Recomendado: **{info['recommended_tm']}kg** "
                        f"(+{info['tm_delta']}kg)"
                    )
                elif info["status"] == "too_heavy":
                    st.error(
                        f"🔴 **{lift_label}**: TM parece alto — promedio {info['avg_reps_over_min']} reps sobre mínimo. "
                        f"TM actual: {info['current_tm']}kg → Recomendado: **{info['recommended_tm']}kg** "
                        f"({info['tm_delta']}kg)"
                    )
                else:
                    st.success(
                        f"✅ **{lift_label}**: TM calibrado — +{info['avg_reps_over_min']} reps/AMRAP. "
                        f"e1RM: {info['latest_e1rm']}kg, TM: {info['current_tm']}kg"
                    )
            st.divider()

        amraps = amrap_tracking(df_531)
        if amraps.empty:
            st.info("Sin datos de AMRAP aún.")
        else:
            # AMRAP table
            display = amraps.copy()
            display["lift"] = display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            display.columns = ["Fecha", "Lift", "Peso (kg)", "Reps", "e1RM",
                               "Mín Reps", "+Sobre Mín", "% TM"]
            st.dataframe(display, use_container_width=True, hide_index=True)

            # AMRAP e1RM chart
            st.markdown("### 📈 e1RM desde AMRAPs")
            prog = lift_progression(df_531)
            if not prog.empty:
                prog_display = prog.copy()
                prog_display["lift"] = prog_display["lift"].map(
                    {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
                )
                fig = px.line(
                    prog_display, x="date", y="e1rm", color="lift",
                    markers=True, title="e1RM por lift (AMRAP)",
                    labels={"date": "", "e1rm": "e1RM (kg)", "lift": ""},
                )
                fig.update_layout(**PL)
                st.plotly_chart(fig, use_container_width=True)

        # Supplemental compliance section (BBB or FSL)
        st.divider()
        bbb = bbb_compliance(df_531)
        fsl = fsl_compliance(df_531)
        if not bbb.empty:
            st.markdown("### 📦 BBB Supplemental Compliance")
            bbb_display = bbb[["date", "lift", "weight_kg", "n_sets", "total_reps", "avg_reps", "pct_of_tm"]].copy()
            bbb_display["lift"] = bbb_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            bbb_display.columns = ["Fecha", "Lift", "Peso (kg)", "Sets", "Total Reps", "Avg Reps", "% TM"]
            st.dataframe(bbb_display, use_container_width=True, hide_index=True)
        if not fsl.empty:
            st.markdown("### 🔁 FSL Compliance")
            fsl_display = fsl[["date", "lift", "weight_kg", "n_sets", "total_reps", "avg_reps", "pct_of_tm"]].copy()
            fsl_display["lift"] = fsl_display["lift"].map(
                {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
            )
            fsl_display.columns = ["Fecha", "Lift", "Peso (kg)", "Sets", "Total Reps", "Avg Reps", "% TM"]
            st.dataframe(fsl_display, use_container_width=True, hide_index=True)
        if bbb.empty and fsl.empty:
            st.info("Sin datos de suplementario aún.")

    elif page == "📈 Progresión":
        st.markdown("## 📈 Progresión")

        # TM progression
        st.markdown("### 🎯 Training Max vs Estimated")
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
        st.divider()
        st.markdown("### 📊 Volumen Semanal")
        wv = weekly_volume_531(df_531)
        if not wv.empty:
            fig = px.bar(
                wv, x="week_start", y="total_volume", color="set_type",
                title="Volumen por semana y tipo de serie",
                labels={"week_start": "", "total_volume": "Volumen (kg)", "set_type": "Tipo"},
                color_discrete_map={
                    "warmup": "#64748b", "working_531": "#ef4444",
                    "amrap": "#f59e0b", "bbb": "#3b82f6", "fsl": "#8b5cf6",
                    "joker": "#ec4899", "accessory": "#22c55e",
                },
            )
            fig.update_layout(**PL)
            st.plotly_chart(fig, use_container_width=True)

        # Cycle comparison
        st.divider()
        st.markdown("### 🔄 Ciclo vs Ciclo")
        cyc = cycle_comparison(df_531)
        if not cyc.empty and cyc["cycle_num"].nunique() >= 1:
            # Table
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

            # Chart: grouped bar of best e1RM per lift per cycle
            if cyc["cycle_num"].nunique() >= 2:
                cyc_chart = cyc.copy()
                cyc_chart["lift"] = cyc_chart["lift"].map(
                    {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}
                )
                cyc_chart["cycle_label"] = "Ciclo " + cyc_chart["cycle_num"].astype(str)
                fig = px.bar(
                    cyc_chart, x="lift", y="amrap_best_e1rm", color="cycle_label",
                    barmode="group", title="Mejor e1RM por lift y ciclo",
                    labels={"lift": "", "amrap_best_e1rm": "e1RM (kg)", "cycle_label": ""},
                )
                fig.update_layout(**PL)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Se necesita al menos 1 ciclo completo para comparar.")

        # Muscle volume
        st.divider()
        st.markdown("### 💪 Distribución Muscular")
        mv = muscle_volume_531(df_531)
        if not mv.empty:
            fig = px.pie(
                mv, values="total_volume", names="muscle_group",
                title="Volumen por grupo muscular",
            )
            fig.update_layout(**PL)
            st.plotly_chart(fig, use_container_width=True)

    elif page == "🏋️ Strength Standards":
        st.markdown("## 🏋️ Strength Standards (531)")

        levels = strength_level_531(df_531)
        lift_labels = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Zercher"}

        for lift, label in lift_labels.items():
            info = levels.get(lift, {})
            e1rm = info.get("e1rm")
            ratio = info.get("ratio_bw")
            level = info.get("level", "Sin datos")

            level_colors = {
                "Elite": "🟣", "Avanzado": "🔵", "Intermedio": "🟢",
                "Principiante": "🟡", "Novato": "⚪", "Sin datos": "⬜",
            }
            emoji = level_colors.get(level, "⬜")

            if e1rm:
                st.markdown(f"{emoji} **{label}** — e1RM: {e1rm}kg ({ratio}×BW) → **{level}**")

                # Progress bar to next level
                stds = STRENGTH_STANDARDS_531[lift]
                levels_order = ["beginner", "intermediate", "advanced", "elite"]
                for j, lvl in enumerate(levels_order):
                    if ratio < stds[lvl]:
                        target = stds[lvl] * BODYWEIGHT
                        prev = stds[levels_order[j-1]] * BODYWEIGHT if j > 0 else 0
                        progress = (e1rm - prev) / (target - prev) if target > prev else 1
                        st.progress(min(progress, 1.0), text=f"→ {levels_order[j].title()}: {target:.0f}kg ({stds[lvl]}×BW)")
                        break
                else:
                    st.progress(1.0, text="🏆 Elite alcanzado")
            else:
                st.markdown(f"{emoji} **{label}** — {level}")

            st.divider()

    elif page == "💪 Sesiones":
        st.markdown("## 💪 Sesiones")

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

    elif page == "🏆 PRs":
        st.markdown("## 🏆 PRs")

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
        st.markdown("## 📅 Calendario Beyond 5/3/1")

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
        st.markdown("## 🗓️ Calendario Anual 5/3/1")
        
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
    # 🧠 INTELIGENCIA 531
    # ══════════════════════════════════════════════════════════════════════
    elif page == "🧠 Inteligencia":
        st.markdown("## 🧠 Inteligencia 5/3/1")

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
                st.markdown("### ¿Tu Training Max es sostenible?")
                st.caption("Basado en reps AMRAP vs mínimos de Wendler. Si no llegas al mínimo, el TM es demasiado alto.")

                sus = tm_sustainability(df_531)

                if sus["system_health"] is not None:
                    health = sus["system_health"]
                    if health >= 0.8:
                        color, emoji = "green", "🟢"
                    elif health >= 0.4:
                        color, emoji = "orange", "🟡"
                    else:
                        color, emoji = "red", "🔴"
                    st.markdown(f"**Salud del sistema:** {emoji} {health:.0%}")

                cols = st.columns(len(sus["lifts"]) or 1)
                for i, (lift, data) in enumerate(sus["lifts"].items()):
                    with cols[i % len(cols)]:
                        st.markdown(f"**{lift_names.get(lift, lift)}**")
                        st.markdown(f"{data['verdict']}")
                        if data["trend"] == "declining":
                            st.caption("📉 Reps en descenso")
                        elif data["trend"] == "improving":
                            st.caption("📈 Reps mejorando")
                        else:
                            st.caption("➡️ Reps estables")
                        if data["alerts"]:
                            for alert in data["alerts"]:
                                st.warning(alert)

                # Also show validate_tm recommendations
                st.divider()
                st.markdown("### Recomendaciones TM")
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
                st.markdown("### Rendimiento AMRAP — Misma semana, ¿más reps?")
                st.caption("Compara tus AMRAP en el mismo tipo de semana (5s/3s/531) a lo largo de los ciclos. "
                           "Mantener o subir reps con más peso = progreso real.")

                api = amrap_performance_index(df_531)
                if api.empty:
                    st.info("Necesitas al menos 2 ciclos para comparar.")
                else:
                    for lift in api["lift"].unique():
                        st.markdown(f"#### {lift_names.get(lift, lift)}")
                        lift_api = api[api["lift"] == lift].copy()

                        # Chart: e1RM over time colored by week_type
                        import plotly.express as px
                        fig = px.scatter(
                            lift_api, x="date", y="e1rm",
                            color="week_label", size="reps",
                            hover_data=["weight_kg", "reps", "reps_delta", "e1rm_delta"],
                            labels={"e1rm": "e1RM (kg)", "date": "", "week_label": "Semana"},
                        )
                        fig.update_layout(**PL, height=300)
                        fig.update_traces(marker=dict(line=dict(width=1, color="white")))
                        st.plotly_chart(fig, use_container_width=True)

                        # Summary table
                        display = lift_api[["date", "week_label", "weight_kg", "reps",
                                           "e1rm", "reps_delta", "e1rm_delta"]].copy()
                        display.columns = ["Fecha", "Semana", "Peso", "Reps", "e1RM",
                                          "Δ Reps", "Δ e1RM"]
                        display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
                        st.dataframe(display, use_container_width=True, hide_index=True)

            # ── Tab 3: Joker Analysis ──
            with tab_joker:
                st.markdown("### Joker Sets — Uso y tendencia")
                st.caption("Singles/doubles pesados después del AMRAP. "
                           "Bien usados aprovechan días buenos. Abusados acumulan fatiga.")

                ja = joker_analysis(df_531)
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Joker Sets", ja["total_joker_sets"])
                c2.metric("Sesiones con Jokers", f"{ja['sessions_with_jokers']}/{ja['total_sessions']}")
                c3.metric("Frecuencia", f"{ja['frequency_pct']}%")

                st.markdown(f"**Valoración:** {ja['assessment']}")

                if ja["per_lift"]:
                    st.divider()
                    for lift, data in ja["per_lift"].items():
                        with st.expander(f"{lift_names.get(lift, lift)} — {data['count']} joker sets"):
                            jc1, jc2, jc3 = st.columns(3)
                            jc1.metric("Mejor peso", f"{data['best_weight']:.0f} kg")
                            jc2.metric("Mejor e1RM", f"{data['best_e1rm']:.0f} kg")
                            if data['avg_pct_of_tm']:
                                jc3.metric("Media %TM", f"{data['avg_pct_of_tm']:.0f}%")

            # ── Tab 4: BBB Fatigue ──
            with tab_bbb:
                st.markdown("### Fatiga en BBB 5×10")
                st.caption("¿Pierdes reps en las últimas series del 5×10? "
                           "Si el dropoff es alto, el % BBB puede ser excesivo.")

                bf = bbb_fatigue_trend(df_531)
                if bf.empty:
                    st.info("Sin datos BBB registrados.")
                else:
                    # Summary metrics
                    avg_dropoff = bf["rep_dropoff"].mean()
                    pct_perfect = (bf["all_tens"].sum() / len(bf) * 100)
                    bc1, bc2, bc3 = st.columns(3)
                    bc1.metric("Drop-off medio", f"{avg_dropoff:+.1f} reps")
                    bc2.metric("Sesiones 5×10 completas", f"{pct_perfect:.0f}%")
                    bc3.metric("Sesiones BBB", len(bf))

                    # Per-lift detail
                    for lift in bf["lift"].unique():
                        lf = bf[bf["lift"] == lift].sort_values("date")
                        st.markdown(f"#### {lift_names.get(lift, lift)}")

                        display = lf[["date", "weight_kg", "reps_list", "avg_reps",
                                      "rep_dropoff", "pct_of_tm", "fatigue_status"]].copy()
                        display.columns = ["Fecha", "Peso", "Reps", "Media", "Dropoff",
                                          "%TM", "Estado"]
                        display["Fecha"] = display["Fecha"].dt.strftime("%d/%m")
                        display["Reps"] = display["Reps"].apply(lambda x: ", ".join(str(r) for r in x))
                        st.dataframe(display, use_container_width=True, hide_index=True)

            # ── Tab 5: True 1RM Trend ──
            with tab_1rm:
                st.markdown("### 1RM Real Estimado")
                st.caption("Tu 1RM real estimado desde AMRAPs — NO es tu Training Max. "
                           "El TM debería ser ~85-90% de este valor.")

                t1rm = true_1rm_trend(df_531)
                if t1rm.empty:
                    st.info("Sin AMRAPs para estimar.")
                else:
                    import plotly.graph_objects as go

                    for lift in t1rm["lift"].unique():
                        lt = t1rm[t1rm["lift"] == lift].sort_values("date")
                        st.markdown(f"#### {lift_names.get(lift, lift)}")

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=lt["date"], y=lt["estimated_1rm"],
                            mode="lines+markers", name="e1RM estimado",
                            line=dict(color="#10b981", width=2),
                            marker=dict(size=8),
                        ))
                        fig.add_trace(go.Scatter(
                            x=lt["date"], y=lt["running_max"],
                            mode="lines", name="Máximo histórico",
                            line=dict(color="#f59e0b", dash="dot", width=1),
                        ))
                        if lt["effective_tm"].notna().any():
                            fig.add_trace(go.Scatter(
                                x=lt["date"], y=lt["effective_tm"],
                                mode="lines", name="Training Max",
                                line=dict(color="#ef4444", dash="dash", width=1),
                            ))
                        fig.update_layout(**PL, height=300, showlegend=True,
                                         legend=dict(orientation="h", y=-0.15))
                        st.plotly_chart(fig, use_container_width=True)

                        # Latest stats
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
        st.markdown("## ⭐ Quality Score")
        st.caption("Puntuación compuesta por sesión: AMRAP (40%) + BBB (30%) + Accesorios (15%) + Volumen (15%)")

        qdf = workout_quality_531(df_531)
        if qdf.empty:
            st.info("Sin datos suficientes para calcular quality score.")
        else:
            # Trend summary
            qt = quality_trend(qdf)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Media", f"{qt['avg']:.0f}/100")
            c2.metric("Mejor", f"{qt['best']}/100")
            c3.metric("Peor", f"{qt['worst']}/100")
            trend_emoji = {"improving": "📈", "declining": "📉", "stable": "➡️"}
            c4.metric("Tendencia", trend_emoji.get(qt["trend"], "➡️"))

            # Chart
            fig = px.bar(
                qdf, x="date", y="quality_score", color="grade",
                color_discrete_map={"S": "#f59e0b", "A": "#10b981", "B": "#3b82f6",
                                    "C": "#8b5cf6", "D": "#f97316", "F": "#ef4444"},
                hover_data=["lift", "amrap_score", "bbb_score", "acc_score", "vol_score"],
                labels={"quality_score": "Score", "date": "", "grade": "Nota"},
            )
            fig.update_layout(**PL, height=350, showlegend=True)
            fig.add_hline(y=qt["avg"], line_dash="dot", line_color="#94a3b8",
                         annotation_text=f"Media: {qt['avg']:.0f}")
            st.plotly_chart(fig, use_container_width=True)

            # Breakdown table
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
        st.markdown("## 📸 Workout Card")
        st.caption("Genera una tarjeta PNG compartible de cualquier sesión.")

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
        st.markdown("## 🔍 Ejercicios No Registrados")
        st.caption("Ejercicios en tus sesiones que no están en la config de 531. "
                   "Posibles sustituciones que necesitan mapear.")

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
