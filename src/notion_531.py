"""
531 BBB Notion Sync — Logbook + Analytics Page Updater

Syncs BBB workout data to:
1. Notion Logbook DB (one row per exercise per workout)
2. Notion Analytics Page (full replace with current stats)
"""
import time
import os
import requests
import pandas as pd
from datetime import datetime

from src.config_531 import (
    NOTION_531_LOGBOOK_DB,
    NOTION_531_ANALYTICS_PAGE,
    TRAINING_MAX,
    CYCLE_WEEKS,
    STRENGTH_STANDARDS_531,
    BODYWEIGHT,
    DAY_CONFIG_531,
)
from src.analytics_531 import (
    global_summary_531,
    amrap_tracking,
    bbb_compliance,
    accessory_summary,
    session_summary_531,
    pr_table_531,
    lift_progression,
    strength_level_531,
    weekly_volume_531,
    muscle_volume_531,
)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
RATE_LIMIT_DELAY = 0.35

LIFT_LABELS = {"ohp": "OHP", "deadlift": "Deadlift", "bench": "Bench", "squat": "Squat"}


# ─── Low-level Notion API ────────────────────────────────────────────

def _post(endpoint: str, body: dict) -> dict:
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.post(f"{BASE}{endpoint}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def _patch(endpoint: str, body: dict) -> dict:
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.patch(f"{BASE}{endpoint}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def _get(endpoint: str) -> dict:
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.get(f"{BASE}{endpoint}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def _delete_children(page_id: str):
    """Delete all child blocks of a page."""
    children = _get(f"/blocks/{page_id}/children?page_size=100")
    for block in children.get("results", []):
        time.sleep(RATE_LIMIT_DELAY)
        requests.delete(f"{BASE}/blocks/{block['id']}", headers=HEADERS)


def _append_blocks(page_id: str, blocks: list[dict]):
    """Append blocks to a page, respecting 100-block limit."""
    for i in range(0, len(blocks), 100):
        chunk = blocks[i : i + 100]
        _patch(f"/blocks/{page_id}/children", {"children": chunk})


# ─── Notion Block Helpers ────────────────────────────────────────────

def _rt(text: str, bold=False, code=False, color="default") -> dict:
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


def _heading2(text: str, emoji: str = "") -> dict:
    content = f"{emoji} {text}" if emoji else text
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [_rt(content)]},
    }


def _heading3(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [_rt(text)]},
    }


def _paragraph(parts: list[dict]) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": parts},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _table_row(cells: list[str]) -> dict:
    return {
        "type": "table_row",
        "table_row": {
            "cells": [[_rt(c)] for c in cells],
        },
    }


def _table(headers: list[str], rows: list[list[str]]) -> dict:
    all_rows = [_table_row(headers)] + [_table_row(r) for r in rows]
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(headers),
            "has_column_header": True,
            "has_row_header": False,
            "children": all_rows,
        },
    }


# ═════════════════════════════════════════════════════════════════════
# LOGBOOK SYNC
# ═════════════════════════════════════════════════════════════════════

def get_synced_hevy_ids_531() -> set[str]:
    """Get all Hevy IDs already synced to 531 Notion logbook."""
    body = {"page_size": 100}
    all_results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = _post(f"/databases/{NOTION_531_LOGBOOK_DB}/query", body)
        all_results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    ids = set()
    for p in all_results:
        props = p.get("properties", {})
        hevy_prop = props.get("Hevy ID", {})
        rt = hevy_prop.get("rich_text", [])
        if rt:
            ids.add(rt[0].get("plain_text", ""))
    return ids


