"""Tests for the UserPrefs + TaskWeights dataclasses (T-301)."""

import pytest

from utils.auto_router.user_prefs import TaskWeights, UserPrefs

# ---------------------------------------------------------------------------
# TaskWeights validation (mirrors TaskSpec contract)
# ---------------------------------------------------------------------------


class TestTaskWeightsValidation:
    """TaskWeights validates the same way as TaskSpec weights."""

    def test_balanced_weights_accepted(self):
        w = TaskWeights(quality=0.4, latency=0.4, cost=0.2)
        assert w.quality == 0.4
        assert w.latency == 0.4
        assert w.cost == 0.2

    def test_extreme_weights_accepted(self):
        # All quality, no latency/cost — valid even if "weird"
        w = TaskWeights(quality=1.0, latency=0.0, cost=0.0)
        assert w.quality == 1.0

    def test_weights_must_sum_to_one_within_tolerance(self):
        # 1e-4 is well within the 1e-3 tolerance
        w = TaskWeights(quality=0.333, latency=0.333, cost=0.334)
        assert w.quality == 0.333

    def test_weights_summing_to_far_off_rejected(self):
        with pytest.raises(ValueError, match=r"expected 1\.0"):
            TaskWeights(quality=0.5, latency=0.5, cost=0.5)  # sums to 1.5

    def test_negative_weight_rejected(self):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            TaskWeights(quality=-0.1, latency=0.6, cost=0.5)

    def test_weight_above_one_rejected(self):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            TaskWeights(quality=1.5, latency=-0.2, cost=-0.3)

    def test_nan_weight_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            TaskWeights(quality=float("nan"), latency=0.5, cost=0.5)

    def test_positive_infinity_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            TaskWeights(quality=float("inf"), latency=0.0, cost=0.0)

    def test_bool_weight_rejected(self):
        # bool is a subclass of int in Python; reject before the int check
        with pytest.raises(TypeError, match="must be a number, got bool"):
            TaskWeights(quality=True, latency=False, cost=False)  # sum = 1.0 but bools

    def test_string_weight_rejected(self):
        with pytest.raises(TypeError, match="must be a number"):
            TaskWeights(quality="0.5", latency=0.5, cost=0.0)

    def test_as_dict(self):
        w = TaskWeights(quality=0.4, latency=0.4, cost=0.2)
        assert w.as_dict() == {"quality": 0.4, "latency": 0.4, "cost": 0.2}

    def test_frozen(self):
        w = TaskWeights(quality=0.4, latency=0.4, cost=0.2)
        with pytest.raises(Exception):  # FrozenInstanceError
            w.quality = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UserPrefs construction + from_dict / to_dict
# ---------------------------------------------------------------------------


class TestUserPrefsConstruction:
    def test_empty(self):
        p = UserPrefs.empty()
        assert p.overrides == {}

    def test_empty_from_dict_none(self):
        p = UserPrefs.from_dict(None)
        assert p.overrides == {}

    def test_empty_from_dict_empty(self):
        p = UserPrefs.from_dict({})
        assert p.overrides == {}

    def test_single_override(self):
        p = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        assert "ptt_response" in p.overrides
        assert p.overrides["ptt_response"].quality == 0.2

    def test_multiple_overrides(self):
        p = UserPrefs(
            overrides={
                "ptt_response": TaskWeights(0.2, 0.7, 0.1),
                "screenshot_understanding": TaskWeights(0.9, 0.05, 0.05),
            }
        )
        assert len(p.overrides) == 2

    def test_empty_task_name_rejected(self):
        with pytest.raises(ValueError, match="non-empty string"):
            UserPrefs(overrides={"": TaskWeights(0.4, 0.4, 0.2)})

    def test_non_string_task_name_rejected(self):
        # Pass a non-string key directly to exercise the type check.
        with pytest.raises(ValueError, match="non-empty string"):
            UserPrefs(overrides={123: TaskWeights(0.4, 0.4, 0.2)})  # type: ignore[dict-item]

    def test_non_taskweights_value_rejected(self):
        with pytest.raises(TypeError, match="must be a TaskWeights"):
            UserPrefs(overrides={"ptt_response": {"quality": 0.4}})  # type: ignore[dict-item]

    def test_frozen(self):
        p = UserPrefs.empty()
        with pytest.raises(Exception):  # FrozenInstanceError
            p.overrides = {"ptt_response": TaskWeights(0.4, 0.4, 0.2)}  # type: ignore[misc]


class TestUserPrefsSerialization:
    def test_to_dict_empty(self):
        assert UserPrefs.empty().to_dict() == {}

    def test_to_dict_single(self):
        p = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        assert p.to_dict() == {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}}

    def test_to_dict_multiple(self):
        p = UserPrefs(
            overrides={
                "ptt_response": TaskWeights(0.2, 0.7, 0.1),
                "screenshot_understanding": TaskWeights(0.9, 0.05, 0.05),
            }
        )
        out = p.to_dict()
        assert out["ptt_response"] == {"quality": 0.2, "latency": 0.7, "cost": 0.1}
        assert out["screenshot_understanding"] == {"quality": 0.9, "latency": 0.05, "cost": 0.05}

    def test_from_dict_roundtrip(self):
        original = {
            "ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1},
            "screenshot_understanding": {"quality": 0.9, "latency": 0.05, "cost": 0.05},
        }
        p = UserPrefs.from_dict(original)
        assert p.to_dict() == original

    def test_from_dict_rejects_invalid_weights(self):
        # Sum not 1.0 — should raise (TaskWeights validation runs on construction)
        with pytest.raises(ValueError, match=r"expected 1\.0"):
            UserPrefs.from_dict({"ptt_response": {"quality": 0.5, "latency": 0.5, "cost": 0.5}})

    def test_from_dict_rejects_non_dict_value(self):
        with pytest.raises(ValueError, match="must be a dict"):
            UserPrefs.from_dict({"ptt_response": "not a dict"})  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# UserPrefs.merged_with (the core composition logic)
