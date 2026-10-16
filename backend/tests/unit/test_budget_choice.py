from unittest.mock import MagicMock, patch
import pytest

from database.budget_choice import (
    BudgetChoiceConflict,
    _reference,
    _store,
    get_choice,
    set_choice,
)


def test_reference_success():
    client = MagicMock()
    ref = _reference(client, "user_123")
    client.collection.assert_called_with("users")
    user_doc = client.collection("users").document.return_value
    user_doc.collection.assert_called_with("budget_choice")
    user_doc.collection("budget_choice").document.assert_called_with("current")


def test_reference_strips_uid():
    client = MagicMock()
    _reference(client, "  user_trimmed  ")
    client.collection("users").document.assert_called_with("user_trimmed")


@pytest.mark.parametrize("invalid_uid", ["", "   ", None, 123])
def test_reference_invalid_uid_raises(invalid_uid):
    client = MagicMock()
    with pytest.raises(ValueError, match="invalid_uid"):
        _reference(client, invalid_uid)


def test_get_choice_returns_valid_choice():
    client = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "period": "2026-10",
        "choice": "upgrade",
        "dont_ask_again": True,
    }
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        doc_mock
    )

    result = get_choice("user_123", "2026-10", firestore_client=client)
    assert result == {
        "period": "2026-10",
        "choice": "upgrade",
        "dont_ask_again": True,
    }


def test_get_choice_period_mismatch_returns_none():
    client = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "period": "2026-09",
        "choice": "upgrade",
        "dont_ask_again": False,
    }
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        doc_mock
    )

    result = get_choice("user_123", "2026-10", firestore_client=client)
    assert result is None


@pytest.mark.parametrize(
    "uid,period",
    [
        ("", "2026-10"),
        ("   ", "2026-10"),
        (None, "2026-10"),
        ("user_123", ""),
        ("user_123", "   "),
        ("user_123", None),
    ],
)
def test_get_choice_empty_or_invalid_inputs_returns_none(uid, period):
    client = MagicMock()
    result = get_choice(uid, period, firestore_client=client)
    assert result is None
    client.collection.assert_not_called()


def test_get_choice_firestore_failure_boundary():
    client = MagicMock()
    client.collection.side_effect = RuntimeError("Firestore unavailable")

    result = get_choice("user_123", "2026-10", firestore_client=client)
    assert result is None


def test_set_choice_validation_uid_period():
    with pytest.raises(ValueError, match="invalid_uid"):
        set_choice("", "2026-10", "upgrade", False)

    with pytest.raises(ValueError, match="invalid_uid"):
        set_choice("   ", "2026-10", "upgrade", False)

    with pytest.raises(ValueError, match="invalid_budget_period"):
        set_choice("user_123", "", "upgrade", False)

    with pytest.raises(ValueError, match="invalid_budget_period"):
        set_choice("user_123", "   ", "upgrade", False)


@pytest.mark.parametrize(
    "choice,dont_ask",
    [
        ("invalid_choice", False),
        (None, False),
        ("upgrade", "not_a_bool"),
        ("on_device", 1),
        ("on_device", None),
    ],
)
def test_set_choice_validation_choice_and_bool(choice, dont_ask):
    with pytest.raises(ValueError, match="invalid_budget_choice"):
        set_choice("user_123", "2026-10", choice, dont_ask)


def test_store_creates_new_choice():
    transaction = MagicMock()
    ref = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = None
    ref.get.return_value = doc_mock

    # Invoke unwrapped _store directly
    func = getattr(_store, "__wrapped__", _store)
    res = func(transaction, ref, "2026-10", "on_device", True)

    assert res == {"period": "2026-10", "choice": "on_device", "dont_ask_again": True}
    transaction.set.assert_called_once_with(ref, res)


def test_store_idempotent_same_choice():
    transaction = MagicMock()
    ref = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "period": "2026-10",
        "choice": "upgrade",
        "dont_ask_again": False,
    }
    ref.get.return_value = doc_mock

    func = getattr(_store, "__wrapped__", _store)
    res = func(transaction, ref, "2026-10", "upgrade", False)

    assert res == {"period": "2026-10", "choice": "upgrade", "dont_ask_again": False}
    transaction.set.assert_not_called()


def test_store_conflict_different_choice_same_period():
    transaction = MagicMock()
    ref = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "period": "2026-10",
        "choice": "on_device",
        "dont_ask_again": False,
    }
    ref.get.return_value = doc_mock

    func = getattr(_store, "__wrapped__", _store)
    with pytest.raises(BudgetChoiceConflict, match="choice_already_recorded"):
        func(transaction, ref, "2026-10", "upgrade", False)


def test_store_conflict_future_period_already_recorded():
    transaction = MagicMock()
    ref = MagicMock()
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "period": "2026-11",
        "choice": "upgrade",
        "dont_ask_again": True,
    }
    ref.get.return_value = doc_mock

    func = getattr(_store, "__wrapped__", _store)
    with pytest.raises(BudgetChoiceConflict, match="budget_period_changed"):
        func(transaction, ref, "2026-10", "upgrade", True)


def test_set_choice_runs_transactional():
    client = MagicMock()
    with patch("database.budget_choice.run_transactional") as mock_run_tx:
        mock_run_tx.return_value = {
            "period": "2026-10",
            "choice": "upgrade",
            "dont_ask_again": False,
        }
        res = set_choice("  user_123  ", "  2026-10  ", "upgrade", False, firestore_client=client)

        assert res == {"period": "2026-10", "choice": "upgrade", "dont_ask_again": False}
        mock_run_tx.assert_called_once()
        args = mock_run_tx.call_args[0]
        assert args[0] == client
        assert args[1] == _store
        assert args[3] == "2026-10"
        assert args[4] == "upgrade"
        assert args[5] is False
