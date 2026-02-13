"""
BBD Analytics — Hevy API Client
"""
import re
import requests
import pandas as pd
from datetime import datetime
from src.config import HEVY_API_KEY, DAY_CONFIG

BASE_URL = "https://api.hevyapp.com/v1"
HEADERS = {"accept": "application/json", "api-key": HEVY_API_KEY}


def _get(endpoint: str, params: dict = None) -> dict:
    """GET request to Hevy API."""
    r = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params or {})
    r.raise_for_status()
    return r.json()


def is_bbd_workout(title: str) -> bool:
    """Check if a workout title matches BBD naming convention."""
    match = re.match(r"^Día\s+([1-6])\b", title)
    if not match:
        return False
    # Reject DC-style A/B rotations
    if re.search(r"\b[AB]\b", title):
        return False
    return True


def get_bbd_day_number(title: str) -> int | None:
    """Extract day number from BBD workout title."""
    match = re.match(r"^Día\s+([1-6])\b", title)
    if match and not re.search(r"\b[AB]\b", title):
        return int(match.group(1))
    return None


def fetch_all_workouts() -> list[dict]:
    """Fetch all workouts from Hevy, paginated."""
    all_workouts = []
    page = 1
    while True:
        data = _get("/workouts", {"page": page, "pageSize": 10})
        wks = data.get("workouts", [])
        if not wks:
            break
        all_workouts.extend(wks)
        if page >= data.get("page_count", 1):
            break
        page += 1
    return all_workouts


def fetch_bbd_workouts() -> list[dict]:
    """Fetch only BBD workouts (filtered)."""
    all_wk = fetch_all_workouts()
    return [w for w in all_wk if is_bbd_workout(w["title"])]


def workouts_to_dataframe(workouts: list[dict]) -> pd.DataFrame:
    """
    Convert raw Hevy workouts to a flat pandas DataFrame.
    One row per exercise per workout.
    """
    rows = []
    for w in workouts:
        date = w["start_time"][:10]
        title = w["title"]
        hevy_id = w["id"]
        day_num = get_bbd_day_number(title)
        day_name = DAY_CONFIG.get(day_num, {}).get("name", title) if day_num else title

        start = datetime.fromisoformat(w["start_time"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(w["end_time"].replace("Z", "+00:00"))
        duration_min = round((end - start).total_seconds() / 60)
        description = w.get("description", "") or ""

        for ex in w.get("exercises", []):
            sets = ex.get("sets", [])
            working = [
                s
                for s in sets
                if s.get("type") in ("normal", "failure", "dropset", None)
            ]
            if not working:
                working = sets

            reps_list = [s.get("reps", 0) or 0 for s in working]
            weights = [s.get("weight_kg", 0) or 0 for s in working]
            volume = sum(wt * r for wt, r in zip(weights, reps_list))

            max_w = max(weights) if weights else 0
            reps_at_max = [r for wt, r in zip(weights, reps_list) if wt == max_w]
            max_r = max(reps_at_max) if reps_at_max else 0

            # Epley e1RM
            if max_w > 0 and max_r > 0:
                e1rm = round(max_w * (1 + max_r / 30), 1) if max_r > 1 else max_w
            else:
                e1rm = 0

            rows.append(
                {
                    "date": pd.Timestamp(date),
                    "hevy_id": hevy_id,
                    "workout_title": title,
                    "day_num": day_num,
                    "day_name": day_name,
                    "duration_min": duration_min,
                    "description": description,
                    "exercise": ex["title"],
                    "exercise_template_id": ex.get("exercise_template_id", ""),
                    "n_sets": len(working),
                    "reps_list": reps_list,
                    "reps_str": ",".join(str(r) for r in reps_list),
                    "total_reps": sum(reps_list),
                    "max_weight": max_w,
                    "max_reps_at_max": max_r,
                    "volume_kg": volume,
                    "e1rm": e1rm,
                    "top_set": f"{max_w}kg x {max_r}" if max_w > 0 else f"BW x {max_r}",
                    "is_bodyweight": max_w == 0,
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "day_num"]).reset_index(drop=True)
    return df
