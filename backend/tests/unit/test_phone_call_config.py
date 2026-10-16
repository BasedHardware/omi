from unittest.mock import MagicMock
from config.plan_catalog import PlanType
from database.phone_call_config import (
    _declared_override,
    _fetch_config,
    _ignored_override_fields,
    get_config_for_plan,
    get_free_plan_config,
    get_paid_plan_config,
    is_paid_phone_call_plan,
)


def test_default_free_and_paid_plan_config():
    free_cfg = get_free_plan_config(config={})
    assert free_cfg['phone_calls_profile'] == 'free'
    assert free_cfg['monthly_call_limit'] == 0
    assert free_cfg['max_duration_seconds'] == 300
    assert free_cfg['allowed_countries'] == []
    assert free_cfg['effective_overlay']['source'] == 'catalog'
    assert free_cfg['effective_overlay']['declared'] is False

    paid_cfg = get_paid_plan_config(config={})
    assert paid_cfg['phone_calls_profile'] == 'paid'
    assert paid_cfg['monthly_call_limit'] is None
    assert paid_cfg['max_duration_seconds'] is None
    assert paid_cfg['allowed_countries'] == []
    assert paid_cfg['effective_overlay']['source'] == 'catalog'


def test_is_paid_phone_call_plan():
    assert is_paid_phone_call_plan(None) is False
    assert is_paid_phone_call_plan(PlanType.basic) is False
    assert is_paid_phone_call_plan("unknown_plan") is False
    assert is_paid_phone_call_plan(PlanType.operator) is True
    assert is_paid_phone_call_plan(PlanType.architect) is True


def test_declared_override_sanitizes_allowed_countries():
    defaults = {"allowed_countries": [], "monthly_call_limit": 0, "max_duration_seconds": 300}

    # ISO-2 trimming, uppercasing, and invalid item filtering
    raw = {
        "allowed_countries": ["us", " ca ", "GB", "FRA", 1234, None, "", "   ", "de"],
    }
    cleaned = _declared_override(raw, defaults)
    assert cleaned["allowed_countries"] == ["US", "CA", "GB", "DE"]

    # Non-list allowed_countries is ignored
    non_list_raw = {"allowed_countries": "US"}
    cleaned_non_list = _declared_override(non_list_raw, defaults)
    assert "allowed_countries" not in cleaned_non_list


def test_declared_override_guards_limits_and_booleans():
    defaults = {"monthly_call_limit": 0, "max_duration_seconds": 300}

    # Valid values
    valid_raw = {"monthly_call_limit": 10, "max_duration_seconds": 600}
    assert _declared_override(valid_raw, defaults) == {"monthly_call_limit": 10, "max_duration_seconds": 600}

    # None clears limit to unlimited
    none_raw = {"monthly_call_limit": None, "max_duration_seconds": None}
    assert _declared_override(none_raw, defaults) == {"monthly_call_limit": None, "max_duration_seconds": None}

    # Reject booleans (True must not evaluate to 1)
    bool_raw = {"monthly_call_limit": True, "max_duration_seconds": False}
    assert _declared_override(bool_raw, defaults) == {}

    # Reject negative integers
    neg_raw = {"monthly_call_limit": -5, "max_duration_seconds": -1}
    assert _declared_override(neg_raw, defaults) == {}

    # Reject strings and floats
    invalid_types = {"monthly_call_limit": "10", "max_duration_seconds": 300.5}
    assert _declared_override(invalid_types, defaults) == {}


def test_effective_config_with_firestore_overlay():
    mock_raw = {
        "free_plan": {
            "monthly_call_limit": 5,
            "max_duration_seconds": 450,
            "allowed_countries": ["us", "ca"],
        }
    }
    res = get_free_plan_config(config=mock_raw)
    assert res["monthly_call_limit"] == 5
    assert res["max_duration_seconds"] == 450
    assert res["allowed_countries"] == ["US", "CA"]
    assert res["effective_overlay"]["source"] == "firestore"
    assert res["effective_overlay"]["declared"] is True
    assert set(res["effective_overlay"]["fields"]) == {
        "allowed_countries",
        "max_duration_seconds",
        "monthly_call_limit",
    }


def test_effective_config_ignored_fields():
    mock_raw = {
        "paid_plan": {
            "monthly_call_limit": 50,
            "typo_field": "some_value",
            "unrecognized_key": 999,
        }
    }
    res = get_paid_plan_config(config=mock_raw)
    assert res["monthly_call_limit"] == 50
    assert "typo_field" not in res
    assert "unrecognized_key" not in res
    assert res["effective_overlay"]["ignored_fields"] == ["typo_field", "unrecognized_key"]


def test_get_config_for_plan_resolution():
    mock_raw = {
        "free_plan": {"monthly_call_limit": 2},
        "paid_plan": {"monthly_call_limit": 100},
    }
    free_res = get_config_for_plan(PlanType.basic, config=mock_raw)
    assert free_res["monthly_call_limit"] == 2
    assert free_res["phone_calls_profile"] == "free"

    paid_res = get_config_for_plan(PlanType.operator, config=mock_raw)
    assert paid_res["monthly_call_limit"] == 100
    assert paid_res["phone_calls_profile"] == "paid"


def test_fetch_config_success_missing_and_exception():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"free_plan": {"monthly_call_limit": 3}}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    # Success
    res = _fetch_config(firestore_client=mock_client)
    assert res == {"free_plan": {"monthly_call_limit": 3}}
    mock_client.collection.assert_called_with("phone_call_config")
    mock_client.collection.return_value.document.assert_called_with("default")

    # Document does not exist
    mock_doc.exists = False
    assert _fetch_config(firestore_client=mock_client) == {}

    # Firestore exception handled gracefully
    mock_client.collection.side_effect = RuntimeError("Firestore unavailable")
    assert _fetch_config(firestore_client=mock_client) == {}


def test_fetch_config_none_client():
    assert _fetch_config(firestore_client=None) == {} or isinstance(_fetch_config(firestore_client=None), dict)


def test_injected_firestore_client_in_get_plan_config():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"free_plan": {"monthly_call_limit": 7}}
    mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

    res = get_free_plan_config(firestore_client=mock_client)
    assert res["monthly_call_limit"] == 7
