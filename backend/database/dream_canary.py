"""Only the reserved synthetic account may receive canary records."""

from datetime import datetime, timezone

from google.cloud import firestore

from config.dream_agent import canary_uid
from database._client import get_firestore_client
from database.conversations import _prepare_conversation_for_write
from database.dream_dirty import after_write, canary_writing
from database.helpers import prepare_for_write

RECORD_ID = 'dream-canary-conversation'


def ensure_synthetic_owner(uid, *, firestore_client=None):
    if not uid or uid != canary_uid():
        raise ValueError('dream_canary_configuration')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    owner = database.collection('users').document(uid)

    @firestore.transactional
    def ensure(tx):
        existing = owner.get(transaction=tx).to_dict()
        if existing is not None and existing.get('dream_canary') is not True:
            raise ValueError('dream_canary_existing_owner')
        if existing is None:
            tx.set(owner, {'dream_canary': True})

    ensure(database.transaction())


@prepare_for_write(data_arg_name='conversation_data', prepare_func=_prepare_conversation_for_write)
@after_write('conversations')
def write_record(uid, conversation_data):
    # Same serialization and dirty hook as processed product conversations.
    get_firestore_client().collection('users').document(uid).collection('conversations').document(RECORD_ID).set(
        conversation_data
    )


def seed(uid):
    ensure_synthetic_owner(uid)
    token = canary_writing.set(True)
    try:
        write_record(
            uid,
            {
                'id': RECORD_ID,
                'created_at': datetime.now(timezone.utc),
                'status': 'completed',
                'discarded': False,
                'has_photos': False,
                'data_protection_level': 'enhanced',
                'structured': {'title': 'Synthetic dream check', 'overview': 'A spelling check for an invented robot.'},
                'transcript_segments': [
                    {
                        'text': 'Robot Qorbi is spelled Qorbi. The notes incorrectly spell it Qorby.',
                        'speaker': 'SPEAKER_00',
                        'start': 0,
                        'end': 5,
                    }
                ],
            },
        )
    finally:
        canary_writing.reset(token)


def record_result(passed, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_canary_health').document('current')

    @firestore.transactional
    def update(tx):
        state = ref.get(transaction=tx).to_dict() or {}
        failures = 0 if passed else min(100, int(state.get('canary_failures', 0)) + 1)
        tx.set(ref, {'canary_failures': failures}, merge=True)
        return failures

    return update(database.transaction())
