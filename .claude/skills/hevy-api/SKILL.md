---
name: hevy-api
description: Hevy API endpoints, authentication, pagination, and data structures for workout tracking
user-invocable: false
---

# Hevy API Reference

## Authentication

All requests require header: `api-key: <HEVY_API_KEY>`
Base URL: `https://api.hevyapp.com/v1`

## Key Endpoints

### GET /workouts
Paginated list of all workouts.
- Params: `page` (1-indexed), `pageSize` (max 10)
- Response: `{ "page": N, "page_count": N, "workouts": [...] }`
- BBD workouts: filtered by title matching `^Día [1-6]\b` (no A/B suffix)

### GET /workouts/{id}
Single workout detail.

### GET /routines
List all routines (templates).
- Useful for extracting exercise_template_ids

### GET /routine_folders
List routine folders. BBD folder ID: `2353809`, 531 folder ID: `2401466`.

## Workout Data Structure

```json
{
  "id": "uuid",
  "title": "Día 1 - Deadlift + Piernas",
  "start_time": "2026-02-12T18:00:00Z",
  "end_time": "2026-02-12T19:30:00Z",
  "exercises": [
    {
      "title": "Peso Muerto (Barra)",
      "exercise_template_id": "C6272009",
      "sets": [
        {
          "type": "normal",
          "weight_kg": 100,
          "reps": 6
        }
      ]
    }
  ]
}
```

## Critical Notes

- `exercise_template_id` is stable across languages — ALWAYS use this for matching
- `title` (exercise name) can be in Spanish or English depending on user locale — NEVER use for matching
- Set types: `normal`, `failure`, `dropset`, `warmup`. Working sets = normal + failure + dropset.
- Pagination: always loop until `page >= page_count`
- Rate limits: be conservative, add small delays for bulk fetches
