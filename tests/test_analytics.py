"""
Tests for BBD + 531 analytics — covers the most fragile/critical functions.
Run: pytest tests/ -v
"""
import pandas as pd
import pytest


# ═══════════════════════════════════════════════════════════════════════
# CONFIG TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestBodyweightSingleSource:
    """Verify BODYWEIGHT is consistent across all modules."""

    def test_config_531_imports_from_config(self):
        from src.config import BODYWEIGHT as bw_config
        from src.config_531 import BODYWEIGHT as bw_531
        assert bw_config == bw_531, "config_531.BODYWEIGHT should be imported from config.py"

    def test_bodyweight_is_positive(self):
        from src.config import BODYWEIGHT
        assert BODYWEIGHT > 0


class TestGetSessionTm:
    """TM_HISTORY resolution — the single source of truth for TMs."""

    def test_base_tm_no_bumps(self):
        from src.config_531 import get_session_tm
        # OHP base TM is 58 from 2026-02-20
        tm = get_session_tm("ohp", "2026-02-20", tm_bumps=0)
        assert tm == 58

    def test_base_tm_with_bumps(self):
        from src.config_531 import get_session_tm
        # OHP: base 58 + 1 bump × 2kg increment = 60
        tm = get_session_tm("ohp", "2026-03-15", tm_bumps=1)
        assert tm == 60

    def test_recalibrated_tm(self):
        from src.config_531 import get_session_tm
        # Bench: recalibrated to 84 on 2026-02-24 with bumps_applied=0
        tm = get_session_tm("bench", "2026-02-25", tm_bumps=0)
        assert tm == 84

    def test_recalibrated_tm_before_date(self):
        from src.config_531 import get_session_tm
        # Bench: before recalibration (2026-02-23), base was 76
        tm = get_session_tm("bench", "2026-02-23", tm_bumps=0)
        assert tm == 76

    def test_effective_tm_uses_session_tm(self):
        """get_effective_tm should delegate to get_session_tm (not use stale TRAINING_MAX)."""
        from src.config_531 import get_effective_tm, get_session_tm
        from datetime import date
        # Both should give same result for today
        effective = get_effective_tm("bench", tm_bumps=0)
        session = get_session_tm("bench", date.today().isoformat(), tm_bumps=0)
        assert effective == session


class TestCyclePosition:
    """Verify cycle/week mapping from session count."""

    def test_first_session(self):
        from src.config_531 import get_cycle_position
        pos = get_cycle_position(0)
        assert pos["week_in_macro"] == 1
        assert pos["week_type"] == 1  # 5s week
        assert pos["mini_cycle"] == 1
        assert pos["macro_num"] == 1
        assert pos["tm_bumps_completed"] == 0

    def test_after_first_week(self):
        from src.config_531 import get_cycle_position
        pos = get_cycle_position(4)  # 4 sessions = 1 week done
        assert pos["week_in_macro"] == 2
        assert pos["week_type"] == 2  # 3s week

    def test_first_tm_bump(self):
        from src.config_531 import get_cycle_position
        pos = get_cycle_position(12)  # 12 sessions = 3 weeks = first mini-cycle done
        assert pos["week_in_macro"] == 4  # First week of mini-cycle B
        assert pos["tm_bumps_completed"] == 1

    def test_second_tm_bump(self):
        from src.config_531 import get_cycle_position
        pos = get_cycle_position(24)  # 24 sessions = 6 weeks = both mini-cycles done
        assert pos["week_in_macro"] == 7  # Deload week
        assert pos["tm_bumps_completed"] == 2

    def test_deload_week(self):
        from src.config_531 import get_cycle_position
        pos = get_cycle_position(24)
        assert pos["week_type"] == 4  # Deload
        assert pos["mini_cycle"] is None


# ═══════════════════════════════════════════════════════════════════════
# BBD ANALYTICS TESTS
# ═══════════════════════════════════════════════════════════════════════