# ---------------------------------------------------------------------------


class TestUserPrefsMerging:
    def test_empty_merged_returns_defaults(self):
        defaults = {"ptt_response": TaskWeights(0.4, 0.4, 0.2)}
        result = UserPrefs.empty().merged_with(defaults)
        assert result == defaults

    def test_override_replaces_default_for_that_task(self):
        defaults = {"ptt_response": TaskWeights(0.4, 0.4, 0.2)}
        override = TaskWeights(0.2, 0.7, 0.1)
        prefs = UserPrefs(overrides={"ptt_response": override})
        result = prefs.merged_with(defaults)
        assert result["ptt_response"] == override

    def test_override_for_one_task_does_not_affect_another(self):
        defaults = {
            "ptt_response": TaskWeights(0.4, 0.4, 0.2),
            "transcription": TaskWeights(0.3, 0.6, 0.1),
        }
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        result = prefs.merged_with(defaults)
        # Override applied:
        assert result["ptt_response"] == TaskWeights(0.2, 0.7, 0.1)
        # Other task unchanged:
        assert result["transcription"] == TaskWeights(0.3, 0.6, 0.1)

    def test_override_for_unknown_task_preserved(self):
        # If a user sets prefs for a task the system doesn't know about,
        # the override is preserved (callers validate task names elsewhere).
        defaults = {"ptt_response": TaskWeights(0.4, 0.4, 0.2)}
        prefs = UserPrefs(overrides={"future_task": TaskWeights(0.4, 0.4, 0.2)})
        result = prefs.merged_with(defaults)
        assert "future_task" in result
        assert result["ptt_response"] == TaskWeights(0.4, 0.4, 0.2)

    def test_merged_result_is_independent_of_inputs(self):
        # Modifying the result must not affect the UserPrefs or defaults.
        defaults = {"ptt_response": TaskWeights(0.4, 0.4, 0.2)}
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        result = prefs.merged_with(defaults)
        result["ptt_response"] = TaskWeights(1.0, 0.0, 0.0)  # type: ignore[index]
        # Original prefs unchanged:
        assert prefs.overrides["ptt_response"] == TaskWeights(0.2, 0.7, 0.1)


# ---------------------------------------------------------------------------
# UserPrefsStore (added in same module but tested separately)
# ---------------------------------------------------------------------------


class TestUserPrefsStore:
    """Smoke tests for UserPrefsStore — full coverage lives in the endpoint tests."""

    def test_get_missing_returns_empty_prefs(self):
        from utils.auto_router.user_prefs_store import UserPrefsStore

        store = UserPrefsStore()
        result = store.get("missing-uid")
        assert result.prefs.overrides == {}
        assert result.updated_at == 0.0

    def test_set_then_get(self):
        from utils.auto_router.user_prefs_store import UserPrefsStore

        store = UserPrefsStore()
        prefs = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        store.set("uid-1", prefs)
        result = store.get("uid-1")
        assert result.prefs == prefs
        assert result.updated_at > 0.0

    def test_set_replaces_existing(self):
        from utils.auto_router.user_prefs_store import UserPrefsStore

        store = UserPrefsStore()
        store.set("uid-1", UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)}))
        store.set("uid-1", UserPrefs(overrides={"b": TaskWeights(0.4, 0.4, 0.2)}))
        result = store.get("uid-1")
        assert "a" not in result.prefs.overrides
        assert "b" in result.prefs.overrides

    def test_clear_removes_entry(self):
        from utils.auto_router.user_prefs_store import UserPrefsStore

        store = UserPrefsStore()
        store.set("uid-1", UserPrefs(overrides={"a": TaskWeights(0.4, 0.4, 0.2)}))
        store.clear("uid-1")
        result = store.get("uid-1")
        assert result.prefs.overrides == {}

    def test_clear_missing_is_noop(self):
        from utils.auto_router.user_prefs_store import UserPrefsStore

        store = UserPrefsStore()
        store.clear("never-existed")  # must not raise


class TestUserPrefsBoolBypass:
    """from_dict should reject booleans explicitly (cubic P2 fix)."""

    def test_from_dict_rejects_bool_quality(self):
        """float(True) == 1.0 would silently accept booleans as weights."""
        with pytest.raises(ValueError, match=r"got bool"):
            UserPrefs.from_dict({"ptt_response": {"quality": True, "latency": 0.5, "cost": 0.4}})

    def test_from_dict_rejects_bool_latency(self):
        with pytest.raises(ValueError, match=r"got bool"):
            UserPrefs.from_dict({"ptt_response": {"quality": 0.5, "latency": False, "cost": 0.5}})

    def test_from_dict_rejects_bool_cost(self):
        with pytest.raises(ValueError, match=r"got bool"):
            UserPrefs.from_dict({"ptt_response": {"quality": 0.5, "latency": 0.5, "cost": False}})

    def test_from_dict_rejects_string_weight(self):
        with pytest.raises(ValueError, match=r"got str"):
            UserPrefs.from_dict({"ptt_response": {"quality": "0.5", "latency": 0.5, "cost": 0.0}})

    def test_from_dict_rejects_none_weight(self):
        with pytest.raises(ValueError, match=r"got NoneType"):
            UserPrefs.from_dict({"ptt_response": {"quality": None, "latency": 0.5, "cost": 0.5}})

    def test_from_dict_rejects_nan_weight(self):
        with pytest.raises(ValueError, match=r"finite"):
            UserPrefs.from_dict({"ptt_response": {"quality": float("nan"), "latency": 0.5, "cost": 0.5}})
