"""
BBD Analytics — Notion API Client
Direct REST API integration for automated sync (GitHub Actions).
"""
import time
import requests
import pandas as pd
from src.config import NOTION_TOKEN, NOTION_BBD_LOGBOOK_DB

# Notion API rate limit: 3 req/s → sleep 0.35s between calls
RATE_LIMIT_DELAY = 0.35


BASE_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _post(endpoint: str, body: dict) -> dict:
    time.sleep(RATE_LIMIT_DELAY)
    r = requests.post(f"{BASE_URL}{endpoint}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def _patch(endpoint: str, body: dict) -> dict:
    r = requests.patch(f"{BASE_URL}{endpoint}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()


def query_database(database_id: str, filter_obj: dict = None) -> list[dict]:
    """Query a Notion database with optional filter."""
    body = {}
    if filter_obj:
        body["filter"] = filter_obj
    body["page_size"] = 100

    all_results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = _post(f"/databases/{database_id}/query", body)
        all_results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_results


def get_synced_hevy_ids(database_id: str = NOTION_BBD_LOGBOOK_DB) -> set[str]:
    """Get all Hevy IDs already synced to Notion."""
    pages = query_database(database_id)
    ids = set()
    for p in pages:
        props = p.get("properties", {})
        hevy_prop = props.get("Hevy ID", {})
        rt = hevy_prop.get("rich_text", [])
        if rt:
            ids.add(rt[0].get("plain_text", ""))
    return ids


def create_logbook_entry(row: pd.Series, database_id: str = NOTION_BBD_LOGBOOK_DB):
    """Create a single logbook entry in Notion from a DataFrame row."""
    properties = {
        "Ejercicio": {"title": [{"text": {"content": str(row["exercise"])}}]},
        "Día": {"select": {"name": str(row["day_name"])}},
        "Fecha": {"date": {"start": row["date"].strftime("%Y-%m-%d")}},
        "Semana": {"number": int(row["week"])},
        "Series": {"number": int(row["n_sets"])},
        "Reps": {"rich_text": [{"text": {"content": str(row["reps_str"])}}]},
        "Top Set": {"rich_text": [{"text": {"content": str(row["top_set"])}}]},
        "Hevy ID": {"rich_text": [{"text": {"content": str(row["hevy_id"])}}]},
        "PR? 🏆": {"checkbox": bool(row.get("is_pr", False))},
    }

    # Only add numeric fields if non-zero
    if row["max_weight"] > 0:
        properties["Peso (kg)"] = {"number": float(row["max_weight"])}
    if row["volume_kg"] > 0:
        properties["Volumen (kg)"] = {"number": float(row["volume_kg"])}
    if row["e1rm"] > 0:
        properties["e1RM"] = {"number": float(row["e1rm"])}
    if row.get("description"):
        properties["Notas"] = {
            "rich_text": [{"text": {"content": str(row["description"])[:2000]}}]
        }

    body = {"parent": {"database_id": database_id}, "properties": properties}
    return _post("/pages", body)


def sync_to_notion(df: pd.DataFrame, database_id: str = NOTION_BBD_LOGBOOK_DB) -> int:
    """
    Sync a DataFrame of exercises to Notion.
    Returns count of new entries created.
    """
    if df.empty:
        return 0

    existing_ids = get_synced_hevy_ids(database_id)
    new_df = df[~df["hevy_id"].isin(existing_ids)]

    if new_df.empty:
        return 0

    # Detect PRs
    new_df = _detect_prs(new_df, df)

    count = 0
    for _, row in new_df.iterrows():
        try:
            create_logbook_entry(row, database_id)
            count += 1
        except Exception as e:
            print(f"  ❌ Error syncing {row['exercise']}: {e}")

    return count


def _detect_prs(new_df: pd.DataFrame, all_df: pd.DataFrame) -> pd.DataFrame:
    """Mark PRs in new data based on all historical data. Uses template_id for matching."""
    new_df = new_df.copy()
    new_df["is_pr"] = False

    # Build historical max e1RM per exercise template_id (excluding new data)
    existing = all_df[~all_df["hevy_id"].isin(new_df["hevy_id"].unique())]
    key_col = "exercise_template_id" if "exercise_template_id" in existing.columns else "exercise"
    hist_max = existing.groupby(key_col)["e1rm"].max().to_dict() if not existing.empty else {}

    for idx, row in new_df.iterrows():
        if row["e1rm"] > 0:
            key = row.get("exercise_template_id", row["exercise"]) if key_col == "exercise_template_id" else row["exercise"]
            prev_max = hist_max.get(key, 0)
            if row["e1rm"] > prev_max:
                new_df.loc[idx, "is_pr"] = True
                hist_max[key] = row["e1rm"]

    return new_df