def _make_bbd_df(rows: list[dict]) -> pd.DataFrame:
    """Helper: build a minimal BBD DataFrame from simplified rows."""
    defaults = {
        "hevy_id": "test-001",
        "workout_title": "Día 1",
        "day_num": 1,
        "day_name": "Día 1 - Deadlift",
        "duration_min": 60,
        "description": "",
        "exercise": "Deadlift",
        "exercise_template_id": "C6272009",
        "n_sets": 3,
        "reps_list": [5, 5, 5],
        "reps_str": "5,5,5",
        "total_reps": 15,
        "max_weight": 100.0,
        "max_reps_at_max": 5,
        "volume_kg": 1500,
        "e1rm": 116.7,
        "top_set": "100kg x 5",
        "is_bodyweight": False,
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        row["date"] = pd.Timestamp(row["date"]) if isinstance(row.get("date"), str) else row.get("date", pd.Timestamp("2026-02-12"))
        full_rows.append(row)
    return pd.DataFrame(full_rows)


class TestWeekAssignment:
    """Cycle-aware week assignment in add_derived_columns."""

    def test_sequential_days_same_week(self):
        from src.analytics import add_derived_columns
        df = _make_bbd_df([
            {"date": "2026-02-12", "day_num": 1, "hevy_id": "a"},
            {"date": "2026-02-13", "day_num": 2, "hevy_id": "b"},
            {"date": "2026-02-14", "day_num": 3, "hevy_id": "c"},
        ])
        result = add_derived_columns(df)
        assert (result["week"] == 1).all()

    def test_cycle_reset_increments_week(self):
        from src.analytics import add_derived_columns
        df = _make_bbd_df([
            {"date": "2026-02-12", "day_num": 5, "hevy_id": "a"},
            {"date": "2026-02-13", "day_num": 6, "hevy_id": "b"},
            {"date": "2026-02-14", "day_num": 1, "hevy_id": "c"},  # reset → week 2
        ])
        result = add_derived_columns(df)
        assert result[result["hevy_id"] == "a"]["week"].iloc[0] == 1
        assert result[result["hevy_id"] == "c"]["week"].iloc[0] == 2

    def test_empty_df(self):
        from src.analytics import add_derived_columns
        df = pd.DataFrame()
        result = add_derived_columns(df)
        assert result.empty


class TestPrDetection:
    """PR detection should use template_id, not exercise name."""

    def test_pr_detected_by_template_id(self):
        from src.notion_client import _detect_prs
        existing = _make_bbd_df([
            {"date": "2026-02-12", "hevy_id": "old", "exercise_template_id": "C6272009",
             "exercise": "Peso Muerto (Barra)", "e1rm": 100},
        ])
        new = _make_bbd_df([
            {"date": "2026-02-13", "hevy_id": "new", "exercise_template_id": "C6272009",
             "exercise": "Peso Muerto (Barra)", "e1rm": 110},
        ])
        result = _detect_prs(new, pd.concat([existing, new]))
        assert result["is_pr"].iloc[0] == True

    def test_no_pr_when_lower(self):
        from src.notion_client import _detect_prs
        existing = _make_bbd_df([
            {"date": "2026-02-12", "hevy_id": "old", "exercise_template_id": "C6272009",
             "exercise": "Deadlift", "e1rm": 150},
        ])
        new = _make_bbd_df([
            {"date": "2026-02-13", "hevy_id": "new", "exercise_template_id": "C6272009",
             "exercise": "Deadlift", "e1rm": 140},
        ])
        result = _detect_prs(new, pd.concat([existing, new]))
        assert result["is_pr"].iloc[0] == False

    def test_different_template_ids_independent(self):
        """PRs are per-exercise, not global."""
        from src.notion_client import _detect_prs
        existing = _make_bbd_df([
            {"date": "2026-02-12", "hevy_id": "old", "exercise_template_id": "C6272009",
             "exercise": "Deadlift", "e1rm": 200},
        ])
        new = _make_bbd_df([
            {"date": "2026-02-13", "hevy_id": "new", "exercise_template_id": "073032BB",
             "exercise": "OHP", "e1rm": 50},
        ])
        result = _detect_prs(new, pd.concat([existing, new]))
        assert result["is_pr"].iloc[0] == True  # First OHP ever = PR


# ═══════════════════════════════════════════════════════════════════════
# 531 SET CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestClassifyMainLiftSets:
    """The most critical heuristic — set classification for 531 workouts."""

    def _make_sets(self, weight_reps: list[tuple]) -> list[dict]:
        """Helper: [(weight, reps), ...] → Hevy-style set dicts."""
        return [
            {"weight_kg": w, "reps": r, "type": "normal"}
            for w, r in weight_reps
        ]

    def test_standard_5s_week(self):
        """5s week: warmup + 3 ascending working sets + BBB 5×10."""
        from src.analytics_531 import _classify_main_lift_sets
        # OHP, TM=58: warmup(23,29,35), working(38,44,50 AMRAP), BBB 5×10@29
        sets = self._make_sets([
            (24, 5), (30, 5), (36, 5),     # warmup
            (38, 5), (44, 5), (50, 12),     # working (AMRAP)
            (30, 10), (30, 10), (30, 10), (30, 10), (30, 10),  # BBB
        ])
        result = _classify_main_lift_sets(sets, "ohp", tm_override=58)
        types = [r["type"] for r in result]
        assert types.count("warmup") == 3
        assert types.count("working_531") == 2
        assert types.count("amrap") == 1
        assert types.count("bbb") == 5

    def test_joker_sets_detected(self):
        """After AMRAP, heavier sets should be classified as joker."""
        from src.analytics_531 import _classify_main_lift_sets
        # DL, TM=140: warmup(56,70,84), working(92,106,120×10 AMRAP), joker(130×1, 140×1), BBB
        sets = self._make_sets([
            (56, 5), (70, 5), (84, 5),      # warmup
            (92, 5), (106, 3), (120, 10),    # working (AMRAP with high reps)
            (130, 1), (140, 1),              # joker (heavier than AMRAP)
            (70, 10), (70, 10), (70, 10), (70, 10), (70, 10),  # BBB
        ])
        result = _classify_main_lift_sets(sets, "deadlift", tm_override=140)
        types = [r["type"] for r in result]
        assert "joker" in types, f"Expected joker sets, got: {types}"

    def test_fallback_when_no_tm(self):
        """Without TM, fallback classification still works."""
        from src.analytics_531 import _classify_main_lift_sets_fallback
        parsed = [
            {"weight": 40, "reps": 5, "idx": 0, "hevy_type": "normal"},
            {"weight": 50, "reps": 5, "idx": 1, "hevy_type": "normal"},
            {"weight": 60, "reps": 5, "idx": 2, "hevy_type": "normal"},
            {"weight": 70, "reps": 3, "idx": 3, "hevy_type": "normal"},
            {"weight": 80, "reps": 5, "idx": 4, "hevy_type": "normal"},  # AMRAP
            {"weight": 40, "reps": 10, "idx": 5, "hevy_type": "normal"},
            {"weight": 40, "reps": 10, "idx": 6, "hevy_type": "normal"},
        ]
        result = _classify_main_lift_sets_fallback(parsed)
        types = [r["type"] for r in result]
        assert "amrap" in types
        assert "bbb" in types


# ═══════════════════════════════════════════════════════════════════════
# HEVY CLIENT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestBbdWorkoutDetection:
    """BBD workout title matching."""

    def test_valid_bbd_titles(self):
        from src.hevy_client import is_bbd_workout
        assert is_bbd_workout("Día 1") is True
        assert is_bbd_workout("Día 6 - Press/Pecho") is True
        assert is_bbd_workout("Día 3 Brazos") is True

    def test_reject_non_bbd(self):
        from src.hevy_client import is_bbd_workout
        assert is_bbd_workout("BBB Día 1 - OHP") is False
        assert is_bbd_workout("Random workout") is False
        assert is_bbd_workout("Día 7") is False  # Only 1-6 valid

    def test_reject_dc_rotations(self):
        from src.hevy_client import is_bbd_workout
        assert is_bbd_workout("Día 1 A") is False
        assert is_bbd_workout("Día 2 B") is False


class TestBbbWorkoutDetection:
    """531 BBB workout matching."""

    def test_by_routine_id(self):
        from src.analytics_531 import is_bbb_workout
        from src.config_531 import BBB_ROUTINE_IDS
        rid = list(BBB_ROUTINE_IDS)[0]
        assert is_bbb_workout({"routine_id": rid, "title": "whatever"}) is True

    def test_by_title(self):
        from src.analytics_531 import is_bbb_workout
        assert is_bbb_workout({"title": "BBB Día 1", "id": "x"}) is True

    def test_by_exception_id(self):
        from src.analytics_531 import is_bbb_workout
        from src.config_531 import EXCEPTION_WORKOUT_IDS
        eid = list(EXCEPTION_WORKOUT_IDS)[0]
        assert is_bbb_workout({"title": "random", "id": eid}) is True

    def test_reject_bbd(self):
        from src.analytics_531 import is_bbb_workout
        assert is_bbb_workout({"title": "Día 1", "id": "y"}) is False


# ═══════════════════════════════════════════════════════════════════════
# 531 INTELLIGENCE TESTS (Phase 4)
# ═══════════════════════════════════════════════════════════════════════

def _make_531_df(rows: list[dict]) -> pd.DataFrame:
    """Helper: build a minimal 531 DataFrame with required columns."""
    defaults = {
        "hevy_id": "test-001",
        "exercise": "Overhead Press",
        "exercise_template_id": "073032BB",
        "lift": "ohp",
        "set_type": "amrap",
        "set_number": 6,
        "weight_kg": 50.0,
        "reps": 8,
        "volume_kg": 400.0,
        "e1rm": 63.3,
        "muscle_group": "Hombros",
        "effective_tm": 58.0,
        "week_type": 1,
        "week_name": "5s",
        "mini_cycle": 1,
        "macro_num": 1,
        "week_in_macro": 1,
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        row["date"] = pd.Timestamp(row["date"]) if isinstance(row.get("date"), str) else row.get("date", pd.Timestamp("2026-02-20"))
        full_rows.append(row)
    return pd.DataFrame(full_rows)


class TestAmrapPerformanceIndex:
    """AMRAP Performance Index — same week_type comparison across cycles."""

    def test_single_amrap_no_delta(self):
        from src.analytics_531 import amrap_performance_index
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "week_type": 1, "reps": 10, "e1rm": 66.7},
        ])
        result = amrap_performance_index(df)
        assert len(result) == 1
        assert result.iloc[0]["reps_delta"] is None

    def test_two_cycles_shows_delta(self):
        from src.analytics_531 import amrap_performance_index
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "week_type": 1, "reps": 10, "e1rm": 66.7,
             "mini_cycle": 1, "macro_num": 1, "weight_kg": 50},
            {"date": "2026-03-13", "lift": "ohp", "week_type": 1, "reps": 8, "e1rm": 68.0,
             "mini_cycle": 2, "macro_num": 1, "weight_kg": 52},
        ])
        result = amrap_performance_index(df)
        assert len(result) == 2
        assert result.iloc[1]["reps_delta"] == -2  # 8 - 10
        assert result.iloc[1]["e1rm_delta"] == 1.3  # 68 - 66.7

    def test_ignores_deload_week(self):
        from src.analytics_531 import amrap_performance_index
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "week_type": 4, "reps": 5, "e1rm": 50.0},
        ])
        result = amrap_performance_index(df)
        assert result.empty  # week_type 4 = deload, filtered out


