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
)
from src.config import DAY_CONFIG, MUSCLE_GROUP_COLORS, KEY_LIFTS, KEY_LIFT_IDS, PROGRAM_START

# ── Page Config ──────────────────────────────────────────────────────
st.set_page_config(page_title="BBD Analytics", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

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
    return df

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("# 🔥 BBD Analytics")
    st.caption(f"Backed by Deadlifts — desde {pd.Timestamp(PROGRAM_START).strftime('%d %b %Y')}")
    st.divider()
    if st.button("🔄 Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    page = st.radio("Sección", [
        "📊 Dashboard",
        "📈 Progresión",
        "🎯 Ratios BBD",
        "🔬 Fatiga Intra-sesión",
        "⚡ Densidad",
        "🏋️ Strength Standards",
        "💪 Sesiones",
        "🏆 PRs",
        "🎯 Adherencia",
    ], label_visibility="collapsed")

try:
    df = load_data()
except Exception as e:
    st.error(f"Error cargando datos: {e}")
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

    dl_1rm = estimate_dl_1rm(df)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sesiones", summary["total_sessions"])
    c2.metric("Volumen Total", f"{summary['total_volume']:,} kg")
    c3.metric("Series", summary["total_sets"])
    c4.metric("Duración Media", f"{summary['avg_duration']} min")
    c5.metric("Semana", summary["current_week"])
    c6.metric("DL 1RM est.", f"{dl_1rm:.0f} kg")

    st.divider()
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### Volumen Semanal")
        wk = weekly_breakdown(df)
        if not wk.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=wk["week"].apply(lambda w: f"Sem {w}"), y=wk["total_volume"],
                marker_color="#ef4444", text=wk["total_volume"].apply(lambda v: f"{v:,.0f}"),
                textposition="outside",
            ))
            fig.update_layout(**PL, yaxis_title="Volumen (kg)", showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.markdown("### Volumen por Músculo")
        mv = muscle_volume(df)
        if not mv.empty:
            fig = px.pie(mv, values="total_volume", names="muscle_group",
                         color="muscle_group",
                         color_discrete_map={r["muscle_group"]: r["color"] for _, r in mv.iterrows()},
                         hole=0.45)
            fig.update_layout(**PL, height=350, showlegend=True)
            fig.update_traces(textposition="inside", textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True)

    # Density sparkline
    st.markdown("### ⚡ Densidad por Sesión (kg/min)")
    dens = session_density(df)
    if not dens.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dens["date"].dt.strftime("%d %b"), y=dens["density_kg_min"],
            mode="lines+markers+text", text=dens["density_kg_min"],
            textposition="top center", line=dict(color="#fbbf24", width=3),
            marker=dict(size=10),
        ))
        fig.update_layout(**PL, height=250, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Targets
    st.markdown("### 🎯 vs Objetivos Semanales")
    targets = vs_targets(df)
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
                st.plotly_chart(fig, use_container_width=True)
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
        st.plotly_chart(fig, use_container_width=True)

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
              help="Estimado del mejor e1RM en peso muerto, o inferido de Shrugs")

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
                    st.plotly_chart(fig, use_container_width=True)
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
    st.plotly_chart(fig, use_container_width=True)

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
            st.plotly_chart(fig, use_container_width=True)

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
        st.plotly_chart(fig, use_container_width=True)


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
    st.plotly_chart(fig, use_container_width=True)

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
    st.plotly_chart(fig, use_container_width=True)


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
        st.plotly_chart(fig, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    f"{summary.get('total_sessions', 0)} sesiones · "
    f"{summary.get('total_volume', 0):,} kg · "
    f"Sem {summary.get('current_week', '?')}"
)
