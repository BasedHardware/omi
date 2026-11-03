"""Legacy Home-title hydration: transcript-only batches, without stored-data writes."""

import logging
from typing import Any, Dict, List
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def neutralize_legacy_list_titles(uid: str, rows: List[Dict[str, Any]], *, budget=None, firestore_client=None) -> None:
    """Bounded transcript-only batch for pre-provenance titles; never expose the blob.

    Modern stamped titles and user edits need no extra IO. The ordinary list
    projection still excludes transcript detail before decode/correction reads.
    """
    from database import conversations
    from utils.conversations.home_titles import neutralize_minimum_title

    candidates = {
        row['id']: row
        for row in rows
        if row.get('id')
        and not row.get('user_title')
        and (row.get('structured') or {}).get('title')
        and not (row.get('structured') or {}).get('title_provenance')
        and 'transcript_segments' not in row
    }
    if not candidates:
        return
    try:
        if budget is not None:
            budget.check()
        client = firestore_client if firestore_client is not None else conversations.db
        refs = [
            client.collection('users').document(uid).collection('conversations').document(cid) for cid in candidates
        ]
        options = {'timeout': budget.rpc_timeout()} if budget is not None else {}
        snapshots = (
            snapshot
            for offset in range(0, len(refs), 50)
            for snapshot in client.get_all(
                refs[offset : offset + 50],
                field_paths=['transcript_segments', 'transcript_segments_compressed'],
                **options,
            )
        )
        for snapshot in snapshots:
            if budget is not None:
                budget.charge()
            if not snapshot.exists or snapshot.id not in candidates:
                continue
            raw = snapshot.to_dict() or {}
            if raw.get('transcript_segments') is None:
                continue
            row = candidates[snapshot.id]
            segments = conversations.decode_transcript_segments_blob(
                uid,
                raw.get('transcript_segments'),
                bool(raw.get('transcript_segments_compressed')),
                require_decryption=row.get('data_protection_level') == 'enhanced',
            )
            projected = neutralize_minimum_title({**row, 'transcript_segments': segments})
            row['structured'] = projected['structured']
    except Exception as error:
        record_fallback(
            component='firestore_read', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
        )
        logger.warning('event=home_legacy_title outcome=unavailable exception_type=%s', type(error).__name__)
