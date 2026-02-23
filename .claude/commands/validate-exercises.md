---
name: validate-exercises
description: Validates that EXERCISE_DB in config.py matches real Hevy workout data. Run this before any exercise-related code change.
allowed-tools: Read, Bash, WebFetch
---

# Validate Exercises

Delegate this task to the `hevy-validator` agent:

Use the Task tool to invoke `hevy-validator` with the following prompt:

"Fetch the 5 most recent BBD workouts from Hevy API and compare all exercise_template_ids against EXERCISE_DB in src/config.py. Report matches, unknowns, and missing exercises. HEVY_API_KEY is set as an environment variable."

After the agent completes, summarize the findings and recommend any config.py updates needed.
