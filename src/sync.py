"""
BBD Analytics — Sync Orchestrator
Run via GitHub Actions or manually: python -m src.sync
"""
import sys
from datetime import datetime
from src.hevy_client import fetch_bbd_workouts, workouts_to_dataframe
from src.analytics import add_derived_columns, global_summary, pr_table
from src.notion_client import sync_to_notion, get_synced_hevy_ids
from src.config import NOTION_BBD_LOGBOOK_DB


def run_sync(dry_run: bool = False) -> dict:
    """
    Full sync pipeline:
    1. Fetch BBD workouts from Hevy
    2. Convert to DataFrame
    3. Filter already-synced
    4. Push new entries to Notion
    """
    print("🔄 BBD Sync — Starting...")
    print(f"   {datetime.now().isoformat()}")

    # 1. Fetch
    print("\n📥 Fetching workouts from Hevy...")
    workouts = fetch_bbd_workouts()
    print(f"   Found {len(workouts)} BBD workouts")

    if not workouts:
        print("   No BBD workouts found. Done.")
        return {"synced": 0, "total": 0}

    # 2. Convert
    df = workouts_to_dataframe(workouts)
    df = add_derived_columns(df)
    print(f"   {len(df)} exercise entries across {df['hevy_id'].nunique()} sessions")

    # 3. Check existing
    print("\n🔍 Checking Notion for existing entries...")
    existing = get_synced_hevy_ids(NOTION_BBD_LOGBOOK_DB)
    new_ids = set(df["hevy_id"].unique()) - existing
    print(f"   Already synced: {len(existing)} workout IDs")
    print(f"   New to sync: {len(new_ids)} workout IDs")

    if not new_ids:
        print("\n✅ Everything up to date. No new workouts to sync.")
        return {"synced": 0, "total": len(df)}

    new_df = df[df["hevy_id"].isin(new_ids)]
    print(f"\n📊 New data to sync:")
    for hid in sorted(new_ids):
        session = new_df[new_df["hevy_id"] == hid].iloc[0]
        print(f"   📅 {session['date'].date()} | {session['workout_title']} | {new_df[new_df['hevy_id']==hid]['n_sets'].sum()} sets")

    # 4. Sync
    if dry_run:
        print("\n🏃 DRY RUN — skipping Notion write")
        synced = len(new_df)
    else:
        print("\n📤 Syncing to Notion...")
        synced = sync_to_notion(new_df, NOTION_BBD_LOGBOOK_DB)
        print(f"   ✅ Created {synced} entries in Notion")

    # Summary
    summary = global_summary(df)
    prs = pr_table(df)

    print(f"\n{'='*50}")
    print(f"📊 Program Summary:")
    print(f"   Sessions: {summary.get('total_sessions', 0)}")
    print(f"   Total volume: {summary.get('total_volume', 0):,} kg")
    print(f"   Total sets: {summary.get('total_sets', 0)}")
    if not prs.empty:
        print(f"\n🏆 Top PRs:")
        for _, row in prs.head(5).iterrows():
            print(f"   {row['exercise']}: {row['max_weight']}kg x{row['max_reps_at_max']} (e1RM {row['e1rm']})")

    return {"synced": synced, "total": len(df)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = run_sync(dry_run=dry)
    print(f"\nDone. Synced {result['synced']} new entries.")
