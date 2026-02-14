"""
BBD Notion Analytics Page Updater
Generates all analytics and replaces the content of the BBD Analytics page.
Uses Notion REST API (blocks endpoint).
"""
import time
import requests
import os
import pandas as pd
from datetime import datetime

# Notion API rate limit: 3 req/s
RATE_LIMIT_DELAY = 0.35

from src.config import NOTION_BBD_LOGBOOK_DB, DAY_CONFIG, PROGRAM_START
from src.analytics import (
    add_derived_columns, global_summary, weekly_breakdown,
    pr_table, muscle_volume, session_summary, session_detail,
    recovery_indicators, day_adherence, vs_targets,
    bbd_ratios, estimate_dl_1rm, dominadas_progress,
    intra_session_fatigue, session_density, strength_standards,
    key_lifts_progression, calc_week,
    # Phase 1
    plateau_detection, acwr, mesocycle_summary, strength_profile,
)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
ANALYTICS_PAGE_ID = os.environ.get(
    "NOTION_ANALYTICS_PAGE", "306cbc499cfe81b08aedce82d40289f6"
)
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ─── Notion Block Helpers ────────────────────────────────────────────

def _rt(text: str, bold=False, code=False, color="default") -> dict:
    """Rich text object."""
    obj = {"type": "text", "text": {"content": text}}
    ann = {}
    if bold:
        ann["bold"] = True
    if code:
        ann["code"] = True
    if color != "default":
        ann["color"] = color
    if ann:
        obj["annotations"] = ann
    return obj


def heading1(text: str) -> dict:
    return {"type": "heading_1", "heading_1": {"rich_text": [_rt(text)]}}


def heading2(text: str) -> dict:
    return {"type": "heading_2", "heading_2": {"rich_text": [_rt(text)]}}


def heading3(text: str) -> dict:
    return {"type": "heading_3", "heading_3": {"rich_text": [_rt(text)]}}


def paragraph(*parts) -> dict:
    """parts: list of (text, bold, code) or just strings."""
    rich = []
    for p in parts:
        if isinstance(p, str):
            rich.append(_rt(p))
        elif isinstance(p, tuple):
            rich.append(_rt(p[0], bold=p[1] if len(p) > 1 else False,
                            code=p[2] if len(p) > 2 else False))
    return {"type": "paragraph", "paragraph": {"rich_text": rich}}


def callout(text_parts, icon="📊") -> dict:
    rich = []
    for p in text_parts:
        if isinstance(p, str):
            rich.append(_rt(p))
        elif isinstance(p, tuple):
            rich.append(_rt(p[0], bold=p[1] if len(p) > 1 else False))
    return {
        "type": "callout",
        "callout": {
            "rich_text": rich,
            "icon": {"type": "emoji", "emoji": icon},
        },
    }


def divider() -> dict:
    return {"type": "divider", "divider": {}}


def table(headers: list[str], rows: list[list[str]]) -> dict:
    """Create a table block with header row + data rows."""
    width = len(headers)
    children = []
    # Header row
    children.append({
        "type": "table_row",
        "table_row": {
            "cells": [[_rt(h, bold=True)] for h in headers]
        },
    })
    # Data rows
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            cells.append([_rt(str(cell))])
        # Pad if needed
        while len(cells) < width:
            cells.append([_rt("")])
        children.append({
            "type": "table_row",
            "table_row": {"cells": cells[:width]},
        })
    return {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "children": children,
        },
    }


def quote(text: str) -> dict:
    return {"type": "quote", "quote": {"rich_text": [_rt(text)]}}


# ─── Notion API Calls ────────────────────────────────────────────────

def _get_child_blocks(page_id: str) -> list[str]:
    """Get all child block IDs of a page."""
    block_ids = []
    url = f"{BASE}/blocks/{page_id}/children?page_size=100"
    while url:
        time.sleep(RATE_LIMIT_DELAY)
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        data = r.json()
        for block in data.get("results", []):
            block_ids.append(block["id"])
        if data.get("has_more"):
            url = f"{BASE}/blocks/{page_id}/children?page_size=100&start_cursor={data['next_cursor']}"
        else:
            url = None
    return block_ids


def _delete_block(block_id: str):
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.delete(f"{BASE}/blocks/{block_id}", headers=HEADERS)
    # Ignore 404s (already deleted)
    if r.status_code not in (200, 404):
        r.raise_for_status()


