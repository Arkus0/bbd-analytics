"""
Candito Linear Program — Notion Integration

Logbook sync and analytics page updates.
"""
import os
import requests
from datetime import datetime
import pandas as pd

from src.config_candito import (
    NOTION_CANDITO_LOGBOOK_DB, NOTION_CANDITO_ANALYTICS_PAGE,
    DAY_CONFIG_CANDITO, EXERCISE_DB_CANDITO, STRENGTH_STANDARDS_CANDITO,
    MAIN_LIFT_TIDS,
)
from src.config import NOTION_TOKEN, BODYWEIGHT

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN or os.environ.get('NOTION_TOKEN', '')}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _get_synced_ids() -> set:
    """Get already-synced Hevy IDs from Notion logbook."""
    token = NOTION_TOKEN or os.environ.get("NOTION_TOKEN", "")
    if not token:
        return set()
    headers = {**NOTION_HEADERS, "Authorization": f"Bearer {token}"}
    ids = set()
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_CANDITO_LOGBOOK_DB}/query",
            headers=headers, json=body, timeout=15,
        )
        if not r.ok:
            break
        data = r.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            hevy_rt = props.get("Hevy ID", {}).get("rich_text", [])
            if hevy_rt:
                ids.add(hevy_rt[0]["plain_text"])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return ids


def sync_candito_logbook(df: pd.DataFrame) -> int:
    """Sync new Candito workouts to Notion logbook."""
    if df.empty:
        return 0
    token = NOTION_TOKEN or os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("  ⚠️ No NOTION_TOKEN — skipping logbook sync")
        return 0
    headers = {**NOTION_HEADERS, "Authorization": f"Bearer {token}"}

    existing = _get_synced_ids()
    new_ids = set(df["hevy_id"].unique()) - existing
    if not new_ids:
        return 0

    synced = 0
    for hid in sorted(new_ids):
        session = df[df["hevy_id"] == hid]
        first = session.iloc[0]
        day_num = first["day_num"]
        day_cfg = DAY_CONFIG_CANDITO.get(day_num, {})
        day_label = f"D{day_num} {day_cfg.get('name', '')}"

        # Top set from main lifts
        main = session[session["role"] == "main"]
        if not main.empty:
            top = main.loc[main["e1rm"].idxmax()]
            top_set = top["top_set"]
        else:
            top_set = session.iloc[0]["top_set"]

        week_num = max(1, (first["date"] - pd.Timestamp("2026-03-08")).days // 7 + 1)

        page = {
            "parent": {"database_id": NOTION_CANDITO_LOGBOOK_DB},
            "properties": {
                "Sesión": {"title": [{"text": {"content": f"{day_label} — S{week_num}"}}]},
                "Fecha": {"date": {"start": str(first["date"].date())}},
                "Día": {"select": {"name": day_label.strip()}},
                "Semana": {"number": week_num},
                "Volumen (kg)": {"number": int(session["volume_kg"].sum())},
                "Ejercicios": {"number": len(session)},
                "Duración (min)": {"number": first["duration_min"]},
                "Hevy ID": {"rich_text": [{"text": {"content": hid}}]},
                "Top Set": {"rich_text": [{"text": {"content": top_set}}]},
            },
        }

        import time
        time.sleep(0.35)
        r = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers, json=page, timeout=15,
        )
        if r.ok:
            synced += 1
        else:
            print(f"  ⚠️ Notion logbook error for {hid}: {r.status_code}")

    return synced


def update_candito_analytics_page(df: pd.DataFrame) -> None:
    """Update the Candito analytics Notion page with current stats."""
    token = NOTION_TOKEN or os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("  ⚠️ No NOTION_TOKEN — skipping analytics update")
        return

    headers = {**NOTION_HEADERS, "Authorization": f"Bearer {token}"}
    page_id = NOTION_CANDITO_ANALYTICS_PAGE

    # Clear existing blocks
    _clear_page(page_id, headers)

    blocks = _build_analytics_blocks(df)
    if not blocks:
        return

    # Append in chunks of 100 (Notion limit)
    for i in range(0, len(blocks), 100):
        chunk = blocks[i:i + 100]
        import time
        time.sleep(0.35)
        r = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            json={"children": chunk},
            timeout=30,
        )
        if not r.ok:
            print(f"  ⚠️ Notion analytics append error: {r.status_code}")


def _clear_page(page_id: str, headers: dict) -> None:
    """Delete all blocks from a page."""
    import time
    r = requests.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100",
        headers=headers, timeout=15,
    )
    if not r.ok:
        return
    for block in r.json().get("results", []):
        time.sleep(0.15)
        requests.delete(
            f"https://api.notion.com/v1/blocks/{block['id']}",
            headers=headers, timeout=10,
        )


def _build_analytics_blocks(df: pd.DataFrame) -> list[dict]:
    """Build Notion blocks for analytics page."""
    blocks = []

    # Header
    blocks.append(_heading("💪 Candito LP Analytics", level=1))
    blocks.append(_text(f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"))
    blocks.append(_divider())

    if df.empty:
        blocks.append(_text("Sin datos todavía. ¡Empieza a entrenar!"))
        return blocks

    from src.analytics_candito import (
        global_summary_candito, pr_table_candito, analyze_progression,
        strength_level_candito,
    )

    # 1. Global Summary
    summary = global_summary_candito(df)
    blocks.append(_heading("📊 Resumen Global", level=2))
    blocks.append(_text(
        f"Sesiones: {summary['total_sessions']} · "
        f"Volumen total: {summary['total_volume_kg']:,} kg · "
        f"Sets: {summary['total_sets']} · "
        f"Duración media: {summary['avg_duration']} min"
    ))
    blocks.append(_divider())

    # 2. Progression Status
    prog = analyze_progression(df)
    if prog:
        blocks.append(_heading("📈 Estado de Progresión", level=2))
        for lk, info in sorted(prog.items()):
            status_emoji = {"progress": "🟢", "hold": "🟡", "stall": "🔴"}.get(info["status"], "⚪")
            blocks.append(_text(
                f"{status_emoji} {lk}: {info['current_weight']}kg → "
                f"{info['suggested_weight']}kg "
                f"({info['total_reps_done']}/{info['target_reps']} reps, "
                f"e1RM {info['e1rm']})"
            ))
        blocks.append(_divider())

    # 3. PRs
    prs = pr_table_candito(df)
    if not prs.empty:
        blocks.append(_heading("🏆 PRs", level=2))
        for _, row in prs.head(10).iterrows():
            blocks.append(_text(
                f"{row['exercise']}: {row['max_weight']}kg × {row['max_reps_at_max']} "
                f"(e1RM {row['e1rm']})"
            ))
        blocks.append(_divider())

    # 4. Strength Levels
    levels = strength_level_candito(df)
    if levels:
        blocks.append(_heading("🏋️ Strength Standards", level=2))
        for lv in levels:
            next_info = f" → {lv['next_level']} ({lv['pct_to_next']}%)" if lv["pct_to_next"] is not None else ""
            blocks.append(_text(
                f"{lv['exercise']}: {lv['level']} ({lv['ratio']}×BW){next_info}"
            ))

    return blocks


# ── Notion block helpers ─────────────────────────────────────────────

def _heading(text: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {key: {"rich_text": [{"text": {"content": text}}]}}


def _text(text: str) -> dict:
    # Truncate to Notion limit
    return {"paragraph": {"rich_text": [{"text": {"content": text[:2000]}}]}}


def _divider() -> dict:
    return {"divider": {}}