class TestTmSustainability:
    """TM Sustainability — are AMRAPs hitting minimums?"""

    def test_healthy_amraps(self):
        from src.analytics_531 import tm_sustainability
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "week_type": 1, "reps": 10, "e1rm": 66.7},
            {"date": "2026-02-21", "lift": "ohp", "week_type": 2, "reps": 8, "e1rm": 70.0},
            {"date": "2026-02-22", "lift": "ohp", "week_type": 3, "reps": 5, "e1rm": 72.0},
        ])
        result = tm_sustainability(df)
        assert result["lifts"]["ohp"]["verdict"] == "🟢 TM sostenible"
        assert result["system_health"] >= 0.8

    def test_failing_amrap(self):
        from src.analytics_531 import tm_sustainability
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "week_type": 1, "reps": 3, "e1rm": 55.0},
            {"date": "2026-02-21", "lift": "ohp", "week_type": 2, "reps": 1, "e1rm": 58.0},
        ])
        result = tm_sustainability(df)
        assert "🔴" in result["lifts"]["ohp"]["verdict"]


class TestJokerAnalysis:
    """Joker Set Analysis."""

    def test_no_jokers(self):
        from src.analytics_531 import joker_analysis
        df = _make_531_df([
            {"date": "2026-02-20", "set_type": "amrap", "hevy_id": "a"},
        ])
        result = joker_analysis(df)
        assert result["total_joker_sets"] == 0
        assert result["frequency_pct"] == 0

    def test_with_jokers(self):
        from src.analytics_531 import joker_analysis
        df = _make_531_df([
            {"date": "2026-02-20", "set_type": "amrap", "hevy_id": "a", "lift": "ohp"},
            {"date": "2026-02-20", "set_type": "joker", "hevy_id": "a", "lift": "ohp",
             "weight_kg": 60, "e1rm": 60, "effective_tm": 58},
        ])
        result = joker_analysis(df)
        assert result["total_joker_sets"] == 1
        assert result["sessions_with_jokers"] == 1
        assert "ohp" in result["per_lift"]


