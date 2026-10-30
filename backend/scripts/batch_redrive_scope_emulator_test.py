#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Loopback-only proof of bounded owner pagination past 1,000 lifetime rows."""

import os
from pathlib import Path
import sys
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.batch_pipeline import redrive_scope as scope


def main():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:', '[::1]:')):
        raise RuntimeError('loopback_firestore_emulator_required')
    client = firestore.Client(project='demo-p55-redrive', credentials=AnonymousCredentials())
    collection = client.collection('p55_redrive_scope_' + uuid4().hex)
    docs = {f'old-{i:04d}': dict(owner_id='synthetic', quarantined_at=10, state='committed') for i in range(1100)}
    base = dict(owner_id='synthetic', quarantined_at=100, state='quarantined', recovery_state='failed_held')
    docs.update({sid: base for sid in ['a-first', 'm-middle', 'z-last']})
    docs['receipt'] = {**base, 'silence_disposition': {'state': 'completed'}}
    docs['paid'] = {**base, 'speech_redrive': {'state': 'failed_held'}}
    docs['future'] = {**base, 'quarantined_at': 151}
    docs['foreign'] = {**base, 'owner_id': 'foreign'}
    try:
        items = list(docs.items())
        for start in range(0, len(items), 400):
            batch = client.batch()
            for sid, row in items[start : start + 400]:
                batch.set(collection.document(sid), row)
            batch.commit()
        found = list(scope.owner_jobs(collection, 'synthetic', page_size=137, read_budget=2000))
        assert len(found) == 1106 and [doc.id for doc in found] == sorted(set(docs) - {'foreign'})
        selected = [doc.id for doc in found if scope.eligible(doc.to_dict(), 50, 150)]
        assert selected == ['a-first', 'm-middle', 'z-last']
        try:
            list(scope.owner_jobs(collection, 'synthetic', page_size=137, read_budget=1000))
        except scope.ScopeRefused as error:
            assert str(error) == 'owner_read_budget'
        else:
            raise AssertionError('budget guard did not fail closed')
        print(
            'PASS: paginated 1106 owner rows; selected 3 held units; excluded foreign/time/spent rows; budget refused'
        )
    finally:
        for start in range(0, len(docs), 400):
            batch = client.batch()
            for sid in list(docs)[start : start + 400]:
                batch.delete(collection.document(sid))
            batch.commit()
        client.close()


if __name__ == '__main__':
    main()
