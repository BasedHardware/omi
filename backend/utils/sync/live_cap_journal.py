"""Emergency encrypted fragment custody in the existing staging/redrive queue.

GCS and Firestore are independent failure domains. A confirmed create hands off
custody even while GCS is unavailable. No TTL, local file, new query or index.
Only the existing fragment-claim sealer may retire the recovered source.
"""

import json
import time
from pathlib import Path
from typing import Callable

from google.api_core.exceptions import AlreadyExists

from database.legal_holds import external_write_fence
from utils.encryption import encrypt, decrypt, encrypt_audio_chunk, decrypt_audio_chunk
from utils.observability.fallback import record_fallback
from utils.observability.held_content import record_staging_retry, record_deferred_seconds
from utils.sync import cap_hold, live_cap_codec
from utils.sync.live_cap_publication import Publication

JOURNAL_RPC_SECONDS = 3.0


class PendingFragment(Exception):
    def __init__(self, row: dict) -> None:
        self.row = row


def defer(
    uid: str, encoded: bytes, source: Publication, metadata: dict, seconds: float, *, standalone: bool = False
) -> None:
    if not 0 < len(encoded) <= live_cap_codec.MAX_OBJECT_BYTES or not 0 < seconds <= 60:
        raise ValueError('invalid emergency live fragment')
    # Same late identity as append recovery: fragment claims also fence an
    # ambiguous original staging commit from double counting this fragment.
    identity = source.identity if standalone else f'late:{source.identity}'
    fragment_id = f'pending:{source.identity}' if standalone else source.identity
    body = {
        'state': 'staging',
        'stage_parts': [],
        'stage_pending': encrypt_audio_chunk(encoded, uid),
        'stage_metadata': encrypt(json.dumps(metadata), uid),
        'stage_fragment_id': fragment_id,
        'stage_seconds': seconds,
        'seconds': 0,  # Only seal increments the published summary.
        'writer_until': 0,
        'created_at': time.time(),
        'started_at': metadata['timestamp'],
        'listed_at': metadata['timestamp'],
        'live_custody_version': 4,
    }
    with external_write_fence(uid):
        ref = cap_hold.holds(uid).document(identity)
        try:
            ref.create(body, timeout=JOURNAL_RPC_SECONDS, retry=None)
        except AlreadyExists:
            row = ref.get(timeout=JOURNAL_RPC_SECONDS, retry=None).to_dict() or {}
            if (
                row.get('state') not in {'held', 'completed', 'retained', 'purged', 'superseded'}
                and row.get('stage_fragment_id') != fragment_id
                and not any(part.get('id') == fragment_id for part in row.get('stage_parts', []))
            ):
                raise ValueError('emergency live custody identity mismatch')
    record_staging_retry('deferred')
    record_deferred_seconds(seconds)
    record_fallback(component='stt_live_session', from_mode='none', to_mode='none', reason='other', outcome='degraded')


def restore(uid: str, identity: str, row: dict, append: Callable) -> None:
    """One bounded put per sweep; append atomically replaces the inline journal.

    A crash or lost reply before append leaves the encrypted journal. A later
    put uses the original immutable identity and verifies an existing object.
    Concurrent sweepers converge through append and the existing claim ledger.
    """
    metadata = json.loads(decrypt(row['stage_metadata'], uid))
    encoded, _ = decrypt_audio_chunk(row['stage_pending'], uid)
    source = Publication(uid, identity=row['stage_fragment_id'])
    with cap_hold.recovery_directory(uid) as directory:
        path = str(Path(directory) / 'pending.opus')
        Path(path).write_bytes(encoded)
        source.fields = cap_hold.upload_held_audio(
            uid,
            path,
            source.identity,
            metadata,
            immutable=True,
            live_size_limit=live_cap_codec.MAX_OBJECT_BYTES,
            rpc_timeout=1.5,
        )
        append(uid, path, Publication(uid, identity=identity), source, metadata, row['stage_seconds'], emergency=True)
