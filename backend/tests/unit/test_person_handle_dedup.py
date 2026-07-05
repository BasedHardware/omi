import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (  # noqa: E402
    ensure_utils_memory_packages_importable,
    install_canonical_write_runtime_stubs,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
)

ensure_utils_memory_packages_importable(str(BACKEND_DIR))
install_database_client_stub()
install_canonical_write_runtime_stubs()
install_ws_i_heavy_import_stubs()

# install_canonical_write_runtime_stubs() stubs database.users with a mock; this test
# needs the REAL module, so evict that stub and import it fresh.
sys.modules.pop("database.users", None)
import database.users as u  # noqa: E402

from google.api_core.exceptions import AlreadyExists  # noqa: E402

assert type(u).__name__ == "module", "expected the real users module, got a stub"


def test_same_handle_across_sources_seeds_the_same_person_id():
    """A phone number ingested from two platforms (iMessage + WhatsApp) must resolve to
    ONE Person: the id is seeded from the handle only, not the source, so concurrent
    cross-source creates converge on a single document instead of duplicating."""
    created = []

    def fake_create_if_absent(uid, data):
        created.append(data)
        return data

    with patch.object(u, 'get_person_by_handle', return_value=None), patch.object(
        u, 'create_person_if_absent', side_effect=fake_create_if_absent
    ):
        p_imessage = u.get_or_create_person_by_handle('uid1', '+15551234567', 'Alice', source='imessage')
        p_whatsapp = u.get_or_create_person_by_handle('uid1', '+15551234567', 'Alice', source='whatsapp')

    # Same handle → same deterministic id regardless of which platform created it.
    assert p_imessage['id'] == p_whatsapp['id']
    assert created[0]['id'] == created[1]['id']


def test_different_handles_still_get_distinct_ids():
    """Sanity: the handle-only seed still separates genuinely different contacts."""
    with patch.object(u, 'get_person_by_handle', return_value=None), patch.object(
        u, 'create_person_if_absent', side_effect=lambda uid, data: data
    ):
        a = u.get_or_create_person_by_handle('uid1', '+15551234567', 'Alice', source='imessage')
        b = u.get_or_create_person_by_handle('uid1', '+15559999999', 'Bob', source='imessage')

    assert a['id'] != b['id']


def test_existing_handle_short_circuits_before_create():
    """If the handle already resolves to a Person, no new doc is created."""
    existing = {'id': 'p_existing', 'name': 'Alice', 'handles': ['+15551234567']}
    with patch.object(u, 'get_person_by_handle', return_value=existing), patch.object(
        u, 'create_person_if_absent'
    ) as create_mock:
        got = u.get_or_create_person_by_handle('uid1', '+15551234567', 'Alice', source='whatsapp')

    assert got is existing
    create_mock.assert_not_called()


def test_create_person_if_absent_returns_existing_on_race():
    """When a concurrent writer already created the handle-seeded id, create_if_absent
    returns the stored doc instead of clobbering it — so the race yields one Person."""
    stored = {'id': 'p1', 'name': 'Alice (first writer)', 'handles': ['+15551234567'], 'source': 'imessage'}

    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = dict(stored)

    doc_ref = MagicMock()
    doc_ref.create.side_effect = AlreadyExists('exists')  # our create lost the race
    doc_ref.get.return_value = snapshot
    doc_ref.id = 'p1'

    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    losing_write = {'id': 'p1', 'name': 'Alice (second writer)', 'handles': ['+15551234567'], 'source': 'whatsapp'}
    with patch.object(u, 'db', db):
        result = u.create_person_if_absent('uid1', losing_write)

    # The first writer's doc wins; our overwrite is discarded.
    assert result['name'] == 'Alice (first writer)'
    assert result['source'] == 'imessage'


def test_create_person_if_absent_creates_when_free():
    """Happy path: id is free → the doc is created and returned as-is."""
    doc_ref = MagicMock()
    doc_ref.create.return_value = None
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    data = {'id': 'p1', 'name': 'Alice', 'handles': ['+15551234567'], 'source': 'imessage'}
    with patch.object(u, 'db', db):
        result = u.create_person_if_absent('uid1', data)

    assert result is data
    doc_ref.create.assert_called_once_with(data)
