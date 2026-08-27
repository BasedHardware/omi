"""Regression tests for stable person rename and alias retention."""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.users as users_db  # noqa: E402
from database import person_aliases  # noqa: E402


def _person_ref(fake_db, exists):
    # db.collection('users').document(uid).collection('people').document(person_id)
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = exists
    return ref


def test_update_person_missing_returns_false_without_updating():
    fake_db = MagicMock()
    _person_ref(fake_db, exists=False)
    with patch.object(users_db, "db", fake_db), patch.object(
        users_db, "rename_person_retaining_aliases", return_value=False
    ) as rename:
        assert users_db.update_person("u1", "missing", "Alice") is False
    rename.assert_called_once_with(fake_db, "u1", "missing", "Alice")


def test_update_person_existing_updates_and_returns_true():
    fake_db = MagicMock()
    _person_ref(fake_db, exists=True)
    with patch.object(users_db, "db", fake_db), patch.object(
        users_db, "rename_person_retaining_aliases", return_value=True
    ) as rename:
        assert users_db.update_person("u1", "p1", "Alice") is True
    rename.assert_called_once_with(fake_db, "u1", "p1", "Alice")


def test_update_person_deleted_between_check_and_update_returns_false():
    fake_db = MagicMock()
    _person_ref(fake_db, exists=True)
    with patch.object(users_db, "db", fake_db), patch.object(users_db, "rename_person_retaining_aliases") as rename:
        rename.return_value = False
        assert users_db.update_person("u1", "racing", "Alice") is False


def test_person_alias_boundary_maps_transactional_not_found_to_missing():
    fake_db = MagicMock()
    with patch.object(
        person_aliases,
        "update_person_name_transaction",
        side_effect=person_aliases.NotFound("person deleted mid-rename"),
    ):
        assert person_aliases.rename_person_retaining_aliases(fake_db, "u1", "racing", "Alice") is False


def test_person_rename_transaction_retains_old_names_as_bounded_exact_aliases():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {
        "name": "Alice Smith",
        "aliases": ["Ally", " ALICE SMITH ", "A. Smith", None],
    }

    result = person_aliases.update_person_name_transaction.to_wrap(transaction, person_ref, " Alicia Smith ")

    assert result is True
    payload = transaction.update.call_args.args[1]
    assert payload["name"] == "Alicia Smith"
    assert payload["aliases"] == ["Ally", "ALICE SMITH", "A. Smith"]
    assert payload["updated_at"].tzinfo is not None


def test_person_rename_transaction_rejects_blank_without_mutation():
    transaction = MagicMock()
    person_ref = MagicMock()
    snapshot = person_ref.get.return_value
    snapshot.exists = True
    snapshot.to_dict.return_value = {"name": "Alice"}

    assert person_aliases.update_person_name_transaction.to_wrap(transaction, person_ref, "   ") is False
    transaction.update.assert_not_called()
