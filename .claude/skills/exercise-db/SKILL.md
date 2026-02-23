---
name: exercise-db
description: Quick reference for BBD exercise template IDs, day assignments, and key lifts. Always consult src/config.py for the authoritative EXERCISE_DB.
user-invocable: false
---

# BBD Exercise Database — Quick Reference

Source of truth: `src/config.py` → `EXERCISE_DB` dict (36 exercises).

## Key Lifts (tracked for progression & ratios)

| Template ID | Exercise | Day | BBD Ratio |
|------------|----------|-----|-----------|
| `C6272009` | Deadlift (Barbell) | 1 | Baseline (1.0) |
| `073032BB` | Strict Press (OHP) | 2 | OHP/DL |
| `0B841777` | Shrug (Barbell) | 4 | Shrug/DL |
| `018ADC12` | Pendlay Row | 4 | Pendlay/DL |
| `40C6A9FC` | Zercher Squat | 5 | Squat/DL |
| `7bedf18e...` | Klokov Press | 6 | Klokov/DL |

## Historical / Replaced Exercises

| Template ID | Exercise | Status |
|------------|----------|--------|
| `2B4B7310` | Peso Muerto Rumano (PMR) | Replaced by conventional DL. Historical data uses ÷0.60 conversion. |
| `5046D0A9` | Front Squat | Replaced by Zercher Squat (40C6A9FC) on Day 5 |
| `d2c10c97...` | Reverse Deadlift (Bob Peoples) | Never used — bar hits thighs |

## Day Layout

- **Day 1**: DL + Legs → C6272009, 70D4EBBF, 83c10c44, B8127AD1, E05C2C38, 99D5F10E
- **Day 2**: Press + Shoulders → 073032BB, 50DFDFAB, 6AC96645, E644F828, b2f6fd25, 60c9c36b
- **Day 3**: Arms (optional) → 875F585F, 112FC6B7, 552AB030, 724CDE60, B5EFBF9C, 234897AB
- **Day 4**: Back + Traps → 0B841777, 018ADC12, F1E57334, 1B2B1E7C, F1D60854
- **Day 5**: Legs → 40C6A9FC, c7949429, B537D09F, 68B83EE0, 06745E58
- **Day 6**: Press + Chest → 7bedf18e, E644F828 (wide grip bench), 875F585F (skullcrusher 21s)

## Strength Standards (×bodyweight)

Key exercises have DOTS-based thresholds: `int` (intermediate), `adv` (advanced), `elite`.
Example: Deadlift → int=1.5, adv=2.0, elite=2.5 (×86kg BW).

## Matching Rules

1. **ALWAYS** use `exercise_template_id` for lookups
2. **NEVER** use exercise `title` — it's locale-dependent (Spanish/English)
3. If a template_id is not in EXERCISE_DB, it's a new exercise Juan added
4. Run `hevy-validator` agent before any exercise-related code change
