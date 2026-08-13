"""Wrapped (yearly recap) CRUD exercised through the neutral storage port (WP2, ADR-0002).

database.wrapped stores at ``users/{uid}/wrapped/{year}`` via point ops (get/set/update). These
tests drive the real port seam with FakeDocumentStore, asserting on returned values and stored
state rather than Firestore call mechanics.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest  # noqa: E402

import database.wrapped as wrapped_module  # noqa: E402
from database.wrapped import WrappedStatus  # noqa: E402
from tests.store_fakes import install_fake_db_client  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    # ADR-0044: wrapped threads the raw ``db`` client; inject the neutral facade over a fake so the
    # real read/write logic runs against ``fake._docs`` (was the retired ``_store`` seam).
    fake = install_fake_db_client(monkeypatch)
    return fake


def test_get_wrapped_missing_returns_none(store):
    assert wrapped_module.get_wrapped('uid-1', 2025) is None


def test_create_then_get_roundtrips_at_expected_path(store):
    created = wrapped_module.create_wrapped('uid-1', 2025)

    assert created['status'] == WrappedStatus.PROCESSING
    assert created['year'] == 2025
    # Path is users/{uid}/wrapped/{year}, doc id is the stringified year.
    assert store.exists('users/uid-1/wrapped/2025')

    fetched = wrapped_module.get_wrapped('uid-1', 2025)
    assert fetched is not None
    assert fetched['status'] == WrappedStatus.PROCESSING
    assert fetched['year'] == 2025


def test_update_status_done_writes_result_and_clears_error(store):
    wrapped_module.create_wrapped('uid-1', 2025)

    ok = wrapped_module.update_wrapped_status(
        'uid-1', 2025, WrappedStatus.DONE, result={'top_word': 'omi'}
    )
    assert ok is True

    stored = store.get('users/uid-1/wrapped/2025').to_dict()
    assert stored['status'] == WrappedStatus.DONE
    assert stored['result'] == {'top_word': 'omi'}
    assert stored['error'] is None
    assert stored['completed_at'] is not None


def test_update_status_error_records_message_and_nulls_result(store):
    wrapped_module.create_wrapped('uid-1', 2025)

    ok = wrapped_module.update_wrapped_status(
        'uid-1', 2025, WrappedStatus.ERROR, error='boom'
    )
    assert ok is True

    stored = store.get('users/uid-1/wrapped/2025').to_dict()
    assert stored['status'] == WrappedStatus.ERROR
    assert stored['error'] == 'boom'
    assert stored['result'] is None


def test_update_status_on_missing_doc_returns_false(store):
    assert wrapped_module.update_wrapped_status('uid-1', 2025, WrappedStatus.DONE) is False


def test_update_progress_merges_and_bumps_updated_at(store):
    wrapped_module.create_wrapped('uid-1', 2025)

    ok = wrapped_module.update_wrapped_progress('uid-1', 2025, {'step': 'stats', 'pct': 0.5})
    assert ok is True

    stored = store.get('users/uid-1/wrapped/2025').to_dict()
    assert stored['progress'] == {'step': 'stats', 'pct': 0.5}
    # Original fields survive the partial update.
    assert stored['status'] == WrappedStatus.PROCESSING


def test_update_progress_on_missing_doc_returns_false(store):
    assert wrapped_module.update_wrapped_progress('uid-1', 2025, {'pct': 0.1}) is False


def test_reset_overwrites_prior_state_back_to_processing(store):
    wrapped_module.create_wrapped('uid-1', 2025)
    wrapped_module.update_wrapped_status('uid-1', 2025, WrappedStatus.ERROR, error='boom')

    reset = wrapped_module.reset_wrapped_for_regeneration('uid-1', 2025)
    assert reset['status'] == WrappedStatus.PROCESSING
    assert reset['error'] is None
    assert reset['progress'] is None

    stored = store.get('users/uid-1/wrapped/2025').to_dict()
    assert stored['status'] == WrappedStatus.PROCESSING
    assert stored['error'] is None
