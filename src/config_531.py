"""
531 BBB Analytics — Configuration

Wendler's 5/3/1 Boring But Big program configuration.
Training Maxes, cycle percentages, exercise mapping.
"""
import os

# ── Hevy / Notion IDs ────────────────────────────────────────────────
BBB_FOLDER_ID = 2401466
NOTION_531_LOGBOOK_DB = os.environ.get(
    "NOTION_531_LOGBOOK_DB", "31e7df96-6afb-4b58-a34c-817cb2bf887d"
)
NOTION_531_ANALYTICS_PAGE = os.environ.get(
    "NOTION_531_ANALYTICS_PAGE", "30dcbc49-9cfe-81fb-8d7e-ebe669b303be"
)

# ── Physical ─────────────────────────────────────────────────────────
from src.config import BODYWEIGHT  # Single source of truth
PROGRAM_START_531 = "2026-02-20"

# ── Training Maxes (updated each cycle) ──────────────────────────────
# TM = ~90% of true 1RM. Updated after each 3-week cycle.
# None = not yet established (waiting for first session)
TRAINING_MAX = {
    "ohp":      58,     # From BBB Day 1 data: 85% x 50kg → TM ≈ 58
    "deadlift": 140,    # From BBD data: e1RM 156kg → TM ≈ 140
    "bench":    84,     # Recalibrated: 64kg×16 AMRAP → e1RM ~98kg → TM ~85% ≈ 84
    "squat":    80,     # Conservative: no back squat history, based on front sq/zercher
}

# ── TM History — single source of truth for past + present TMs ───────
# Each entry: {"from": ISO date, "base_tm": kg, "bumps_applied": int}
# "bumps_applied" = how many auto-bumps had already occurred when this
# base was set.  Recalibrations reset the base; automatic bumps stack on top.
#
# To add a recalibration: append a new entry with the date it takes effect
# and bumps_applied = number of bumps completed at that point.
TM_HISTORY = {
    "ohp": [
        {"from": "2026-02-20", "base_tm": 58, "bumps_applied": 0},
    ],
    "deadlift": [
        {"from": "2026-02-20", "base_tm": 140, "bumps_applied": 0},
    ],
    "bench": [
        {"from": "2026-02-20", "base_tm": 76, "bumps_applied": 0},
        # Recalibrated after 64kg×16 AMRAP on 2026-02-23 → e1RM ~98 → TM ~84
        {"from": "2026-02-24", "base_tm": 84, "bumps_applied": 0},
    ],
    "squat": [
        {"from": "2026-02-20", "base_tm": 80, "bumps_applied": 0},
    ],
}

# TM increment per cycle
TM_INCREMENT = {
    "ohp":      2,     # Upper body: +2 kg/cycle (smallest: 1kg/side)
    "deadlift": 4,     # Lower body: +4 kg/cycle (2kg/side)
    "bench":    2,
    "squat":    4,
}

# ── 531 Cycle Structure — Beyond 5/3/1 ───────────────────────────────
# Macro cycle = 7 weeks: 3 working + 3 working + 1 deload
# TM bumps after each 3-week mini-cycle (+2kg upper, +4kg lower)
# No deload between mini-cycles — deload only on week 7.
#
# Week 1: 5s   (mini-cycle A)
# Week 2: 3s   (mini-cycle A)
# Week 3: 531  (mini-cycle A) → bump TM
# Week 4: 5s   (mini-cycle B, new TM)
# Week 5: 3s   (mini-cycle B)
# Week 6: 531  (mini-cycle B) → bump TM
# Week 7: Deload
MACRO_CYCLE_LENGTH = 7  # weeks in a full macro cycle
WORKING_BLOCK_LENGTH = 3  # weeks in each working mini-cycle
SESSIONS_PER_WEEK = 4  # one session per main lift (OHP, DL, Bench, Squat)

CYCLE_WEEKS = {
    1: {  # "5s week"
        "name": "Semana 5s",
        "sets": [
            {"pct": 0.65, "reps": 5},
            {"pct": 0.75, "reps": 5},
            {"pct": 0.85, "reps": "5+"},  # AMRAP
        ],
    },
    2: {  # "3s week"
        "name": "Semana 3s",
        "sets": [
            {"pct": 0.70, "reps": 3},
            {"pct": 0.80, "reps": 3},
            {"pct": 0.90, "reps": "3+"},  # AMRAP
        ],
    },
    3: {  # "1s week" / "531 week"
        "name": "Semana 531",
        "sets": [
            {"pct": 0.75, "reps": 5},
            {"pct": 0.85, "reps": 3},
            {"pct": 0.95, "reps": "1+"},  # AMRAP
        ],
    },
    4: {  # Deload (only used on week 7 of macro)
        "name": "Deload",
        "sets": [
            {"pct": 0.40, "reps": 5},
            {"pct": 0.50, "reps": 5},
            {"pct": 0.60, "reps": 5},
        ],
    },
}