def create_531_logbook_entry(session_df: pd.DataFrame) -> int:
    """
    Create logbook entries for one workout session.
    Groups by exercise and creates one entry per exercise (not per set).
    """
    if session_df.empty:
        return 0

    count = 0
    hevy_id = session_df["hevy_id"].iloc[0]
    date = session_df["date"].iloc[0]

    for exercise, ex_df in session_df.groupby("exercise"):
        tid = ex_df["exercise_template_id"].iloc[0]
        lift = ex_df["lift"].iloc[0]
        set_type = ex_df["set_type"].iloc[0]

        # For main lifts, find the dominant set type
        if lift:
            # Separate AMRAP/working/BBB
            amrap_sets = ex_df[ex_df["set_type"] == "amrap"]
            bbb_sets = ex_df[ex_df["set_type"] == "bbb"]
            working_sets = ex_df[ex_df["set_type"].isin(["working_531", "amrap"])]

            # Create entry for 531 working sets (including AMRAP)
            if not working_sets.empty:
                w_sets = working_sets
                max_w = w_sets["weight_kg"].max()
                max_r = w_sets.loc[w_sets["weight_kg"] == max_w, "reps"].max()
                e1rm = w_sets["e1rm"].max()
                reps_str = ",".join(f"{int(r['weight_kg'])}×{int(r['reps'])}" for _, r in w_sets.iterrows())

                properties = {
                    "Ejercicio": {"title": [{"text": {"content": f"{exercise} (531)"}}]},
                    "Fecha": {"date": {"start": date.strftime("%Y-%m-%d")}},
                    "Tipo": {"select": {"name": "working_531"}},
                    "Series": {"number": len(w_sets)},
                    "Reps": {"rich_text": [{"text": {"content": reps_str}}]},
                    "Top Set": {"rich_text": [{"text": {"content": f"{max_w}kg × {max_r}"}}]},
                    "Peso (kg)": {"number": float(max_w)},
                    "Volumen (kg)": {"number": float(w_sets["volume_kg"].sum())},
                    "e1RM": {"number": float(e1rm)},
                    "Hevy ID": {"rich_text": [{"text": {"content": hevy_id}}]},
                }
                if lift:
                    properties["Lift"] = {"select": {"name": LIFT_LABELS.get(lift, lift)}}
                if not amrap_sets.empty:
                    properties["AMRAP Reps"] = {"number": int(amrap_sets["reps"].iloc[0])}
                    tm = TRAINING_MAX.get(lift)
                    if tm:
                        properties["% TM"] = {"number": round(max_w / tm, 3)}
                if ex_df.get("cycle_num") is not None and not ex_df["cycle_num"].isna().all():
                    properties["Ciclo"] = {"number": int(ex_df["cycle_num"].iloc[0])}
                if ex_df.get("week_in_cycle") is not None and not ex_df["week_in_cycle"].isna().all():
                    properties["Semana"] = {"number": int(ex_df["week_in_cycle"].iloc[0])}

                try:
                    _post("/pages", {"parent": {"database_id": NOTION_531_LOGBOOK_DB}, "properties": properties})
                    count += 1
                except Exception as e:
                    print(f"  ❌ Error syncing {exercise} (531): {e}")

            # Create entry for BBB sets
            if not bbb_sets.empty:
                bbb_w = bbb_sets["weight_kg"].iloc[0]
                bbb_reps = ",".join(str(int(r)) for r in bbb_sets["reps"])
                bbb_avg = round(bbb_sets["reps"].mean(), 1)

                properties = {
                    "Ejercicio": {"title": [{"text": {"content": f"{exercise} (BBB)"}}]},
                    "Fecha": {"date": {"start": date.strftime("%Y-%m-%d")}},
                    "Tipo": {"select": {"name": "bbb"}},
                    "Series": {"number": len(bbb_sets)},
                    "Reps": {"rich_text": [{"text": {"content": bbb_reps}}]},
                    "Top Set": {"rich_text": [{"text": {"content": f"{bbb_w}kg × {bbb_avg}"}}]},
                    "Peso (kg)": {"number": float(bbb_w)},
                    "Volumen (kg)": {"number": float(bbb_sets["volume_kg"].sum())},
                    "Hevy ID": {"rich_text": [{"text": {"content": hevy_id}}]},
                }
                if lift:
                    properties["Lift"] = {"select": {"name": LIFT_LABELS.get(lift, lift)}}
                    tm = TRAINING_MAX.get(lift)
                    if tm:
                        properties["% TM"] = {"number": round(bbb_w / tm, 3)}

                try:
                    _post("/pages", {"parent": {"database_id": NOTION_531_LOGBOOK_DB}, "properties": properties})
                    count += 1
                except Exception as e:
                    print(f"  ❌ Error syncing {exercise} (BBB): {e}")

        else:
            # Accessory exercise — one entry
            max_w = ex_df["weight_kg"].max()
            max_r = ex_df.loc[ex_df["weight_kg"] == max_w, "reps"].max() if max_w > 0 else ex_df["reps"].max()
            reps_str = ",".join(str(int(r)) for r in ex_df["reps"])

            properties = {
                "Ejercicio": {"title": [{"text": {"content": exercise}}]},
                "Fecha": {"date": {"start": date.strftime("%Y-%m-%d")}},
                "Tipo": {"select": {"name": "accessory"}},
                "Lift": {"select": {"name": "Accessory"}},
                "Series": {"number": len(ex_df)},
                "Reps": {"rich_text": [{"text": {"content": reps_str}}]},
                "Top Set": {"rich_text": [{"text": {"content": f"{max_w}kg × {max_r}" if max_w > 0 else f"BW × {max_r}"}}]},
                "Volumen (kg)": {"number": float(ex_df["volume_kg"].sum())},
                "Hevy ID": {"rich_text": [{"text": {"content": hevy_id}}]},
            }
            if max_w > 0:
                properties["Peso (kg)"] = {"number": float(max_w)}
            e1rm = ex_df["e1rm"].max()
            if e1rm > 0:
                properties["e1RM"] = {"number": float(e1rm)}

            try:
                _post("/pages", {"parent": {"database_id": NOTION_531_LOGBOOK_DB}, "properties": properties})
                count += 1
            except Exception as e:
                print(f"  ❌ Error syncing {exercise}: {e}")

    return count


