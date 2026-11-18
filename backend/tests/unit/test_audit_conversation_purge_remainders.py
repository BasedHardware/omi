from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Forbidden

from scripts import audit_conversation_purge_remainders as audit

UID = 'private-owner'
CID = 'private-conversation'
START = datetime(2026, 11, 18, 14, tzinfo=timezone.utc)
END = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)


class Snapshot:
    id = 'segment'

    def __init__(self, data):
        self.data = data
        self.reference = SimpleNamespace(path=f'users/{UID}/deleted_conversations/{CID}')

    def to_dict(self):
        return self.data

    def get(self, key):
        return self.data[key]


class Query:
    def __init__(self, rows):
        self.rows = rows

    def where(self, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def select(self, *args):
        return self

    def limit(self, size):
        return Query(self.rows[:size])

    def get(self, **kwargs):
        return self.rows


@pytest.fixture
def stores():
    rows = {}
    db = Mock()
    db.collection_group.return_value = Query([Snapshot({})])
    gcs = Mock()
    gcs.list_blobs.return_value = []
    return db, gcs, rows


@pytest.mark.parametrize('location', [None, *audit.LOCATIONS])
def test_locations(stores, location):
    db, gcs, rows = stores
    if location == 'wal_objects':
        gcs.list_blobs.return_value = [object()]
    elif location == 'segment_journals':
        rows[location] = [Snapshot({'segment_id': 'segment'})]
    elif location == 'referenced_objects':
        rows['batch_pipeline_prod_artifacts'] = [Snapshot({'conversation_id': CID, 'uri': 'test'})]
        gcs.bucket.return_value.blob.return_value.exists.return_value = True
    elif location is not None:
        rows[location] = [Snapshot({'conversation_id': CID, 'owner_key': audit.privacy_owner_key(UID)})]

    def collection(name):
        result = Mock()
        result.where.side_effect = lambda **kwargs: Query(rows.get(name, []))
        document = result.document.return_value
        document.get.return_value = Mock(exists=False, **{'to_dict.return_value': {}})
        document.collection.return_value.where.return_value = Query(rows.get('segment_journals', []))
        return result

    db.collection.side_effect = collection
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(audit, 'batch_object_address', lambda uid, uri: ('bucket', 'private-object', None))
        report = audit.audit(db, gcs, START, END, audit.Budget(100))
    assert report['terminal_checked'] == 1
    assert report['pending'] == 0
    if location is None:
        assert not any(report['remainders'].values())
        assert report['verdict'] == 'incomplete_scan'  # Independent shadow coverage is unavailable.
    else:
        assert report['remainders'][location] == 1
        assert report['verdict'] == 'remainders_found'
    encoded = json.dumps(report)
    assert all(secret not in encoded for secret in (UID, CID, 'private-object'))


def test_pending_is_excluded(stores):
    db, gcs, _ = stores
    db.collection.return_value.document.return_value.get.return_value.exists = True
    report = audit.audit(db, gcs, START, END, audit.Budget(100))
    assert (report['tombstones'], report['pending'], report['terminal_checked']) == (1, 1, 0)
    gcs.list_blobs.assert_not_called()


def test_access_denial_drops_exception_payload():
    with pytest.raises(audit.Incomplete, match='^access_denied:deleted_conversations$'):
        audit.read('deleted_conversations', Mock(side_effect=Forbidden(f'{UID}/{CID}')))
