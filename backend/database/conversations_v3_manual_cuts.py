"""Owner-level manual end instants for v3 conversations (reliability experiment ``end_open_conversation``).

A cut is the server time at which the wearer asked to end the conversation in
progress. It holds no content. The builder reads the cuts that fall inside the
span it loaded and starts a new conversation at each one.

Reliability experiment ``live_words_cascade`` is the one exception to "no content": a cut may carry
``live_tail``, the live words the phone was showing for the conversation that End closed
(``utils/conversations/v3/live_tail.py``), encrypted with the owner's key. It is read only by that
conversation's summary pass and removed once stored text covers it or the cut is a day old. Off, the
field is never written or read.
"""

import json
from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from utils import encryption

COLLECTION = 'conversation_v3_manual_cuts'
READ_LIMIT = 200


def _cuts(client, uid):
    return client.collection('users').document(uid).collection(COLLECTION)


TAIL_FIELD = 'live_tail'
TAIL_WORDS_FIELD = 'live_tail_words'
# A retried End request stores its cut again at the same instant.
SAME_INSTANT_LIMIT = 5
# Old tails are looked for this far back from the day-old mark, at most this many Ends per look.
TAIL_SWEEP_WINDOW = timedelta(days=7)
TAIL_SWEEP_LIMIT = 50


def record(uid, at, *, tail=None, tail_words=0, firestore_client=None) -> str:
    """Store one cut and return its id. ``tail`` (already checked and bounded) is stored encrypted."""
    client = firestore_client or get_firestore_client()
    ref = _cuts(client, uid).document()
    row = {'at': at, 'created_at': datetime.now(timezone.utc), 'source': 'client_finalize'}
    if tail:
        row[TAIL_FIELD] = encryption.encrypt(json.dumps(tail, ensure_ascii=False, separators=(',', ':')), uid)
        row[TAIL_WORDS_FIELD] = int(tail_words)
    ref.set(row)
    return ref.id


def tail(uid, at, *, firestore_client=None):
    """The live words stored with the cut at exactly ``at``; None when that cut carries none (one read)."""
    client = firestore_client or get_firestore_client()
    for row in _cuts(client, uid).where(filter=FieldFilter('at', '==', at)).limit(SAME_INSTANT_LIMIT).stream():
        stored = (row.to_dict() or {}).get(TAIL_FIELD)
        if isinstance(stored, str) and stored:
            lines = json.loads(encryption.decrypt(stored, uid))
            return lines if isinstance(lines, list) else None
    return None


def clear_tail(uid, at, *, firestore_client=None) -> None:
    """Remove the stored words of the cut at ``at``; the cut itself stays."""
    client = firestore_client or get_firestore_client()
    for row in _cuts(client, uid).where(filter=FieldFilter('at', '==', at)).limit(SAME_INSTANT_LIMIT).stream():
        if TAIL_FIELD in (row.to_dict() or {}):
            row.reference.update({TAIL_FIELD: firestore.DELETE_FIELD})


def around(uid, at, *, firestore_client=None) -> tuple[datetime | None, datetime | None]:
    """The last cut at or before ``at`` and the first cut after it (two one-row reads)."""
    client = firestore_client or get_firestore_client()

    def one(query):
        for row in query.limit(1).stream():
            value = (row.to_dict() or {}).get('at')
            return value if isinstance(value, datetime) else None
        return None

    cuts = _cuts(client, uid)
    before = one(cuts.where(filter=FieldFilter('at', '<=', at)).order_by('at', direction='DESCENDING'))
    after = one(cuts.where(filter=FieldFilter('at', '>', at)).order_by('at'))
    return before, after


def load(uid, since, *, firestore_client=None) -> list[datetime]:
    """Cuts at or after ``since``, oldest first."""
    client = firestore_client or get_firestore_client()
    rows = _cuts(client, uid).where(filter=FieldFilter('at', '>=', since)).order_by('at').limit(READ_LIMIT).stream()
    return [at for at in ((row.to_dict() or {}).get('at') for row in rows) if isinstance(at, datetime)]


def clear_tails_before(uid, before, *, firestore_client=None) -> int:
    """Remove the stored words of the cuts in the week before ``before``; returns how many held any.

    One range read on the cut time (``TAIL_SWEEP_LIMIT`` rows at most). A tail older than that week is
    reached only if its conversation is summarised again.
    """
    client = firestore_client or get_firestore_client()
    rows = (
        _cuts(client, uid)
        .where(filter=FieldFilter('at', '>=', before - TAIL_SWEEP_WINDOW))
        .where(filter=FieldFilter('at', '<', before))
        .order_by('at', direction='DESCENDING')
        .limit(TAIL_SWEEP_LIMIT)
        .stream()
    )
    cleared = 0
    for row in rows:
        if TAIL_FIELD in (row.to_dict() or {}):
            row.reference.update({TAIL_FIELD: firestore.DELETE_FIELD})
            cleared += 1
    return cleared