# BBB supplemental percentages progression across cycles
BBB_PCT_PROGRESSION = {
    1: 0.50,  # First cycle: 50% of TM
    2: 0.55,
    3: 0.60,  # Progression ceiling for most
    4: 0.60,
    5: 0.65,
    6: 0.70,  # Advanced only
}

# ══════════════════════════════════════════════════════════════════════
# FOREVER 5/3/1 — Leader / Anchor Framework
# ══════════════════════════════════════════════════════════════════════
#
# Structure per block:
#   [Leader × leader_cycles] + [7th Week Deload] + [Anchor × anchor_cycles] + [7th Week TM Test]
# Each cycle = 3 weeks. Deload/TM Test = 1 week each.
# TM bumps after each completed 3-week cycle (leader OR anchor).
#
# Pre-plan: current Beyond 5/3/1 macro runs until PLAN_START_SESSION.
# After that, YEARLY_PLAN takes over.

# How many sessions (completed) before the Forever plan starts.
# Current macro: 8 sessions done → ~20 more to finish (weeks 3-7 = 5 weeks × 4).
# Set to 28 = 7 weeks × 4 sessions (full first Beyond macro).
PLAN_START_SESSION = 28

# ── Supplemental Templates ───────────────────────────────────────────
# Each template defines how to build the supplemental portion of a workout.
# "sets_spec" is a list of {reps, pct_source, count} where:
#   pct_source: "fixed_pct" (of TM), "fsl" (first working set %), "ssl" (second set)
#   Or a callable week→pct pattern for Forever BBB.

