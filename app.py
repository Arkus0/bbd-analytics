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

from src.hevy_client import fetch_bbd_workouts, workouts_to_dataframe
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
from src.config import DAY_CONFIG, MUSCLE_GROUP_COLORS, KEY_LIFTS, KEY_LIFT_IDS, PROGRAM_START, NOTION_TOKEN, NOTION_HALL_OF_TITANS_DB
import requests as _requests
import re as _re

# ── Page Config ──────────────────────────────────────────────────────
st.set_page_config(page_title="BBD Analytics", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

@st.cache_data(ttl=300)
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


@st.cache_data(ttl=300)
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
</style>
""", unsafe_allow_html=True)

PL = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Space Grotesk", color="#e2e8f0"), margin=dict(l=40, r=20, t=40, b=40),
)

BODYWEIGHT = 86.0  # kg — update from Seguimiento

# ── Data Loading ─────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    workouts = fetch_bbd_workouts()
    df = workouts_to_dataframe(workouts)
    df = add_derived_columns(df)
    return {"df": df, "ts": pd.Timestamp.now(tz="Europe/Madrid")}

try:
    result = load_data()
    if isinstance(result, dict):
        df, last_sync = result["df"], result["ts"]
    else:
        # Stale cache from previous version — force refresh
        st.cache_data.clear()
        result = load_data()
        df, last_sync = result["df"], result["ts"]
except Exception as e:
    st.error(f"Error cargando datos: {e}")
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🔥 BBD Analytics")
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

    # Cron health: check Notion analytics page last edit
    notion_edit = _notion_last_edit()
    if notion_edit is not None:
        hours_since = (now - notion_edit.tz_convert("Europe/Madrid")).total_seconds() / 3600
        if hours_since > 24:
            st.error(f"⚠️ Notion sync hace {int(hours_since)}h — revisa GitHub Actions")
        else:
            st.caption(f"✅ Notion sync: hace {int(hours_since)}h")

    st.divider()
    page = st.radio("Sección", [
        "📊 Dashboard",
        "📈 Progresión",
        "🎯 Ratios BBD",
        "🔬 Fatiga Intra-sesión",
        "⚡ Densidad",
        "🏋️ Strength Standards",
        "🧠 Inteligencia",
        "🎮 Niveles",
        "🏛️ Hall of Titans",
        "💪 Sesiones",
        "🏆 PRs",
        "🎯 Adherencia",
    ], label_visibility="collapsed")

if df.empty:
    st.warning("No hay entrenamientos BBD registrados.")
    st.stop()

summary = global_summary(df)


# ══════════════════════════════════════════════════════════════════════
# 📊 DASHBOARD
# ══════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.markdown("## 📊 Dashboard General")

    # ── Week selector ──
    all_weeks = sorted(df["week"].unique().tolist())
    current_week = summary["current_week"]

    if len(all_weeks) >= 2:
        sel_week = st.select_slider(
            "📅 Semana", options=all_weeks, value=current_week,
            format_func=lambda w: f"Sem {w}" + (" (actual)" if w == current_week else ""),
        )
    else:
        sel_week = all_weeks[0] if all_weeks else 1
        st.caption(f"📅 Semana {sel_week}")

    wk_df = df[df["week"] == sel_week]
    wk_summary = {
        "sessions": int(wk_df["hevy_id"].nunique()),
        "volume": int(wk_df["volume_kg"].sum()),
        "sets": int(wk_df["n_sets"].sum()),
        "avg_dur": int(wk_df.groupby("hevy_id")["duration_min"].first().mean()) if not wk_df.empty else 0,
    }

    dl_1rm = estimate_dl_1rm(df)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sesiones", wk_summary["sessions"])
    c2.metric("Volumen", f"{wk_summary['volume']:,} kg")
    c3.metric("Series", wk_summary["sets"])
    c4.metric("Duración Media", f"{wk_summary['avg_dur']} min")
    c5.metric("Semana", f"{sel_week} / {current_week}")
    c6.metric("DL 1RM est.", f"{dl_1rm:.0f} kg")

    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### Volumen Semanal")
        wk = weekly_breakdown(df)
        if not wk.empty:
            colors = ["#ef4444" if w == sel_week else "#7f1d1d" for w in wk["week"]]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=wk["week"].apply(lambda w: f"Sem {w}"), y=wk["total_volume"],
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
    st.markdown(f"### 🎯 vs Objetivos Semanales — Sem {sel_week}")
    targets = vs_targets(df, week=sel_week)
    tc1, tc2, tc3 = st.columns(3)
    for col, t in zip([tc1, tc2, tc3], targets):
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
              help="Peso en barra del PMR ÷ 0.60, o inferido de Shrugs")

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

# ── Footer ───────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    f"{summary.get('total_sessions', 0)} sesiones · "
    f"{summary.get('total_volume', 0):,} kg · "
    f"Sem {summary.get('current_week', '?')}"
)
