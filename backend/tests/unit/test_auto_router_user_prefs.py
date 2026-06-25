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
        # v6: nested format with both overrides and model_overrides keys.
        assert UserPrefs.empty().to_dict() == {"overrides": {}, "model_overrides": {}}

    def test_to_dict_single(self):
        p = UserPrefs(overrides={"ptt_response": TaskWeights(0.2, 0.7, 0.1)})
        assert p.to_dict() == {
            "overrides": {"ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1}},
            "model_overrides": {},
        }

    def test_to_dict_multiple(self):
        p = UserPrefs(
            overrides={
                "ptt_response": TaskWeights(0.2, 0.7, 0.1),
                "screenshot_understanding": TaskWeights(0.9, 0.05, 0.05),
            }
        )
        out = p.to_dict()
        assert out["overrides"]["ptt_response"] == {"quality": 0.2, "latency": 0.7, "cost": 0.1}
        assert out["overrides"]["screenshot_understanding"] == {"quality": 0.9, "latency": 0.05, "cost": 0.05}
        assert out["model_overrides"] == {}

    def test_from_dict_roundtrip(self):
        # Legacy format input (top-level IS the overrides dict, v3 wire format).
        # Roundtrip via the new nested format.
        original = {
            "ptt_response": {"quality": 0.2, "latency": 0.7, "cost": 0.1},
            "screenshot_understanding": {"quality": 0.9, "latency": 0.05, "cost": 0.05},
        }
        p = UserPrefs.from_dict(original)
        assert p.to_dict() == {
            "overrides": original,
            "model_overrides": {},
        }

    def test_from_dict_accepts_new_nested_format(self):
        # v6 wire format: {"overrides": {...}, "model_overrides": {...}}
        data = {
            "overrides": {"ptt_response": {"quality": 0.4, "latency": 0.5, "cost": 0.1}},
            "model_overrides": {"ptt_response": "gpt-realtime-2"},
        }
        p = UserPrefs.from_dict(data)
        assert p.overrides["ptt_response"] == TaskWeights(0.4, 0.5, 0.1)
        assert p.model_overrides == {"ptt_response": "gpt-realtime-2"}

    def test_from_dict_accepts_partial_new_format(self):
        # Only overrides key — model_overrides defaults to empty.
        data = {"overrides": {"ptt_response": {"quality": 0.4, "latency": 0.5, "cost": 0.1}}}
        p = UserPrefs.from_dict(data)
        assert p.overrides["ptt_response"] == TaskWeights(0.4, 0.5, 0.1)
        assert p.model_overrides == {}

        # Only model_overrides key — overrides defaults to empty.
        data = {"model_overrides": {"ptt_response": "whisper"}}
        p = UserPrefs.from_dict(data)
        assert p.overrides == {}
        assert p.model_overrides == {"ptt_response": "whisper"}

    def test_from_dict_rejects_non_dict_overrides_value(self):
        with pytest.raises(ValueError, match="'overrides' must be a dict"):
            UserPrefs.from_dict({"overrides": "not a dict"})

    def test_from_dict_rejects_non_dict_model_overrides_value(self):
        with pytest.raises(ValueError, match="'model_overrides' must be a dict"):
            UserPrefs.from_dict({"model_overrides": "not a dict"})

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

    def test_from_dict_rejects_nan_weight(self):
        with pytest.raises(ValueError, match=r"finite"):
            UserPrefs.from_dict({"ptt_response": {"quality": float("nan"), "latency": 0.5, "cost": 0.5}})


# ---------------------------------------------------------------------------
# UserPrefs.model_overrides (v6) — per-task model pinning
# ---------------------------------------------------------------------------


class TestModelOverrides:
    """v6: per-task model pinning lets users lock the auto-router to a
    specific model for a specific task (instead of trusting the pick)."""

    def test_default_empty(self):
        # New field defaults to empty (backward-compat with v3/v4 callers).
        assert UserPrefs().model_overrides == {}
        assert UserPrefs.empty().model_overrides == {}

    def test_construction_with_model_overrides(self):
        p = UserPrefs(model_overrides={"ptt_response": "gpt-realtime-2"})
        assert p.model_overrides == {"ptt_response": "gpt-realtime-2"}

    def test_construction_with_both_overrides_and_model_overrides(self):
        p = UserPrefs(
            overrides={"ptt_response": TaskWeights(0.4, 0.5, 0.1)},
            model_overrides={"ptt_response": "gpt-realtime-2"},
        )
        assert p.overrides["ptt_response"] == TaskWeights(0.4, 0.5, 0.1)
        assert p.model_overrides == {"ptt_response": "gpt-realtime-2"}

    def test_construction_rejects_empty_task_name(self):
        with pytest.raises(ValueError, match="model_override key must be a non-empty string"):
            UserPrefs(model_overrides={"": "whisper"})

    def test_construction_rejects_non_string_task_name(self):
        with pytest.raises(ValueError, match="model_override key must be a non-empty string"):
            UserPrefs(model_overrides={123: "whisper"})  # type: ignore[dict-item]

    def test_construction_rejects_empty_model_id(self):
        with pytest.raises(ValueError, match="model_override for .* must be a non-empty string"):
            UserPrefs(model_overrides={"ptt_response": ""})

    def test_construction_rejects_non_string_model_id(self):
        with pytest.raises(ValueError, match="model_override for .* must be a non-empty string"):
            UserPrefs(model_overrides={"ptt_response": 123})  # type: ignore[dict-item]

    def test_to_dict_includes_model_overrides(self):
        p = UserPrefs(model_overrides={"ptt_response": "gpt-realtime-2"})
        d = p.to_dict()
        assert d["model_overrides"] == {"ptt_response": "gpt-realtime-2"}

    def test_to_dict_empty_model_overrides_serializes_as_empty(self):
        # Even when empty, model_overrides appears in the dict for forward-compat
        # (clients that know about model_overrides can rely on the key existing).
        d = UserPrefs.empty().to_dict()
        assert "model_overrides" in d
        assert d["model_overrides"] == {}

    def test_from_dict_parses_model_overrides(self):
        data = {
            "overrides": {},
            "model_overrides": {
                "ptt_response": "gpt-realtime-2",
                "transcription": "assemblyai-universal",
            },
        }
        p = UserPrefs.from_dict(data)
        assert p.model_overrides == {
            "ptt_response": "gpt-realtime-2",
            "transcription": "assemblyai-universal",
        }

    def test_roundtrip_with_both_fields(self):
        original = UserPrefs(
            overrides={"ptt_response": TaskWeights(0.4, 0.5, 0.1)},
            model_overrides={"ptt_response": "gpt-realtime-2"},
        )
        restored = UserPrefs.from_dict(original.to_dict())
        assert restored == original

    def test_equality_includes_model_overrides(self):
        # Two UserPrefs with same overrides but different model_overrides are NOT equal.
        a = UserPrefs(model_overrides={"ptt_response": "gpt-realtime-2"})
        b = UserPrefs(model_overrides={"ptt_response": "claude-haiku"})
        assert a != b

    def test_equality_with_empty_model_overrides(self):
        # A UserPrefs with no model_overrides equals one with empty model_overrides.
        a = UserPrefs(overrides={"ptt_response": TaskWeights(0.4, 0.5, 0.1)})
        b = UserPrefs(
            overrides={"ptt_response": TaskWeights(0.4, 0.5, 0.1)},
            model_overrides={},
        )
        assert a == b