class TestBbbFatigueTrend:
    """BBB Fatigue — rep drop-off in 5×10 sets."""

    def test_perfect_fives(self):
        from src.analytics_531 import bbb_fatigue_trend
        df = _make_531_df([
            {"date": "2026-02-20", "set_type": "bbb", "hevy_id": "a", "lift": "ohp",
             "set_number": i, "reps": 10, "weight_kg": 30, "volume_kg": 300,
             "effective_tm": 58, "macro_num": 1}
            for i in range(1, 6)
        ])
        result = bbb_fatigue_trend(df)
        assert len(result) == 1
        assert result.iloc[0]["all_tens"] == True
        assert result.iloc[0]["rep_dropoff"] == 0.0
        assert result.iloc[0]["fatigue_status"] == "🟢 Sin fatiga"

    def test_fatigued_sets(self):
        from src.analytics_531 import bbb_fatigue_trend
        reps = [10, 10, 9, 8, 7]
        df = _make_531_df([
            {"date": "2026-02-20", "set_type": "bbb", "hevy_id": "a", "lift": "ohp",
             "set_number": i + 1, "reps": reps[i], "weight_kg": 30, "volume_kg": 30 * reps[i],
             "effective_tm": 58, "macro_num": 1}
            for i in range(5)
        ])
        result = bbb_fatigue_trend(df)
        assert result.iloc[0]["rep_dropoff"] > 0
        assert result.iloc[0]["all_tens"] == False