def _append_blocks(page_id: str, blocks: list[dict]):
    """Append blocks to a page. Batches in groups of 100."""
    for i in range(0, len(blocks), 100):
        batch = blocks[i : i + 100]
        time.sleep(RATE_LIMIT_DELAY)
        r = requests.patch(
            f"{BASE}/blocks/{page_id}/children",
            headers=HEADERS,
            json={"children": batch},
        )
        if r.status_code != 200:
            print(f"   ⚠️ Block append error: {r.status_code} — {r.text[:200]}")
            r.raise_for_status()


# ─── Build Analytics Page ────────────────────────────────────────────

def build_analytics_blocks(df: pd.DataFrame) -> list[dict]:
    """Build all Notion blocks for the analytics page."""
    blocks = []
    now = datetime.now()
    current_week = calc_week(pd.Timestamp(now.date()))
    summary = global_summary(df)

    # ── Header ──
    blocks.append(paragraph(
        "Estadísticas y análisis del programa ",
        ("Backed by Deadlifts", True),
        ". Esta página se actualiza automáticamente con cada sync."
    ))
    blocks.append(callout([
        ("📅 Última actualización: ", False),
        (now.strftime("%d %b %Y %H:%M"), True),
        (" | Semana actual: ", False),
        (str(current_week), True),
        (" | Inicio programa: ", False),
        (pd.Timestamp(PROGRAM_START).strftime("%d %b %Y"), True),
    ], "📅"))
    blocks.append(divider())

    # ── 1. Resumen Global ──
    blocks.append(heading1("🎯 Resumen Global"))
    dl_1rm = estimate_dl_1rm(df)
    blocks.append(table(
        ["Métrica", "Valor"],
        [
            ["Sesiones completadas", str(summary["total_sessions"])],
            ["Series totales", str(summary["total_sets"])],
            ["Volumen total", f"{summary['total_volume']:,} kg"],
            ["Reps totales", f"{summary['total_reps']:,}"],
            ["Duración media", f"{summary['avg_duration']} min"],
            ["Días entrenados / semana", f"{len(summary['days_completed'])} / 5-6"],
            ["Volumen medio / sesión", f"{summary['avg_volume_session']:,} kg"],
            ["Series media / sesión", str(summary["avg_sets_session"])],
            ["DL 1RM estimado", f"{dl_1rm:.0f} kg"],
            ["Ejercicios únicos", str(summary["total_exercises_unique"])],
        ],
    ))
    blocks.append(divider())

    # ── 2. Progreso Semanal ──
    blocks.append(heading1("📈 Progreso Semanal"))
    wk = weekly_breakdown(df)
    if not wk.empty:
        rows = []
        for _, w in wk.iterrows():
            delta = f"{w['vol_delta_pct']:+.1f}%" if pd.notna(w["vol_delta_pct"]) else "—"
            days_str = ", ".join(w["days"]) if isinstance(w["days"], list) else str(w["days"])
            density = f"{w['density_kg_min']:.0f}" if pd.notna(w.get("density_kg_min")) else "—"
            rows.append([
                str(int(w["week"])),
                f"{w['date_start'].strftime('%d')}-{w['date_end'].strftime('%d %b')}",
                str(int(w["sessions"])),
                days_str,
                str(int(w["total_sets"])),
                f"{w['total_volume']:,.0f}",
                f"{w['vol_per_session']:,.0f}",
                density,
                delta,
                f"{w['adherence_pct']:.0f}%",
            ])
        blocks.append(table(
            ["Sem", "Fechas", "Ses", "Días", "Series", "Vol (kg)", "Vol/Ses", "kg/min", "Δ Vol", "Adh"],
            rows,
        ))
    blocks.append(divider())

    # ── 3. PRs ──
    blocks.append(heading1("🏆 PRs Actuales por Ejercicio"))
    prs = pr_table(df)
    if not prs.empty:
        rows = []
        for i, (_, p) in enumerate(prs.iterrows(), 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)
            weight_str = f"{p['max_weight']:.0f} kg" if p["max_weight"] > 0 else "BW"
            e1rm_str = f"{p['e1rm']:.1f}" if p["e1rm"] > 0 else "—"
            bw_ratio = f"{p['e1rm']/86:.2f}×" if p["e1rm"] > 0 else "—"
            rows.append([
                medal, p["exercise"], weight_str,
                str(int(p["max_reps_at_max"])), e1rm_str, bw_ratio,
                p["date"].strftime("%d %b"), "🆕",
            ])
        blocks.append(table(
            ["#", "Ejercicio", "Peso", "Reps", "e1RM", "×BW", "Fecha", "Trend"],
            rows,
        ))
    blocks.append(paragraph("🆕 = primer registro | ⬆️ = nuevo PR | ➡️ = sin cambio | ⬇️ = regresión"))
    blocks.append(divider())

    # ── 4. Volumen por Músculo ──
    blocks.append(heading1("💪 Volumen por Grupo Muscular"))
    mv = muscle_volume(df)
    if not mv.empty:
        rows = []
        for _, m in mv.iterrows():
            rows.append([
                m["muscle_group"],
                f"{m['total_volume']:,.0f}",
                f"{m['pct_volume']:.1f}%",
                str(int(m["total_sets"])),
                str(int(m["sessions"])),
            ])
        blocks.append(table(
            ["Grupo Muscular", "Volumen (kg)", "% Total", "Series", "Sesiones"],
            rows,
        ))
    blocks.append(divider())

    # ── 5. Historial de Sesiones ──
    blocks.append(heading1("📋 Historial de Sesiones"))
    sessions = session_summary(df)
    current_wk_num = 0
    for _, s in sessions.sort_values("date").iterrows():
        wk_num = calc_week(s["date"])
        if wk_num != current_wk_num:
            blocks.append(heading2(f"Semana {wk_num}"))
            current_wk_num = wk_num

        dens = s["total_volume"] / s["duration_min"] if s["duration_min"] > 0 else 0
        blocks.append(heading3(
            f"📅 {s['date'].strftime('%d %b')} — {s['day_name']}"
        ))

        detail = session_detail(df, s["hevy_id"])
        rows = []
        for _, d in detail.iterrows():
            weight_str = f"{d['max_weight']:.0f} kg" if d["max_weight"] > 0 else "BW"
            vol_str = f"{d['volume_kg']:,.0f}" if d["volume_kg"] > 0 else "—"
            e1rm_str = f"{d['e1rm']:.1f}" if d["e1rm"] > 0 else "—"
            rows.append([
                d["exercise"], str(int(d["n_sets"])),
                d.get("reps_str", ""), weight_str, vol_str,
                d.get("top_set", ""), e1rm_str,
            ])
        # Total row
        rows.append([
            "TOTAL", str(int(s["total_sets"])), "",
            "", f"{s['total_volume']:,.0f}", "", "",
        ])
        blocks.append(table(
            ["Ejercicio", "Series", "Reps", "Peso", "Volumen", "Top Set", "e1RM"],
            rows,
        ))

        desc = s["description"] if pd.notna(s["description"]) and s["description"] else ""
        blocks.append(quote(
            f"⏱️ Duración: {s['duration_min']:.0f} min | ⚡ {dens:.0f} kg/min"
            + (f' | 📝 "{desc}"' if desc else "")
        ))

    blocks.append(divider())

    # ── 6. Ejercicios Clave ──
    blocks.append(heading1("🔑 Ejercicios Clave — Progresión e1RM"))
    progressions = key_lifts_progression(df)
    for lift, ldf in progressions.items():
        blocks.append(heading2(lift))
        rows = []
        prev_e1rm = None
        for _, r in ldf.iterrows():
            delta = "—"
            if prev_e1rm is not None:
                d = r["e1rm"] - prev_e1rm
                delta = f"{d:+.1f}" if d != 0 else "→"
            prev_e1rm = r["e1rm"]
            rows.append([
                str(int(r["week"])), r["date"].strftime("%d %b"),
                f"{r['max_weight']:.0f} kg", str(int(r["max_reps_at_max"])),
                f"{r['e1rm']:.1f}", delta,
            ])
        blocks.append(table(["Sem", "Fecha", "Peso", "Reps", "e1RM", "Δ"], rows))

    blocks.append(divider())

    # ── 7. Ratios BBD ──
    blocks.append(heading1("🎯 Ratios BBD — Intensidad Relativa"))
    blocks.append(paragraph(
        f"DL 1RM estimado: ", (f"{dl_1rm:.0f} kg", True),
        " (inferido de los mejores e1RM en deadlift o shrugs)"
    ))

    ratios = bbd_ratios(df)
    if not ratios.empty:
        rows = []
        for _, r in ratios.iterrows():
            w_str = f"{r['current_weight']:.0f} kg" if r["current_weight"] > 0 else "—"
            pct_str = f"{r['pct_of_dl']:.0f}%" if r["pct_of_dl"] > 0 else "—"
            rows.append([
                r["label"], w_str, pct_str,
                f"{r['target_low']}-{r['target_high']}%", r["status"],
            ])
        blocks.append(table(
            ["Ejercicio", "Peso", "% DL", "Rango BBD", "Estado"],
            rows,
        ))

    dom = dominadas_progress(df)
    blocks.append(heading3("🏊 Dominadas — Objetivo 75 reps/sesión"))
    if dom["best"] > 0:
        blocks.append(paragraph(
            f"Mejor sesión: ", (f"{dom['best']} reps", True),
            f" | Última: {dom['last']} | Faltan: {dom['target'] - dom['best']} reps"
            f" | Progreso: {dom['pct']:.0f}%"
        ))
    else:
        blocks.append(paragraph("Aún no hay sesiones con dominadas registradas."))

    blocks.append(divider())

    # ── 8. Fatiga Intra-sesión ──
    blocks.append(heading1("🔬 Fatiga Intra-sesión"))
    fatigue = intra_session_fatigue(df)
    if not fatigue.empty:
        avg_fat = fatigue["fatigue_pct"].mean()
        stable = (fatigue["pattern"].str.contains("Estable")).sum()
        blocks.append(paragraph(
            f"Fatiga media: ", (f"{avg_fat:.1f}%", True),
            f" | Ejercicios estables: {stable}/{len(fatigue)}"
        ))
        rows = []
        for _, f_ in fatigue.iterrows():
            reps_str = ",".join(str(r) for r in f_["reps_list"])
            rows.append([
                f_["exercise"], str(f_["n_sets"]), reps_str,
                f"{f_['weight']:.0f} kg", f"{f_['fatigue_pct']:.1f}%",
                f"{f_['cv_reps']:.1f}%", f_["pattern"],
            ])
        blocks.append(table(
            ["Ejercicio", "Sets", "Reps", "Peso", "Dropoff", "CV", "Patrón"],
            rows,
        ))
    blocks.append(paragraph("Umbrales: 🟢 ≤10% estable | 🟡 10-25% moderada | 🔴 >25% alta"))
    blocks.append(divider())

    # ── 9. Densidad ──
    blocks.append(heading1("⚡ Densidad de Entrenamiento"))
    dens_df = session_density(df)
    if not dens_df.empty:
        rows = []
        for _, d in dens_df.iterrows():
            rows.append([
                f"{d['date'].strftime('%d %b')} — {d['day_name']}",
                f"{d['duration_min']:.0f} min",
                f"{d['total_volume']:,.0f} kg",
                f"{d['density_kg_min']:.0f} kg/min",
                f"{d['sets_per_min']:.2f}",
            ])
        blocks.append(table(
            ["Sesión", "Duración", "Volumen", "Densidad", "Sets/min"],
            rows,
        ))
    blocks.append(divider())

    # ── 10. Strength Standards ──
    blocks.append(heading1("🏋️ Strength Standards — DOTS"))
    blocks.append(paragraph(
        "Nivel de fuerza ajustado por peso corporal (86 kg). "
        "DOTS = estándar IPF para comparar fuerza relativa."
    ))
    ss = strength_standards(df, 86.0)
    if not ss.empty:
        rows = []
        for _, s in ss.iterrows():
            next_str = f"{s['next_threshold']} (+{s['kg_to_next']:.0f}kg)" if s["kg_to_next"] > 0 else "—"
            rows.append([
                s["exercise"][:30], f"{s['best_e1rm']:.1f} kg",
                f"{s['bw_ratio']:.2f}×", f"{s['dots_score']:.0f}",
                s["level"], f"~P{s['percentile']}", next_str,
            ])
        blocks.append(table(
            ["Ejercicio", "e1RM", "×BW", "DOTS", "Nivel", "Pctil", "Siguiente"],
            rows,
        ))
    blocks.append(paragraph("Escala: 🌱 Principiante | 📊 Intermedio | 💪 Avanzado | 🏆 Elite"))
    blocks.append(divider())

    # ── 11. Recovery ──
    blocks.append(heading1("📊 Indicadores de Recuperación"))
    rec = recovery_indicators(df)
    if not rec.empty:
        rows = []
        for _, r in rec.iterrows():
            delta = f"{r['vol_delta_pct']:+.1f}%" if pd.notna(r["vol_delta_pct"]) else "—"
            fat = f"{r['avg_fatigue']:.1f}%" if pd.notna(r.get("avg_fatigue")) else "—"
            rows.append([
                str(int(r["week"])), f"{r['total_volume']:,.0f} kg", delta,
                str(int(r["sessions"])), fat,
                f"{r['adherence_pct']:.0f}%", r["alert"],
            ])
        blocks.append(table(
            ["Sem", "Volumen", "Δ Vol", "Sesiones", "Fatiga", "Adherencia", "Estado"],
            rows,
        ))
    blocks.append(paragraph(
        "🟢 OK | 🟡 Monitorizar (1 señal) | 🔴 Deload (2+ señales: "
        "vol cayendo + fatiga alta + fatiga subiendo + baja adherencia)"
    ))
    blocks.append(divider())

    # ── 12. Adherencia ──
    blocks.append(heading1("🔄 Adherencia al Programa"))
    adh = day_adherence(df)
    rows = []
    for _, a in adh.iterrows():
        last = a["last_date"].strftime("%d %b") if pd.notna(a["last_date"]) else "—"
        rows.append([
            f"{a['day_name']} — {a['focus']}",
            a["status"], str(a["times_completed"]), last,
        ])
    blocks.append(table(["Día BBD", "Estado", "Veces", "Última"], rows))
    completed = adh["times_completed"].gt(0).sum()
    blocks.append(paragraph(f"Cobertura actual: {completed}/6 días completados al menos una vez"))
    blocks.append(divider())

    # ── 13. Comparativa vs Objetivos ──
    blocks.append(heading1("📐 Comparativa BBD vs Objetivos"))
    targets = vs_targets(df)
    ratios_data = bbd_ratios(df)

    target_rows = []
    for t in targets:
        pct = t["pct"]
        status = "✅" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
        target_rows.append([t["metric"], str(t["target"]), str(t["actual"]), status])

    # Add BBD-specific targets
    if not ratios_data.empty:
        for _, r in ratios_data.iterrows():
            if r["current_weight"] > 0:
                target_rows.append([
                    f"{r['label']} (% DL)", f"{r['target_low']}-{r['target_high']}%",
                    f"{r['pct_of_dl']:.0f}%", r["status"].split(" ")[0],
                ])
    if dom["best"] > 0:
        dom_status = "✅" if dom["pct"] >= 100 else "🔴" if dom["pct"] < 50 else "🟡"
        target_rows.append(["Dominadas/sesión", "75 reps", str(dom["best"]), dom_status])

    dens_avg = dens_df["density_kg_min"].mean() if not dens_df.empty else 0
    dens_status = "✅" if dens_avg >= 150 else "🟡"
    target_rows.append(["Densidad media", ">150 kg/min", f"{dens_avg:.0f} kg/min", dens_status])

    blocks.append(table(["Métrica", "Objetivo", "Actual", "Estado"], target_rows))
    blocks.append(paragraph(
        f"DL e1RM estimado: ~{dl_1rm:.0f} kg. "
        "Se actualizará cuando registres Peso Muerto directo."
    ))

    blocks.append(divider())

    # ── 14. Plateau Detection — Phase 1 ──
    blocks.append(heading1("🔴 Detección de Estancamiento"))
    plateaus = plateau_detection(df)
    if not plateaus.empty:
        stuck = (plateaus["status"].str.contains("Estancado")).sum()
        watch = (plateaus["status"].str.contains("Vigilar")).sum()
        blocks.append(paragraph(
            f"Resumen: ",
            (f"{stuck} estancados", True),
            f" · {watch} a vigilar · ",
            (f"{len(plateaus) - stuck - watch} progresando", True),
        ))
        rows = []
        for _, p in plateaus.iterrows():
            rows.append([
                p["exercise"][:30], f"{p['pr_e1rm']:.1f}", f"{p['last_e1rm']:.1f}",
                f"{p['pct_of_pr']:.0f}%", str(p["weeks_since_pr"]),
                f"{p['trend_slope']:+.2f}", p["status"],
            ])
        blocks.append(table(
            ["Ejercicio", "PR e1RM", "Último e1RM", "% PR", "Sem sin PR", "Tendencia", "Estado"],
            rows,
        ))
        stale = plateaus[plateaus["status"].str.contains("Estancado")]
        if not stale.empty:
            blocks.append(callout([
                "⚠️ Estancados: ",
                (", ".join(f"{r['exercise']} ({r['weeks_since_pr']} sem)" for _, r in stale.iterrows()), True),
                " — Considera variar reps/series, deload, o cambiar variante.",
            ], "⚠️"))
    else:
        blocks.append(paragraph("Se necesitan ≥2 semanas de datos por ejercicio para detectar estancamientos."))
    blocks.append(divider())

    # ── 15. ACWR — Phase 1 ──
    blocks.append(heading1("⚖️ ACWR — Carga Aguda/Crónica"))
    acwr_df = acwr(df)
    if not acwr_df.empty and not acwr_df["acwr"].isna().all():
        valid = acwr_df.dropna(subset=["acwr"])
        if not valid.empty:
            latest = valid.iloc[-1]
            blocks.append(callout([
                f"Semana {int(latest['week'])}: ACWR = ",
                (f"{latest['acwr']:.2f}", True),
                f" → {latest['acwr_zone']}",
            ], "⚖️"))
            rows = []
            for _, a in valid.iterrows():
                chronic_str = f"{a['chronic_volume']:,.0f}" if pd.notna(a["chronic_volume"]) else "—"
                rows.append([
                    str(int(a["week"])), f"{a['acute_volume']:,.0f}", chronic_str,
                    f"{a['acwr']:.2f}", a["acwr_zone"], str(int(a["sessions"])),
                ])
            blocks.append(table(
                ["Sem", "Vol. Agudo", "Vol. Crónico", "ACWR", "Zona", "Sesiones"],
                rows,
            ))
    else:
        blocks.append(paragraph("Se necesitan al menos 2 semanas para calcular ACWR."))
    blocks.append(paragraph("Zonas: 🔵 <0.8 detraining | 🟢 0.8-1.3 segura | 🟡 1.3-1.5 overreaching | 🔴 >1.5 riesgo"))
    blocks.append(divider())

    # ── 16. Mesocycles — Phase 1 ──
    blocks.append(heading1("📦 Mesociclos — Bloques de 4 Semanas"))
    meso = mesocycle_summary(df)
    if not meso.empty:
        rows = []
        for _, m in meso.iterrows():
            vol_delta = f"{m['vol_delta_pct']:+.1f}%" if pd.notna(m["vol_delta_pct"]) else "—"
            fat_str = f"{m['avg_fatigue']:.1f}%" if pd.notna(m["avg_fatigue"]) else "—"
            dens_str = f"{m['avg_density']:.0f}" if pd.notna(m["avg_density"]) else "—"
            rows.append([
                f"Meso {int(m['mesocycle'])}",
                f"Sem {int(m['week_start'])}–{int(m['week_end'])}",
                str(int(m["total_sessions"])),
                f"{m['avg_weekly_volume']:,.0f} kg",
                vol_delta, f"{m['avg_e1rm']:.1f} kg",
                fat_str, dens_str,
            ])
        blocks.append(table(
            ["Mesociclo", "Semanas", "Sesiones", "Vol/sem", "Δ Vol", "e1RM med.", "Fatiga", "Densidad"],
            rows,
        ))
    else:
        blocks.append(paragraph("Datos insuficientes para análisis de mesociclos."))
    blocks.append(divider())

    # ── 17. Strength Profile — Phase 1 ──
    blocks.append(heading1("🕐 Perfil de Fuerza Actual"))
    profile = strength_profile(df)
    if profile:
        rows = []
        for axis, score in profile.items():
            bar = "█" * (score // 10) + "░" * (10 - score // 10)
            rows.append([axis, f"{score}/100", bar])
        blocks.append(table(["Eje", "Puntuación", ""], rows))
        blocks.append(paragraph(
            "Ejes: Empuje Vertical · Empuje Horizontal · Tracción · Piernas · Core & Grip. "
            "Score normalizado vs techo teórico (0-100)."
        ))
    else:
        blocks.append(paragraph("Sin datos suficientes para el perfil de fuerza."))

    return blocks


# ─── Main Update Function ────────────────────────────────────────────

def update_analytics_page(df: pd.DataFrame):
    """Delete all content from analytics page and recreate with fresh data."""
    print("📊 Updating Analytics page...")
    df = add_derived_columns(df)

    # 1. Build new blocks
    blocks = build_analytics_blocks(df)
    print(f"   Built {len(blocks)} blocks")

    # 2. Delete existing content
    existing = _get_child_blocks(ANALYTICS_PAGE_ID)
    print(f"   Deleting {len(existing)} existing blocks...")
    for bid in existing:
        _delete_block(bid)

    # 3. Append new content
    print(f"   Appending {len(blocks)} new blocks...")
    _append_blocks(ANALYTICS_PAGE_ID, blocks)
    print("   ✅ Analytics page updated!")