SUPPLEMENTAL_TEMPLATES = {
    "bbb_forever": {
        "name": "Forever BBB",
        "description": "5×10, percentage varies by week (60/50/70 for 3/5/1). Book p48-49.",
        "role": "leader",
        "sets_per_session": 5,
        "reps_per_set": 10,
        # Book: Forever BBB option 1 (beginner/intermediate)
        # Week 1 (5s): 60%, Week 2 (3s): 50%, Week 3 (531): 70%
        "pct_by_week": {1: 0.60, 2: 0.50, 3: 0.70},
        "pct_source": "fixed_pct",
    },
    "bbb_fsl": {
        "name": "BBB, FSL",
        "description": "5×10 at FSL percentages (65/70/75). Heaviest BBB variant. Book p53-54.",
        "role": "leader",
        "sets_per_session": 5,
        "reps_per_set": 10,
        # Book: BBB FSL uses first working set % as BBB weight
        # 5s week FSL=65%, 3s week FSL=70%, 531 week FSL=75%
        "pct_by_week": {1: 0.65, 2: 0.70, 3: 0.75},
        "pct_source": "fixed_pct",
    },
    "bbb_constant": {
        "name": "Original BBB",
        "description": "5×10 @ constant 50-55% TM. Book p49-50.",
        "role": "leader",
        "sets_per_session": 5,
        "reps_per_set": 10,
        "pct_by_week": {1: 0.50, 2: 0.50, 3: 0.50},
        "pct_source": "fixed_pct",
    },
    "bbb_challenge": {
        "name": "BBB Challenge",
        "description": "5×10, pct increases per cycle (50→60→70). Book p52-53.",
        "role": "leader",
        "sets_per_session": 5,
        "reps_per_set": 10,
        # Book: cycle 1=50%, cycle 2=60%, cycle 3=70%
        "pct_by_cycle": {1: 0.50, 2: 0.60},
        "pct_source": "fixed_pct",
    },
    "fsl_5x5": {
        "name": "FSL 5×5",
        "description": "5×5 at First Set Last weight. Book p58-63.",
        "role": "anchor",
        "sets_per_session": 5,
        "reps_per_set": 5,
        "pct_by_week": {1: None, 2: None, 3: None},  # None = use FSL
        "pct_source": "fsl",
    },
    "ssl_5x5": {
        "name": "SSL 5×5",
        "description": "5×5 at Second Set Last weight. Book p85-86 (Volume & Strength).",
        "role": "leader",  # SSL appears as leader supplemental, not anchor for BBB
        "sets_per_session": 5,
        "reps_per_set": 5,
        # SSL = second working set percentage: 75%/80%/85%
        "pct_by_week": {1: 0.75, 2: 0.80, 3: 0.85},
        "pct_source": "fixed_pct",
    },
    "widowmaker": {
        "name": "Widowmaker",
        "description": "1×20 at First Set Last weight. Book p66-70.",
        "role": "anchor",
        "sets_per_session": 1,
        "reps_per_set": 20,
        "pct_by_week": {1: None, 2: None, 3: None},
        "pct_source": "fsl",
    },
    "5x5_531": {
        "name": "5x5/3/1",
        "description": "5×5 at the top set weight (85/90/95%)",
        "role": "leader",
        "sets_per_session": 5,
        "reps_per_set": 5,
        # The 5x5 IS the main work — top set pct varies by week
        "pct_by_week": {1: 0.85, 2: 0.90, 3: 0.95},
        "pct_source": "fixed_pct",
        "replaces_main_work": True,  # No separate 531 sets, 5x5 IS the workout
    },
    "5x5_531_anchor": {
        "name": "5x5/3/1 Anchor",
        "description": "Higher intensity: 5×3@90%, 5×5@85%, 3×3@95%",
        "role": "anchor",
        "sets_per_session": 5,
        "reps_per_set": None,  # varies by week
        "week_spec": {
            1: {"sets": 5, "reps": 3, "pct": 0.90},
            2: {"sets": 5, "reps": 5, "pct": 0.85},
            3: {"sets": 3, "reps": 3, "pct": 0.95},
        },
        "pct_source": "fixed_pct",
        "replaces_main_work": True,
    },
    "svr2": {
        "name": "SVR II",
        "description": "Week 1: Widowmaker, Week 2: BBB, Week 3: SSL 5×5",
        "role": "leader",
        "week_spec": {
            1: {"type": "widowmaker", "sets": 1, "reps": "15-20", "pct_source": "fsl"},
            2: {"type": "bbb", "sets": 5, "reps": 10, "pct": 0.65, "pct_source": "fixed_pct"},
            3: {"type": "ssl", "sets": 5, "reps": 5, "pct": 0.85, "pct_source": "fixed_pct"},
        },
        "pct_source": "mixed",
    },
    "none": {
        "name": "No supplemental",
        "description": "Used during 7th week protocol",
        "role": "deload",
        "sets_per_session": 0,
        "reps_per_set": 0,
        "pct_source": "none",
    },
}

# ── Main Work Modes ──────────────────────────────────────────────────
# How the 3 working sets behave in each phase.
MAIN_WORK_MODES = {
    "5s_pro": {
        "name": "5's Progression",
        "description": "All sets ×5, no AMRAP. Focus on bar speed.",
        "amrap": False,
        "reps_override": 5,  # All working sets are 5 reps
    },
    "pr_set": {
        "name": "PR Set",
        "description": "Standard 5/3/1 with AMRAP on top set.",
        "amrap": True,
        "reps_override": None,
    },
    "pr_set_jokers": {
        "name": "PR Set + Jokers",
        "description": "AMRAP on top set, then 1-2 joker sets above.",
        "amrap": True,
        "reps_override": None,
        "jokers": True,
    },
    "tm_test": {
        "name": "TM Test",
        "description": "Work up to TM for 3-5 reps. 70%×5, 80%×5, 90%×5, TM×3-5.",
        "amrap": False,
        "custom_sets": [
            {"pct": 0.70, "reps": 5},
            {"pct": 0.80, "reps": 5},
            {"pct": 0.90, "reps": 5},
            {"pct": 1.00, "reps": 5},  # Target: 3-5 reps
        ],
    },
    "deload": {
        "name": "Deload",
        "description": "Light work: 70%×5, 80%×3, 90%×1, TM×1.",
        "amrap": False,
        "custom_sets": [
            {"pct": 0.70, "reps": 5},
            {"pct": 0.80, "reps": 3},
            {"pct": 0.90, "reps": 1},
            {"pct": 1.00, "reps": 1},
        ],
    },
}

