---
name: notion-blocks
description: Notion API block construction patterns and limitations for BBD analytics page updates
user-invocable: false
---

# Notion Blocks Reference for BBD

## Analytics Page Update Flow

1. Delete all existing children of the analytics page
2. Build new blocks via `notion_analytics.py` section builders
3. Append blocks in batches (max 100 per request)

## Block Construction Patterns

### Section Header
```python
{"object": "block", "type": "heading_2", "heading_2": {
    "rich_text": [{"type": "text", "text": {"content": "📊 Section Title"}}]
}}
```

### Rich Text with Bold/Color
```python
{"type": "text", "text": {"content": "value"}, "annotations": {"bold": True, "color": "green"}}
```

### Table Block
```python
{"type": "table", "table": {
    "table_width": N,
    "has_column_header": True,
    "has_row_header": False,
    "children": [table_rows...]
}}
```

### Callout (for summaries)
```python
{"type": "callout", "callout": {
    "icon": {"type": "emoji", "emoji": "🔥"},
    "rich_text": [{"type": "text", "text": {"content": "message"}}]
}}
```

## Critical Limits

| Constraint | Limit |
|-----------|-------|
| Blocks per append request | **100 max** |
| Rich text content length | 2000 chars max |
| Table rows | Part of the 100 block limit |
| Nested blocks | Max 2 levels deep |

## 18 Analytics Sections

1-4: Global summary, weekly volume, PRs, muscle distribution
5-8: Relative intensity, BBD ratios, intra-session fatigue, density
9-11: Key lifts progression, pull-ups, DOTS standards
12-13: Recovery indicators, adherence
14-17: Phase 1 intelligence (plateau, ACWR, mesocycles, strength profile)
18: Gamification RPG

## Common Pitfalls

- Exceeding 100 blocks silently truncates — split into multiple appends
- Empty rich_text arrays cause 400 errors — always have at least one text element
- Notion API version header required: `Notion-Version: 2022-06-28`
- Page ID format: use with dashes for API calls
