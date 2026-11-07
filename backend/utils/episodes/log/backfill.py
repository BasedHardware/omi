"""Bounded, restartable legacy-to-fact conversion; never deletes legacy state."""

from database import episode_log as store
from utils.episodes.log.codec import digest
from utils.episodes.log.fold import automatic

PAGE_SIZE = 100


def events_for(kind, doc_id, row):
    if kind == 'episodes':
        return [{'kind': 'baseline' if automatic(row) else 'fence', 'payload': {'row': dict(row, id=doc_id)}}]
    if kind == 'episode_links':
        if doc_id == 'recorded_timeline':
            return []  # Serialization metadata, not a domain boundary.
        return [{'kind': 'baseline_link', 'cid': doc_id, 'payload': row}]
    if kind in {'episode_segment_receipts', 'receipt_archive'}:
        return [{'kind': 'receipts', 'cid': doc_id, 'payload': {'ids': sorted(set(row.get('ids') or []))}}]
    raise ValueError('unsupported legacy namespace')


def convert(uid, records, *, apply=False, firestore_client=None):
    """Records: namespace, id, unsealed data, optional archive index. Dry run is pure."""
    report = {'documents': 0, 'facts': 0, 'written': 0, 'fingerprints': 0, 'consumed_ids': 0, 'fences': 0}
    for record in records:
        kind, doc_id, row = record['namespace'], record['id'], record['data']
        events = events_for(kind, doc_id, row)
        report['documents'] += 1
        report['facts'] += len(events)
        report['fingerprints'] += bool(row.get('composed_fingerprint'))
        report['consumed_ids'] += len(set(row.get('ids') or []))
        report['fences'] += sum(event['kind'] == 'fence' for event in events)
        if apply and events:
            key = digest({'backfill': record})
            if store.append(uid, key, events, firestore_client=firestore_client) is not None:
                report['written'] += 1
    return report
