"""Content-free fact wire format: geometry deltas and authoritative references.

No transcript, title, notes, names, structured member metadata or encrypted
content blobs are retained. Speech fields are reloaded from legacy authority by
the drain. Allowlisting also protects future content fields by default.
"""

from copy import deepcopy

ROW_FIELDS = frozenset(
    {
        'id',
        'status',
        'close_reason',
        'started_at',
        'last_activity_at',
        'recorded_end',
        'closed_at',
        'conversation_ids',
        'recorded_members',
        'member_activity',
        'discarded_conversation_ids',
        'duplicate_conversation_ids',
        'recovered_conversation_ids',
        'recorded_merged_into',
        'sources',
        'parallel_content_spans',
        'composed_fingerprint',
        'composer_version',
        'compose_pending_since',
        'summary_needs_regeneration',
        'wrap_up_requested_at',
        'closing_conversation_id',
        'primary_conversation_id',
    }
)


def geometry(row):
    return {key: deepcopy(value) for key, value in row.items() if key in ROW_FIELDS}


def compact_events(events):
    result = []
    for event in events:
        kind, payload = event['kind'], event['payload']
        if kind == 'mutation':
            before = {row['id']: geometry(row) for row in payload.get('before', [])}
            rows = []
            for row in payload.get('after', []):
                old, new = before.get(row['id'], {}), geometry(row)
                rows.append(
                    {
                        'id': row['id'],
                        'seed': old,
                        'set': {k: v for k, v in new.items() if k not in old or old[k] != v},
                        'unset': sorted(set(old) - set(new)),
                    }
                )
            result.append(
                {
                    'kind': 'mutation_delta',
                    'payload': {
                        'rows': rows,
                        'seeds': [v for k, v in before.items() if k not in {r['id'] for r in rows}],
                        'span': deepcopy(payload.get('span')),
                        'links': deepcopy(payload.get('links') or {}),
                        'receipts': deepcopy(payload.get('receipts') or {}),
                    },
                }
            )
        elif kind in {'baseline', 'fence'}:
            result.append(
                {'kind': kind, 'payload': {'replace': payload.get('replace', False), 'row': geometry(payload['row'])}}
            )
        elif kind == 'member':
            result.append({'kind': 'member_refresh', 'cid': event['cid'], 'payload': {}})
        elif kind in {
            'mutation_delta',
            'member_refresh',
            'home_refresh',
            'backfill_complete',
            'receipts',
            'baseline_link',
            'link',
            'span_recorded',
            'conversation_merged',
            'conversation_discarded',
        }:
            result.append(deepcopy(event))
        else:
            raise ValueError('unsupported_episode_fact')
    return result