class TestTrue1rmTrend:
    """True 1RM estimation from AMRAP performance."""

    def test_basic_trend(self):
        from src.analytics_531 import true_1rm_trend
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "set_type": "amrap",
             "weight_kg": 50, "reps": 10, "e1rm": 66.7, "effective_tm": 58},
            {"date": "2026-03-13", "lift": "ohp", "set_type": "amrap",
             "weight_kg": 52, "reps": 8, "e1rm": 65.9, "effective_tm": 60},
        ])
        result = true_1rm_trend(df)
        assert len(result) == 2
        assert "running_max" in result.columns
        assert result.iloc[0]["running_max"] == 66.7
        assert result.iloc[1]["running_max"] == 66.7  # Running max stays

    def test_tm_as_pct(self):
        from src.analytics_531 import true_1rm_trend
        df = _make_531_df([
            {"date": "2026-02-20", "lift": "ohp", "set_type": "amrap",
             "weight_kg": 50, "reps": 10, "e1rm": 66.7, "effective_tm": 58},
        ])
        result = true_1rm_trend(df)
        # TM 58 / e1RM 66.7 ≈ 86.9%
        assert 85 < result.iloc[0]["tm_as_pct_of_1rm"] < 90


# ═══════════════════════════════════════════════════════════════════════
# SHARED ANALYTICS TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestDetectUnknownExercises:
    """Auto-detect exercise substitutions."""

    def test_all_known(self):
        from src.shared_analytics import detect_unknown_exercises
        db = {"AAA": {"name": "Curl"}, "BBB": {"name": "Press"}}
        df = pd.DataFrame([
            {"exercise_template_id": "AAA", "exercise": "Curl", "date": pd.Timestamp("2026-02-20"), "hevy_id": "x"},
        ])
        result = detect_unknown_exercises(df, db)
        assert result.empty

    def test_unknown_detected(self):
        from src.shared_analytics import detect_unknown_exercises
        db = {"AAA": {"name": "Curl"}}
        df = pd.DataFrame([
            {"exercise_template_id": "AAA", "exercise": "Curl", "date": pd.Timestamp("2026-02-20"), "hevy_id": "x"},
            {"exercise_template_id": "ZZZ", "exercise": "Remo con Barra", "date": pd.Timestamp("2026-02-20"), "hevy_id": "x"},
            {"exercise_template_id": "ZZZ", "exercise": "Remo con Barra", "date": pd.Timestamp("2026-02-21"), "hevy_id": "y"},
        ])
        result = detect_unknown_exercises(df, db)
        assert len(result) == 1
        assert result.iloc[0]["template_id"] == "ZZZ"
        assert result.iloc[0]["session_count"] == 2
        assert result.iloc[0]["suggested_muscle_group"] == "Espalda"  # "remo"

    def test_muscle_group_guessing(self):
        from src.shared_analytics import detect_unknown_exercises
        df = pd.DataFrame([
            {"exercise_template_id": "X1", "exercise": "Curl de Bíceps", "date": pd.Timestamp("2026-02-20"), "hevy_id": "a"},
            {"exercise_template_id": "X2", "exercise": "Sentadilla Búlgara", "date": pd.Timestamp("2026-02-20"), "hevy_id": "a"},
        ])
        result = detect_unknown_exercises(df, {})
        mg_map = dict(zip(result["template_id"], result["suggested_muscle_group"]))
        assert mg_map["X1"] == "Bíceps"
        assert mg_map["X2"] == "Piernas"