# ── Yearly Plan ──────────────────────────────────────────────────────
# Each block = 2 leader cycles + deload + 1 anchor cycle + TM test = 11 weeks.
# Block durations:
#   leader_weeks = leader_cycles × 3
#   deload_weeks = 1
#   anchor_weeks = anchor_cycles × 3
#   tm_test_weeks = 1
#   total = leader_weeks + 1 + anchor_weeks + 1

YEARLY_PLAN = [
    {
        # Book combo (p74, Program 4): Leader BBB → Anchor PR Set + Jokers + FSL
        "block": 1,
        "name": "Base — Forever BBB",
        "leader_template": "bbb_forever",
        "leader_main_work": "5s_pro",
        "leader_cycles": 2,
        "anchor_template": "fsl_5x5",
        "anchor_main_work": "pr_set_jokers",
        "anchor_cycles": 1,
        "tm_pct": 85,  # Book p45: 85% TM for BBB
        "notes": "Book p48-49. Forever BBB 60/50/70%. Anchor PR Set+Jokers+FSL (p74 Program 4).",
    },
    {
        # Book combo (p52-53): BBB Challenge → Original 5/3/1 or PR Set+FSL
        "block": 2,
        "name": "Empuje — BBB Challenge",
        "leader_template": "bbb_challenge",
        "leader_main_work": "5s_pro",
        "leader_cycles": 2,
        "anchor_template": "fsl_5x5",
        "anchor_main_work": "pr_set_jokers",
        "anchor_cycles": 1,
        "tm_pct": 85,  # Book p52: BBB Challenge uses 85% TM (90% max for beginners)
        "notes": "Book p52-53. Challenge: cycle1=50%, cycle2=60%. Anchor PR Set+Jokers+FSL.",
    },
    {
        # Book (p87-95): 5x5/3/1 leader → 5x5/3/1 Anchor
        "block": 3,
        "name": "Fuerza — 5x5/3/1",
        "leader_template": "5x5_531",
        "leader_main_work": "5s_pro",  # 5x5 replaces main+supplemental
        "leader_cycles": 2,
        "anchor_template": "5x5_531_anchor",
        "anchor_main_work": "5s_pro",
        "anchor_cycles": 1,
        "tm_pct": 80,  # Book p88: 80% TM mandatory, no higher
        "notes": "Book p87-95. 5x5 at 85/90/95% TM. Anchor 5x3@90%,5x5@85%,3x3@95%. TM 80% mandatory.",
    },
    {
        # Book (p77-80): SVR II leader → standard FSL anchor
        "block": 4,
        "name": "Variedad — SVR II",
        "leader_template": "svr2",
        "leader_main_work": "pr_set",  # SVR II week 1 has PR set
        "leader_cycles": 2,
        "anchor_template": "fsl_5x5",
        "anchor_main_work": "pr_set_jokers",
        "anchor_cycles": 1,
        "tm_pct": 85,  # Book p77: 85% TM
        "notes": "Book p77-80. SVR II: Widowmaker/BBB@65%/SSL@85% rotating. Anchor PR Set+Jokers+FSL.",
    },
    {
        # Book (p53-54): BBB FSL is the heaviest book-approved BBB variant
        "block": 5,
        "name": "Cierre — BBB FSL",
        "leader_template": "bbb_fsl",
        "leader_main_work": "5s_pro",
        "leader_cycles": 2,
        "anchor_template": "fsl_5x5",
        "anchor_main_work": "pr_set_jokers",
        "anchor_cycles": 1,
        "tm_pct": 85,  # Book p53-54: conservative TM required for BBB FSL
        "notes": "Book p53-54. BBB FSL (65/70/75%) — heaviest BBB variant in the book. Anchor PR Set+Jokers+FSL.",
    },
]


def get_block_weeks(block: dict) -> int:
    """Total weeks in a block: leader + deload + anchor + TM test."""
    return block["leader_cycles"] * 3 + 1 + block["anchor_cycles"] * 3 + 1