def sync_531_logbook(df: pd.DataFrame) -> int:
    """Sync all new 531 workouts to Notion logbook."""
    if df.empty:
        return 0

    existing = get_synced_hevy_ids_531()
    new_ids = set(df["hevy_id"].unique()) - existing

    if not new_ids:
        return 0

    count = 0
    for hid in sorted(new_ids):
        session_df = df[df["hevy_id"] == hid]
        n = create_531_logbook_entry(session_df)
        count += n
        date = session_df["date"].iloc[0]
        print(f"  📝 {date.strftime('%Y-%m-%d')} | {n} entries")

    return count


# ═════════════════════════════════════════════════════════════════════
# ANALYTICS PAGE UPDATE
# ═════════════════════════════════════════════════════════════════════

def update_531_analytics_page(df: pd.DataFrame):
    """Replace the 531 analytics page with current data."""
    page_id = NOTION_531_ANALYTICS_PAGE
    if not page_id:
        print("  ⚠️ NOTION_531_ANALYTICS_PAGE not set — skipping")
        return

    print("📊 Updating 531 Analytics page...")

    # Delete existing content
    _delete_children(page_id)

    blocks = []
    now_str = datetime.now().strftime("%d %b %Y %H:%M")

    # ── Header ──
    blocks.append(_paragraph([
        _rt(f"Última actualización: {now_str}", color="gray"),
    ]))
    blocks.append(_divider())

    # ── 1. Global Summary ──
    summary = global_summary_531(df)
    blocks.append(_heading2("Resumen Global", "📊"))
    if summary:
        blocks.append(_paragraph([
            _rt(f"Sesiones: ", bold=True), _rt(f"{summary['total_sessions']}"),
            _rt(f" | Volumen: ", bold=True), _rt(f"{summary['total_volume_kg']:,} kg"),
            _rt(f" | Sets: ", bold=True), _rt(f"{summary['total_sets']}"),
            _rt(f" | AMRAPs: ", bold=True), _rt(f"{summary['amrap_count']}"),
        ]))

    # ── 2. Training Maxes ──
    blocks.append(_divider())
    blocks.append(_heading2("Training Maxes", "🎯"))
    tm_rows = []
    for lift, label in LIFT_LABELS.items():
        tm = TRAINING_MAX.get(lift)
        tm_rows.append([label, f"{tm} kg" if tm else "TBD"])
    blocks.append(_table(["Lift", "TM"], tm_rows))

    # ── 3. AMRAP Tracker ──
    blocks.append(_divider())
    blocks.append(_heading2("AMRAP Tracker", "🎯"))
    amraps = amrap_tracking(df)
    if not amraps.empty:
        amrap_rows = []
        for _, r in amraps.iterrows():
            label = LIFT_LABELS.get(r["lift"], r["lift"])
            over = r["reps_over_min"]
            status = "🟢" if over >= 3 else "🟡" if over >= 0 else "🔴"
            amrap_rows.append([
                r["date"].strftime("%d %b"),
                label,
                f"{r['weight_kg']}kg × {r['reps']}",
                f"{status} +{over}",
                f"{r['e1rm']}kg",
            ])
        blocks.append(_table(
            ["Fecha", "Lift", "AMRAP", "vs Mín", "e1RM"],
            amrap_rows,
        ))
    else:
        blocks.append(_paragraph([_rt("Sin datos de AMRAP aún.")]))

    # ── 4. BBB Compliance ──
    blocks.append(_divider())
    blocks.append(_heading2("BBB Supplemental", "📦"))
    bbb = bbb_compliance(df)
    if not bbb.empty:
        bbb_rows = []
        for _, r in bbb.iterrows():
            label = LIFT_LABELS.get(r["lift"], str(r["lift"]))
            status = "✅" if r["sets_ok"] and r["reps_ok"] else "⚠️"
            pct = f"{r['pct_of_tm']}%" if r["pct_of_tm"] else "-"
            bbb_rows.append([
                r["date"].strftime("%d %b"),
                label,
                f"{r['weight_kg']}kg ({pct} TM)",
                f"{r['n_sets']} × {r['avg_reps']}",
                status,
            ])
        blocks.append(_table(
            ["Fecha", "Lift", "Peso", "Sets × Reps", "OK"],
            bbb_rows,
        ))
    else:
        blocks.append(_paragraph([_rt("Sin datos BBB aún.")]))

    # ── 5. Accessories ──
    blocks.append(_divider())
    blocks.append(_heading2("Accesorios", "🔧"))
    acc = accessory_summary(df)
    if not acc.empty:
        acc_rows = []
        for _, r in acc.iterrows():
            acc_rows.append([
                r["muscle_group"],
                str(r["total_sets"]),
                str(r["total_reps"]),
                f"{r['total_volume']:,.0f} kg",
            ])
        blocks.append(_table(["Grupo", "Sets", "Reps", "Volumen"], acc_rows))
    else:
        blocks.append(_paragraph([_rt("Sin datos de accesorios aún.")]))

    # ── 6. Strength Standards ──
    blocks.append(_divider())
    blocks.append(_heading2("Strength Standards", "🏋️"))
    levels = strength_level_531(df)
    level_rows = []
    for lift, label in LIFT_LABELS.items():
        info = levels.get(lift, {})
        e1rm = info.get("e1rm")
        ratio = info.get("ratio_bw")
        level = info.get("level", "Sin datos")
        level_rows.append([
            label,
            f"{e1rm}kg" if e1rm else "-",
            f"{ratio}×BW" if ratio else "-",
            level,
        ])
    blocks.append(_table(["Lift", "e1RM", "×BW", "Nivel"], level_rows))

    # ── 7. Sessions ──
    blocks.append(_divider())
    blocks.append(_heading2("Sesiones", "💪"))
    sessions = session_summary_531(df)
    if not sessions.empty:
        sess_rows = []
        for _, s in sessions.iterrows():
            lift_label = LIFT_LABELS.get(s["main_lift"], s["main_lift"])
            sess_rows.append([
                s["date"].strftime("%d %b"),
                lift_label,
                f"{s['amrap_weight']}kg × {s['amrap_reps']}",
                f"{s['bbb_sets']}s × {s['bbb_avg_reps']}r",
                f"{s['total_volume']:,}kg",
            ])
        blocks.append(_table(
            ["Fecha", "Lift", "AMRAP", "BBB", "Vol Total"],
            sess_rows,
        ))

    # ── 8. PRs ──
    blocks.append(_divider())
    blocks.append(_heading2("PRs", "🏆"))
    prs = pr_table_531(df)
    if not prs.empty:
        pr_rows = []
        for _, r in prs.head(10).iterrows():
            pr_rows.append([
                r["exercise"],
                f"{r['max_weight']}kg",
                f"{r['max_e1rm']}kg",
            ])
        blocks.append(_table(["Ejercicio", "Peso Máx", "e1RM"], pr_rows))

    # ── Append all blocks ──
    _append_blocks(page_id, blocks)
    print(f"  ✅ 531 Analytics page updated ({len(blocks)} blocks)")