class TestWorkoutQuality531:
    """531 quality score."""

    def test_perfect_session(self):
        from src.shared_analytics import workout_quality_531
        df = _make_531_df([
            # AMRAP: 10 reps on 5s week (min 5) → 20 + 5*4 = 40
            {"date": "2026-02-20", "set_type": "amrap", "hevy_id": "a", "lift": "ohp",
             "reps": 10, "e1rm": 66.7, "weight_kg": 50, "volume_kg": 500,
             "exercise": "OHP", "is_main_lift": True, "week_in_cycle": 1},
            # 5 BBB sets of 10 → 30
            *[{"date": "2026-02-20", "set_type": "bbb", "hevy_id": "a", "lift": "ohp",
               "reps": 10, "e1rm": 40, "weight_kg": 30, "volume_kg": 300,
               "exercise": "OHP", "is_main_lift": True, "set_number": i, "week_in_cycle": 1}
              for i in range(5)],
            # 2 accessories
            {"date": "2026-02-20", "set_type": "accessory", "hevy_id": "a", "lift": "ohp",
             "reps": 12, "e1rm": 20, "weight_kg": 15, "volume_kg": 180,
             "exercise": "Lateral Raise", "is_main_lift": False, "week_in_cycle": 1},
            {"date": "2026-02-20", "set_type": "accessory", "hevy_id": "a", "lift": "ohp",
             "reps": 15, "e1rm": 25, "weight_kg": 20, "volume_kg": 300,
             "exercise": "Face Pull", "is_main_lift": False, "week_in_cycle": 1},
        ])
        result = workout_quality_531(df)
        assert len(result) == 1
        assert result.iloc[0]["quality_score"] >= 80  # High score
        assert result.iloc[0]["grade"] in ("S", "A")

    def test_grade_mapping(self):
        from src.shared_analytics import _grade
        assert _grade(95) == "S"
        assert _grade(82) == "A"
        assert _grade(70) == "B"
        assert _grade(50) == "C"
        assert _grade(20) == "F"


class TestWorkoutCard:
    """Workout card generation."""

    def test_card_builds_data_531(self):
        from src.shared_analytics import build_card_data_531
        df = _make_531_df([
            {"date": "2026-02-20", "set_type": "amrap", "hevy_id": "sess1", "lift": "ohp",
             "reps": 8, "e1rm": 63.3, "weight_kg": 50, "volume_kg": 400,
             "exercise": "OHP", "is_main_lift": True, "workout_title": "BBB Día 1"},
            {"date": "2026-02-20", "set_type": "bbb", "hevy_id": "sess1", "lift": "ohp",
             "reps": 10, "e1rm": 40, "weight_kg": 30, "volume_kg": 300,
             "exercise": "OHP", "is_main_lift": True, "workout_title": "BBB Día 1"},
        ])
        card = build_card_data_531(df, "sess1")
        assert card is not None
        assert card["amrap_reps"] == 8
        assert card["amrap_weight"] == 50
        assert "Volumen" in card["stats"]

    def test_card_returns_none_for_missing(self):
        from src.shared_analytics import build_card_data_531
        df = _make_531_df([
            {"date": "2026-02-20", "hevy_id": "sess1"},
        ])
        card = build_card_data_531(df, "nonexistent")
        assert card is None

    def test_png_generation(self):
        from src.shared_analytics import generate_workout_card
        card_data = {
            "date": pd.Timestamp("2026-02-20"),
            "title": "BBB Día 1",
            "lift": "ohp",
            "amrap_weight": 50,
            "amrap_reps": 8,
            "amrap_e1rm": 63.3,
            "bbb_sets": 5,
            "bbb_weight": 30,
            "bbb_avg_reps": 10,
            "stats": {"Volumen": "1,200kg", "Sets": "12", "Ejercicios": "4"},
            "quality_score": 85,
            "grade": "A",
        }
        try:
            png = generate_workout_card(card_data, program="531")
            assert isinstance(png, bytes)
            assert len(png) > 1000  # Should be a real image
            assert png[:4] == b'\x89PNG'  # PNG magic bytes
        except ImportError:
            pass  # Pillow not installed in test env