def get_plan_position(total_sessions: int) -> dict:
    """
    Calculate position in the Forever yearly plan.

    Returns dict with:
        phase: "pre_plan" | "leader" | "7th_week_deload" | "anchor" | "7th_week_tm_test"
        block: block dict from YEARLY_PLAN (or None for pre_plan)
        block_num: 1-based block number
        cycle_in_phase: which cycle within leader/anchor (1-based)
        week_type: 1 (5s), 2 (3s), 3 (531), or 4 (deload/TM test)
        week_in_block: absolute week within current block (1-based)
        tm_bumps_total: total TM bumps from plan start
        supplemental_template: template key from SUPPLEMENTAL_TEMPLATES
        main_work_mode: mode key from MAIN_WORK_MODES
    """
    if total_sessions < PLAN_START_SESSION:
        # Still in pre-plan (legacy Beyond 5/3/1 macro)
        legacy = get_cycle_position(total_sessions)
        return {
            "phase": "pre_plan",
            "block": None,
            "block_num": 0,
            "cycle_in_phase": legacy.get("mini_cycle"),
            "week_type": legacy["week_type"],
            "week_name": legacy["week_name"],
            "week_in_block": legacy["week_in_macro"],
            "tm_bumps_total": legacy["tm_bumps_completed"],
            "supplemental_template": "bbb_constant",
            "main_work_mode": "pr_set",
            "macro_num": legacy["macro_num"],
        }

    # Sessions into the plan
    plan_sessions = total_sessions - PLAN_START_SESSION
    plan_weeks = plan_sessions // SESSIONS_PER_WEEK

    # Walk through blocks to find position
    cumulative_weeks = 0
    cumulative_bumps = 0
    # Count bumps from pre-plan (2 bumps per completed Beyond macro)
    pre_plan_macros = PLAN_START_SESSION // (MACRO_CYCLE_LENGTH * SESSIONS_PER_WEEK)
    pre_plan_bumps = pre_plan_macros * 2
    cumulative_bumps = pre_plan_bumps

    for block in YEARLY_PLAN:
        block_total_weeks = get_block_weeks(block)
        leader_weeks = block["leader_cycles"] * 3
        anchor_weeks = block["anchor_cycles"] * 3

        if plan_weeks < cumulative_weeks + block_total_weeks:
            # We're in this block
            week_in_block = plan_weeks - cumulative_weeks  # 0-based
            w = week_in_block

            # Phase breakdown within block:
            # [0..leader_weeks-1] = leader
            # [leader_weeks] = 7th week deload
            # [leader_weeks+1..leader_weeks+anchor_weeks] = anchor
            # [leader_weeks+1+anchor_weeks] = 7th week TM test

            if w < leader_weeks:
                # Leader phase
                cycle_in_leader = w // 3 + 1  # 1 or 2
                week_in_cycle = w % 3 + 1  # 1, 2, or 3
                # Bumps from completed leader cycles
                bumps_in_block = w // 3
                return {
                    "phase": "leader",
                    "block": block,
                    "block_num": block["block"],
                    "cycle_in_phase": cycle_in_leader,
                    "week_type": week_in_cycle,
                    "week_name": CYCLE_WEEKS[week_in_cycle]["name"],
                    "week_in_block": w + 1,
                    "tm_bumps_total": cumulative_bumps + bumps_in_block,
                    "supplemental_template": block["leader_template"],
                    "main_work_mode": block["leader_main_work"],
                }

            elif w == leader_weeks:
                # 7th week deload (between leader and anchor)
                bumps_in_block = block["leader_cycles"]
                return {
                    "phase": "7th_week_deload",
                    "block": block,
                    "block_num": block["block"],
                    "cycle_in_phase": None,
                    "week_type": 4,
                    "week_name": "Deload (7th Week)",
                    "week_in_block": w + 1,
                    "tm_bumps_total": cumulative_bumps + bumps_in_block,
                    "supplemental_template": "none",
                    "main_work_mode": "deload",
                }

            elif w < leader_weeks + 1 + anchor_weeks:
                # Anchor phase
                anchor_offset = w - leader_weeks - 1
                cycle_in_anchor = anchor_offset // 3 + 1
                week_in_cycle = anchor_offset % 3 + 1
                bumps_in_block = block["leader_cycles"] + (anchor_offset // 3)
                return {
                    "phase": "anchor",
                    "block": block,
                    "block_num": block["block"],
                    "cycle_in_phase": cycle_in_anchor,
                    "week_type": week_in_cycle,
                    "week_name": CYCLE_WEEKS[week_in_cycle]["name"],
                    "week_in_block": w + 1,
                    "tm_bumps_total": cumulative_bumps + bumps_in_block,
                    "supplemental_template": block["anchor_template"],
                    "main_work_mode": block["anchor_main_work"],
                }

            else:
                # 7th week TM test (after anchor)
                bumps_in_block = block["leader_cycles"] + block["anchor_cycles"]
                return {
                    "phase": "7th_week_tm_test",
                    "block": block,
                    "block_num": block["block"],
                    "cycle_in_phase": None,
                    "week_type": 4,
                    "week_name": "TM Test (7th Week)",
                    "week_in_block": w + 1,
                    "tm_bumps_total": cumulative_bumps + bumps_in_block,
                    "supplemental_template": "none",
                    "main_work_mode": "tm_test",
                }

        # Move to next block
        # Count all TM bumps in this block
        bumps_this_block = block["leader_cycles"] + block["anchor_cycles"]
        cumulative_bumps += bumps_this_block
        cumulative_weeks += block_total_weeks

    # Past all planned blocks — repeat last block
    last_block = YEARLY_PLAN[-1]
    return {
        "phase": "leader",
        "block": last_block,
        "block_num": last_block["block"],
        "cycle_in_phase": 1,
        "week_type": 1,
        "week_name": "Semana 5s",
        "week_in_block": 1,
        "tm_bumps_total": cumulative_bumps,
        "supplemental_template": last_block["leader_template"],
        "main_work_mode": last_block["leader_main_work"],
    }


def get_supplemental_pct(template_key: str, week_type: int, cycle_in_phase: int = 1,
                          lift: str = None, tm: float = None) -> float | None:
    """
    Get the supplemental percentage of TM for a given template, week, and cycle.

    Returns:
        Float percentage (0.0-1.0), or None if FSL (caller must compute from first working set).
    """
    tmpl = SUPPLEMENTAL_TEMPLATES.get(template_key, {})
    pct_source = tmpl.get("pct_source", "none")

    if pct_source == "none":
        return None
    if pct_source == "fsl":
        return None  # Caller computes from CYCLE_WEEKS first set pct

    if pct_source == "mixed":
        # SVR II etc: check week_spec
        ws = tmpl.get("week_spec", {}).get(week_type, {})
        if ws.get("pct_source") == "fsl":
            return None
        return ws.get("pct", 0.50)

    # fixed_pct
    if "pct_by_cycle" in tmpl:
        cycle_key = min(cycle_in_phase, max(tmpl["pct_by_cycle"].keys()))
        return tmpl["pct_by_cycle"].get(cycle_key, 0.50)

    pct_map = tmpl.get("pct_by_week", {})
    return pct_map.get(week_type, 0.50)


def get_fsl_pct(week_type: int) -> float:
    """Get the First Set Last percentage for a given week type."""
    # FSL = first working set percentage
    week_cfg = CYCLE_WEEKS.get(week_type, CYCLE_WEEKS[1])
    return week_cfg["sets"][0]["pct"]


# ── Day Configuration ────────────────────────────────────────────────
# Maps BBB day number → main lift + metadata
# Day order matches Juan's Hevy routine setup
DAY_CONFIG_531 = {
    1: {
        "name": "BBB Día 1 - OHP",
        "main_lift": "ohp",
        "focus": "Press + Hombros",
        "color": "#f97316",
    },
    2: {
        "name": "BBB Día 2 - Deadlift",
        "main_lift": "deadlift",
        "focus": "Peso Muerto",
        "color": "#ef4444",
    },
    3: {
        "name": "BBB Día 3 - Bench",
        "main_lift": "bench",
        "focus": "Press de Banca",
        "color": "#3b82f6",
    },
    4: {
        "name": "BBB Día 4 - Zercher",
        "main_lift": "squat",
        "focus": "Sentadilla Zercher",
        "color": "#22c55e",
    },
}

# ── Exercise Template IDs (from Hevy) ────────────────────────────────
# Main lifts — these are the 531 working sets
MAIN_LIFT_TIDS = {
    "ohp":      "073032BB",   # Press Militar de Pie (Barra)
    "deadlift": "C6272009",   # Peso Muerto (Barra)
    "bench":    "E644F828",   # Press de Banca - Agarre Abierto (Barra)
    "squat":    "40C6A9FC",   # Zercher Squat (replaces Back Squat D04AC939)
}

# Reverse lookup: template_id → lift name
TID_TO_LIFT = {v: k for k, v in MAIN_LIFT_TIDS.items() if v}

# ── Exercise Database (531 context) ──────────────────────────────────
# All exercises that appear in BBB workouts
EXERCISE_DB_531 = {
    # Main lifts
    "073032BB": {
        "name": "OHP (Barbell)",
        "role": "main",
        "lift": "ohp",
        "muscle_group": "Hombros",
    },
    "C6272009": {
        "name": "Deadlift (Barbell)",
        "role": "main",
        "lift": "deadlift",
        "muscle_group": "Espalda Baja",
    },
    "E644F828": {
        "name": "Bench Press (Barbell)",
        "role": "main",
        "lift": "bench",
        "muscle_group": "Pecho",
    },
    "40C6A9FC": {
        "name": "Zercher Squat",
        "role": "main",
        "lift": "squat",
        "muscle_group": "Piernas",
    },
    "D04AC939": {
        "name": "Squat (Barbell)",
        "role": "historical",  # Replaced by Zercher Squat
        "lift": "squat",
        "muscle_group": "Piernas",
    },
    # Accessories from Day 1
    "0B841777": {
        "name": "Shrug (Barbell)",
        "role": "accessory",
        "muscle_group": "Trapecios",
    },
    "875F585F": {
        "name": "Skullcrusher (Barbell)",
        "role": "accessory",
        "muscle_group": "Tríceps",
    },
    "23A48484": {
        "name": "Cable Crunch",
        "role": "accessory",
        "muscle_group": "Core",
    },
}

# Workouts done without routine_id that should be included
EXCEPTION_WORKOUT_IDS = {
    "edf3607a-8a50-470c-ae79-7d1b739d8c5d",  # BBB Day 1 — 2026-02-20 (first session, logged manually)
    "864e5e48-2e8f-491a-b7a8-a2b79797cf74",  # BBB Day 2 — 2026-02-21 (routine_id mismatch)
}

# ── Routine IDs in BBB folder ────────────────────────────────────────
BBB_ROUTINE_IDS = {
    "619fb49a-7d62-4de5-9567-86e616103b5b",  # BBB día 1 - OHP
    "47a7c25b-fac8-4979-b853-dc7284ca9e80",  # BBB día 2 - Deadlift
    "5bec1b7b-25d8-4c84-be6e-35f915a9a3fc",  # BBB día 3 - Bench
    "331eb58f-e25e-47c0-b375-5e526ceab5e1",  # BBB día 4 - Squat
}

# Ordered map: day_num → routine_id (for updating routines)
DAY_ROUTINE_MAP = {
    1: "619fb49a-7d62-4de5-9567-86e616103b5b",  # OHP
    2: "47a7c25b-fac8-4979-b853-dc7284ca9e80",  # Deadlift
    3: "5bec1b7b-25d8-4c84-be6e-35f915a9a3fc",  # Bench
    4: "331eb58f-e25e-47c0-b375-5e526ceab5e1",  # Squat
}

# Accessory templates per day (kept static, Juan adjusts weights manually)
DAY_ACCESSORIES = {
    1: [  # OHP day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
    ],
    2: [  # DL day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
    ],
    3: [  # Bench day
        {"exercise_template_id": "0B841777", "rest_seconds": 90, "sets": [
            {"type": "normal", "weight_kg": 80, "reps": 10},
            {"type": "normal", "weight_kg": 80, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
    ],
    4: [  # Squat day
        {"exercise_template_id": "23A48484", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
            {"type": "normal", "weight_kg": 60, "reps": 10},
        ]},
        {"exercise_template_id": "875F585F", "rest_seconds": 60, "sets": [
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
            {"type": "normal", "weight_kg": 40, "reps": 10},
        ]},
    ],
}

# ── Strength Standards (Wendler-style, multiples of BW) ──────────────
STRENGTH_STANDARDS_531 = {
    "ohp":      {"beginner": 0.35, "intermediate": 0.65, "advanced": 1.00, "elite": 1.25},
    "deadlift": {"beginner": 1.00, "intermediate": 1.50, "advanced": 2.00, "elite": 2.50},
    "bench":    {"beginner": 0.50, "intermediate": 1.00, "advanced": 1.50, "elite": 2.00},
    "squat":    {"beginner": 0.50, "intermediate": 0.85, "advanced": 1.25, "elite": 1.60},  # Zercher Squat
}


def get_tm(lift: str) -> float | None:
    """Get current Training Max for a lift."""
    return TRAINING_MAX.get(lift)


def round_to_plate(weight: float) -> float:
    """Round weight to nearest 2kg (Juan's smallest increment: 1kg per side)."""
    return round(weight / 2) * 2


def get_session_tm(lift: str, session_date: str, tm_bumps: int = 0) -> float:
    """
    Get the effective Training Max for a lift at a specific session date.

    Looks up TM_HISTORY to find the correct base TM for that date, then
    applies automatic bumps on top:
        effective_tm = base_tm + (tm_bumps - bumps_applied_at_base) × increment

    This is the single source of truth for "what TM was this session
    planned with".  Use this instead of TRAINING_MAX.get() for any
    historical or per-session calculation.

    Args:
        lift: one of "ohp", "deadlift", "bench", "squat"
        session_date: ISO date string "YYYY-MM-DD"
        tm_bumps: total automatic bumps completed at this point in the program

    Returns:
        Effective TM in kg (rounded to plates).
    """
    history = TM_HISTORY.get(lift, [])
    if not history:
        return TRAINING_MAX.get(lift, 0) or 0

    # Find the entry active at session_date (latest entry <= date)
    active = history[0]
    for entry in history:
        if entry["from"] <= session_date:
            active = entry
        else:
            break

    base = active["base_tm"]
    bumps_at_base = active.get("bumps_applied", 0)
    increment = TM_INCREMENT.get(lift, 2)
    extra_bumps = max(0, tm_bumps - bumps_at_base)

    return round_to_plate(base + extra_bumps * increment)


def get_cycle_position(total_sessions: int) -> dict:
    """
    Calculate current position in the Beyond 5/3/1 macro cycle.

    Beyond scheme: 3 working weeks + 3 working weeks + 1 deload = 7-week macro.
    TM bumps after each 3-week mini-cycle (after week 3 and week 6).

    Each 'week' = 4 training sessions (one per main lift).

    Returns:
        week_in_macro: 1-7 (position in 7-week macro)
        week_type: 1, 2, or 3 (maps to 5s, 3s, 531) or 4 (deload)
        mini_cycle: 1 or 2 (which 3-week block we're in, or None for deload)
        macro_num: which macro cycle we're on (1-based)
        tm_bumps_completed: how many TM bumps have occurred
    """
    completed_weeks = total_sessions // 4
    macro_num = (completed_weeks // MACRO_CYCLE_LENGTH) + 1
    week_in_macro = (completed_weeks % MACRO_CYCLE_LENGTH) + 1  # 1-7

    if week_in_macro <= 3:
        # Mini-cycle A
        week_type = week_in_macro  # 1=5s, 2=3s, 3=531
        mini_cycle = 1
    elif week_in_macro <= 6:
        # Mini-cycle B
        week_type = week_in_macro - 3  # 1=5s, 2=3s, 3=531
        mini_cycle = 2
    else:
        # Deload (week 7)
        week_type = 4
        mini_cycle = None

    # TM bumps: one after each completed 3-week block
    # Completed blocks = completed full 3-week sections
    total_completed_blocks = 0
    for m in range(macro_num):
        if m < macro_num - 1:
            total_completed_blocks += 2  # Previous macros contributed 2 blocks each
        else:
            # Current macro
            if week_in_macro > 3:
                total_completed_blocks += 1  # Finished mini-cycle A
            if week_in_macro > 6:
                total_completed_blocks += 1  # Finished mini-cycle B

    return {
        "week_in_macro": week_in_macro,
        "week_type": week_type,
        "week_name": CYCLE_WEEKS.get(week_type, {}).get("name", "?"),
        "mini_cycle": mini_cycle,
        "macro_num": macro_num,
        "tm_bumps_completed": total_completed_blocks,
        "completed_weeks": completed_weeks,
    }


def get_effective_tm(lift: str, tm_bumps: int) -> float:
    """
    Calculate the effective TM for a lift after N bumps.

    Delegates to get_session_tm() with today's date so that TM_HISTORY
    recalibrations are always respected. Use this for forward-looking
    calculations (routine updates, projections). For historical per-session
    TMs, use get_session_tm() directly with the session date.
    """
    from datetime import date
    return get_session_tm(lift, date.today().isoformat(), tm_bumps)


def expected_weights(lift: str, week: int, tm_override: float = None) -> list[dict] | None:
    """
    Get expected working set weights for a lift on a given cycle week.
    Returns list of {weight, reps, pct} or None if TM not set.
    """
    tm = tm_override or get_tm(lift)
    if tm is None:
        return None
    week_config = CYCLE_WEEKS.get(week)
    if not week_config:
        return None
    result = []
    for s in week_config["sets"]:
        result.append({
            "weight": round_to_plate(tm * s["pct"]),
            "reps": s["reps"],
            "pct": s["pct"],
        })
    return result

