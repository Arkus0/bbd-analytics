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

# 531 imports
from src.analytics_531 import (
    fetch_bbb_workouts, workouts_to_dataframe_531, add_cycle_info,
    global_summary_531, pr_table_531, update_hevy_routines,
)
from src.notion_531 import sync_531_logbook, update_531_analytics_page


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
        if not dry_run:
            from src.notion_analytics import update_analytics_page
            print()
            update_analytics_page(df)
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

    # 5. Update Analytics page
    if not dry_run:
        from src.notion_analytics import update_analytics_page
        print()
        update_analytics_page(df)

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


def run_531_sync(dry_run: bool = False) -> dict:
    """
    531 BBB sync pipeline:
    1. Fetch BBB workouts from Hevy
    2. Convert to DataFrame
    3. Sync new entries to Notion logbook
    4. Update analytics page
    """
    print("\n💀 531 BBB Sync — Starting...")

    # 1. Fetch
    print("\n📥 Fetching 531 BBB workouts from Hevy...")
    workouts = fetch_bbb_workouts()
    print(f"   Found {len(workouts)} BBB workouts")

    if not workouts:
        print("   No BBB workouts found. Done.")
        return {"synced": 0, "total": 0}

    # 2. Convert
    df = workouts_to_dataframe_531(workouts)
    df = add_cycle_info(df)
    print(f"   {len(df)} set entries across {df['hevy_id'].nunique()} sessions")

    # 3. Sync logbook
    if dry_run:
        print("\n🏃 DRY RUN — skipping Notion write")
        synced = 0
    else:
        print("\n📤 Syncing 531 logbook to Notion...")
        synced = sync_531_logbook(df)
        print(f"   ✅ Created {synced} entries in Notion")

    # 4. Update Analytics page
    if not dry_run:
        print()
        update_531_analytics_page(df)

    # 5. Update Hevy routines with correct weights for current week/cycle
    if not dry_run:
        print("\n🔄 Updating Hevy routines...")
        routine_results = update_hevy_routines(df)
        for day, info in sorted(routine_results.items()):
            if info["status"] == "updated":
                print(f"   ✅ Day {day} ({info['lift']}): {info['week']} C{info['cycle']}")
            elif info["status"] == "skipped":
                print(f"   ⏭️ Day {day}: {info.get('reason', 'skipped')}")
            else:
                print(f"   ❌ Day {day}: {info.get('msg', 'error')}")

    # Summary
    summary = global_summary_531(df)
    prs = pr_table_531(df)

    print(f"\n{'='*50}")
    print(f"💀 531 BBB Summary:")
    print(f"   Sessions: {summary.get('total_sessions', 0)}")
    print(f"   Total volume: {summary.get('total_volume_kg', 0):,} kg")
    if not prs.empty:
        print(f"\n🏆 Top PRs:")
        for _, row in prs.head(5).iterrows():
            print(f"   {row['exercise']}: {row['max_weight']}kg (e1RM {row['max_e1rm']})")

    return {"synced": synced, "total": len(df)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    # Run both syncs
    bbd_result = run_sync(dry_run=dry)
    bbb_result = run_531_sync(dry_run=dry)
    print(f"\nDone. BBD: {bbd_result['synced']} new. 531: {bbb_result['synced']} new.")
