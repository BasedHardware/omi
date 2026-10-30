"""Erase held content, retaining only allowlisted v4 publication/audit evidence."""

import hashlib
from typing import Any

from google.api_core.exceptions import NotFound

from utils.observability.held_content import record_erasure
from utils.sync import cap_hold


def _destinations(record: dict) -> set[str]:
    result = {record['conversation_id']} if record.get('conversation_id') else set()
    response = record.get('response') or {}
    for key in ('new_memories', 'updated_memories', '_fenced_conversation_ids', '_merged'):
        result.update(response.get(key) or [])
    return result


def terminal_receipts(row: dict) -> dict:
    """No paths, provider results, transcripts, or encrypted metadata survive.

    Piece names can be file paths, so retain only their opaque digest. Source
    seconds (rather than charged seconds) also describe settled empty pieces.
    This map shares the existing v4 tombstone's lifetime and owner erasure.
    """
    if row.get('state') == 'purged':
        return row.get('terminal_receipts') or {'version': 1, 'pieces': [], 'conversation_ids': []}
    plan = row.get('piece_plan') or {}
    receipts = row.get('piece_receipts') or {}
    ingests = row.get('piece_ingests') or {}
    pieces, destinations = [], set()
    for name in sorted(set(plan) | set(receipts) | set(ingests)):
        receipt = receipts.get(name) or {}
        ingest = ingests.get(name) or {}
        ids = _destinations(receipt) | _destinations(ingest)
        destinations.update(ids)
        outcome = (
            'failed'
            if receipt.get('state') == 'failed_reconciliation'
            else (
                'transcribed'
                if ingest or receipt.get('has_content')
                else 'settled_empty' if receipt.get('state') == 'transcribed' else 'failed'
            )
        )
        pieces.append(
            {
                'piece_id': hashlib.sha256(name.encode()).hexdigest(),
                'outcome': outcome,
                'seconds': (plan.get(name) or {}).get('seconds', receipt.get('seconds', ingest.get('seconds', 0))),
                'attempt': receipt.get('attempt', ingest.get('attempt', 0)),
                'provider': receipt.get('provider')
                or ingest.get('provider')
                or (receipt.get('usage_metadata') or {}).get('provider')
                or (ingest.get('usage_metadata') or {}).get('provider'),
                'conversation_ids': sorted(ids),
            }
        )
    if not pieces:
        pieces.append(
            {
                'piece_id': 'source',
                'outcome': 'empty_plan' if row.get('piece_plan') == {} else 'failed',
                'seconds': row.get('seconds', 0),
                'attempt': 0,
                'provider': None,
                'conversation_ids': [],
            }
        )
    return {'version': 1, 'pieces': pieces, 'conversation_ids': sorted(destinations)}


def erase(uid: str, snapshot: Any, row: dict[str, Any]) -> None:
    try:
        _erase_objects(uid, snapshot, row)
    except Exception:
        record_erasure('failure')
        raise


def _erase_objects(uid: str, snapshot: Any, row: dict[str, Any]) -> None:
    if row.get('live_custody_version') == 4:
        # Ingest proofs are written in a separate conversation transaction and
        # may be newer than the coordinator's in-memory completion checkpoint.
        row = {**row, **(snapshot.reference.get().to_dict() or {})}
    # Account deletion already purges this existing owner-scoped chunk prefix.
    objects = [
        row,
        *({'audio_path': part} for part in row.get('audio_parts') or []),
        *(row.get('stage_parts') or []),
        *(row.get('piece_plan') or {}).values(),
    ]
    for path in {item[key] for item in objects for key in ('audio_path', 'metadata_path') if item.get(key)}:
        if not path.startswith(f'chunks/{uid}/cap-held/'):
            raise ValueError('hold audio owner mismatch')
        try:
            cap_hold.get_private_cloud_sync_bucket().blob(path).delete()
        except NotFound:
            pass
    if row.get('live_custody_version') == 4:
        # Keep the publication idempotency barrier after source deletion. A lost
        # writer reply must not recreate/retranscribe a capture already recovered.
        snapshot.reference.set(
            {
                'state': 'purged',
                'live_custody_version': 4,
                'terminal_receipts': terminal_receipts(row),
                'stage_fragment_ids': row.get('stage_fragment_ids')
                or [part['id'] for part in row.get('stage_parts') or []],
                'next_attempt_at': cap_hold.RETAINED_NEXT_ATTEMPT_AT,
            }
        )
    else:
        snapshot.reference.delete()
