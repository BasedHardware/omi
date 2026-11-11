"""Resolve private no-speech receipts and restore without audio or secrets.

Known receipts retain their exact fence. Prepared/unknown receipts first prove
this run's current closed shape, then fence the restore on the read revision.
"""

from collections import Counter
import time

from database import no_speech_terminal as terminal_db
from utils.conversations import no_speech_restore as lifecycle


def _snapshot(store, uid, cid):
    snapshot = store.client.collection('users').document(uid).collection('conversations').document(cid).get()
    return (snapshot.to_dict() or {}) if snapshot.exists else {}, terminal_db.revision(snapshot)


def undo_no_speech(store, entries, *, ledger, pace=0.0):
    outcomes = Counter()
    for entry in entries:
        try:
            expected_revision = entry.get('committed_revision')
            if not expected_revision or expected_revision == terminal_db.COMMITTED_REVISION_UNKNOWN:
                row, expected_revision = _snapshot(store, entry['uid'], entry['conversation_id'])
                marker = row.get(terminal_db.MARKER) or {}
                if (
                    marker.get('run_id') != entry['run_id']
                    or row.get('status') != 'completed'
                    or row.get('discarded') is not True
                    or row.get(terminal_db.TERMINAL_NO_DERIVED_EFFECTS_FIELD) is not True
                ):
                    raise terminal_db.NoSpeechConflict('not_matching_close')
                if not expected_revision:
                    raise terminal_db.NoSpeechConflict('committed_revision_unknown')
            lifecycle.restore_no_speech_capture(
                entry['uid'],
                entry['conversation_id'],
                expected_closed_revision=expected_revision,
                run_id=entry['run_id'],
                firestore_client=store.client,
            )
            outcomes['restored'] += 1
        except terminal_db.NoSpeechConflict as error:
            outcomes[str(error)] += 1
        except Exception:
            outcomes['write_error'] += 1
        if pace:
            time.sleep(pace)
    return dict(sorted(outcomes.items()))
