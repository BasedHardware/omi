"""Tests for the UserPrefs + TaskWeights dataclasses (T-301)."""

import dataclasses
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
# Frozen immutability (cubic review fix)
# ---------------------------------------------------------------------------


class TestUserPrefsFrozenDict:
    """Cubic review caught that UserPrefs stored a mutable dict inside a
    frozen dataclass. __post_init__ now wraps the dict in MappingProxyType
    so external mutations raise TypeError instead of silently bypassing
    __post_init__ validation."""

    def test_mutating_overrides_dict_raises_type_error(self):
        weights = TaskWeights(0.4, 0.5, 0.1)
        prefs = UserPrefs(overrides={"ptt_response": weights})
        # Attempting to add a new entry raises TypeError (read-only view).
        with pytest.raises(TypeError):
            prefs.overrides["new_task"] = weights

    def test_mutating_existing_entry_raises_type_error(self):
        original = TaskWeights(0.4, 0.5, 0.1)
        prefs = UserPrefs(overrides={"ptt_response": original})
        # Attempting to replace an existing value raises TypeError.
        with pytest.raises(TypeError):
            prefs.overrides["ptt_response"] = TaskWeights(1.0, 0.0, 0.0)

    def test_overrides_iteration_still_works(self):
        # MappingProxyType is iterable + supports .items() — used by to_dict().
        weights = TaskWeights(0.4, 0.5, 0.1)
        prefs = UserPrefs(overrides={"ptt_response": weights, "transcription": weights})
        items = list(prefs.overrides.items())
        assert len(items) == 2
        assert prefs.overrides["ptt_response"] == weights

    def test_reassignment_of_field_still_raises_frozen_error(self):
        # The dataclass being frozen also prevents reassigning self.overrides.
        prefs = UserPrefs()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            prefs.overrides = {}

    def test_empty_prefs_overrides_is_empty_mapping(self):
        # MappingProxyType({}) is falsy + len 0.
        prefs = UserPrefs()
        assert len(prefs.overrides) == 0
        assert not prefs.overrides  # bool check


# ---------------------------------------------------------------------------
# from_dict schema validation (cubic review fix)
# ---------------------------------------------------------------------------


class TestUserPrefsFromDictSchema:
    """Cubic review caught that from_dict didn't defensively check the
    input shape/required keys, leading to uncaught AttributeError /
    KeyError on malformed data. Now we raise clear ValueErrors."""

    def test_from_dict_rejects_non_dict_input(self):
        with pytest.raises(ValueError, match="expects a dict"):
            UserPrefs.from_dict("not a dict")  # type: ignore[arg-type]

    def test_from_dict_rejects_none_entry(self):
        with pytest.raises(ValueError, match="must be a dict"):
            UserPrefs.from_dict({"ptt_response": None})  # type: ignore[dict-item]

    def test_from_dict_rejects_missing_required_key(self):
        # Missing 'cost' key.
        with pytest.raises(ValueError, match="missing required key"):
            UserPrefs.from_dict({"ptt_response": {"quality": 0.4, "latency": 0.5}})  # no 'cost'

    def test_from_dict_rejects_empty_task_name(self):
        with pytest.raises(ValueError, match="non-empty string"):
            UserPrefs.from_dict({"": {"quality": 0.4, "latency": 0.5, "cost": 0.1}})

    def test_from_dict_rejects_non_string_task_name(self):
        with pytest.raises(ValueError, match="non-empty string"):
            UserPrefs.from_dict({123: {"quality": 0.4, "latency": 0.5, "cost": 0.1}})  # type: ignore[dict-item]

    def test_from_dict_with_valid_data_still_works(self):
        # Regression: ensure the strict checks don't break the happy path.
        prefs = UserPrefs.from_dict({"ptt_response": {"quality": 0.4, "latency": 0.5, "cost": 0.1}})
        assert prefs.overrides["ptt_response"] == TaskWeights(0.4, 0.5, 0.1)

    def test_from_dict_rejects_invalid_weight_in_field(self):
        # Quality value out of range — raises during TaskWeights construction.
        with pytest.raises(ValueError):
            UserPrefs.from_dict({"ptt_response": {"quality": 1.5, "latency": 0.0, "cost": -0.5}})


# ---------------------------------------------------------------------------
# Shared validation helpers (cubic review fix)
# ---------------------------------------------------------------------------


class TestSharedWeightValidation:
    """The per-axis validation logic was duplicated between TaskWeights
    and TaskSpec. Now it's in user_prefs._validate_weight +
    _validate_weights_sum_to_one. These tests verify the helpers work
    correctly in isolation."""

    def test_validate_weight_accepts_valid_floats(self):
        from utils.auto_router.user_prefs import _validate_weight

        assert _validate_weight(0.5, "test") == 0.5
        assert _validate_weight(0, "test") == 0.0
        assert _validate_weight(1, "test") == 1.0

    def test_validate_weight_rejects_bool(self):
        from utils.auto_router.user_prefs import _validate_weight

        with pytest.raises(TypeError, match="must be a number, got bool"):
            _validate_weight(True, "test")

    def test_validate_weight_rejects_string(self):
        from utils.auto_router.user_prefs import _validate_weight

        with pytest.raises(TypeError, match="must be a number"):
            _validate_weight("0.5", "test")  # type: ignore[arg-type]

    def test_validate_weight_rejects_nan(self):
        from utils.auto_router.user_prefs import _validate_weight

        with pytest.raises(ValueError, match="finite"):
            _validate_weight(float("nan"), "test")

    def test_validate_weight_rejects_out_of_range(self):
        from utils.auto_router.user_prefs import _validate_weight

        with pytest.raises(ValueError, match="must be in"):
            _validate_weight(1.5, "test")
        with pytest.raises(ValueError, match="must be in"):
            _validate_weight(-0.1, "test")

    def test_validate_weights_sum_to_one_within_tolerance(self):
        from utils.auto_router.user_prefs import _validate_weights_sum_to_one

        # Should not raise — within 1e-3 tolerance.
        _validate_weights_sum_to_one(0.4, 0.5, 0.1, "test")
        _validate_weights_sum_to_one(0.34, 0.33, 0.33, "test")  # 1.00

    def test_validate_weights_sum_to_one_out_of_tolerance(self):
        from utils.auto_router.user_prefs import _validate_weights_sum_to_one

        with pytest.raises(ValueError, match="sum to"):
            _validate_weights_sum_to_one(0.5, 0.5, 0.5, "test")  # sum 1.5
        with pytest.raises(ValueError, match="sum to"):
            _validate_weights_sum_to_one(0.0, 0.0, 0.0, "test")  # sum 0.0

    def test_weight_sum_tolerance_constant(self):
        # The tolerance is exposed as a module constant for downstream use.
        from utils.auto_router.user_prefs import WEIGHT_SUM_TOLERANCE

        assert WEIGHT_SUM_TOLERANCE == 1e-3
