---
name: test-sync
description: Runs a dry-run sync to verify the full pipeline works without writing to Notion. Use after code changes to analytics, notion_analytics, or sync.
allowed-tools: Read, Bash
---

# Test Sync

Run the following validation steps in order:

## Step 1: Syntax Check
```bash
python3 -c "
import ast
for f in ['src/config.py', 'src/analytics.py', 'src/notion_analytics.py', 'src/hevy_client.py', 'src/sync.py', 'app.py']:
    ast.parse(open(f).read())
    print(f'✅ {f}')
"
```

## Step 2: Import Check
```bash
python3 -c "
from src.config import EXERCISE_DB, DAY_CONFIG, BODYWEIGHT
from src.hevy_client import fetch_bbd_workouts, workouts_to_dataframe
from src.analytics import compute_all
print(f'✅ All imports OK')
print(f'   EXERCISE_DB: {len(EXERCISE_DB)} exercises')
print(f'   DAY_CONFIG: {len(DAY_CONFIG)} days')
print(f'   BODYWEIGHT: {BODYWEIGHT} kg')
"
```

## Step 3: Dry Run Sync (if API keys available)
```bash
python3 -m src.sync --dry-run 2>&1
```

Report the results of each step. If any step fails, diagnose the issue and suggest a fix.
