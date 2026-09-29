from database import conversations
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'translation-test-user'
CID = 'conversation'
PATH = ('users', UID, 'conversations', CID)


def store_with_segments(*segments):
    return StrictFirestore(
        {
            PATH: conversations.encode_conversation_for_write(
                UID,
                {
                    'id': CID,
                    'data_protection_level': 'standard',
                    'transcript_segments': list(segments),
                    'client_processing_projection': {'keep': True},
                },
                'standard',
            )
        }
    )


def read(store):
    return conversations.prepare_conversation_for_read(store.rows[PATH], UID)


def test_source_fence_priority_per_target_merge_and_projection_preservation(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    store = store_with_segments({'id': 's', 'text': 'Yến nói với bác năm 2025.', 'translations': []})
    write = lambda source, target, value, policy='legacy': conversations.materialize_translation(
        UID, CID, 's', source, target, value, policy_version=policy, firestore_client=store
    )
    assert write('wrong source', 'en', 'wrong') is None
    assert write('Yến nói với bác năm 2025.', 'en', 'Yến spoke with the elder in 2025.', 'viewed_v1')
    assert write('Yến nói với bác năm 2025.', 'fr', 'Yến a parlé avec son aîné.')
    assert write('Yến nói với bác năm 2025.', 'en', 'bad legacy output')
    doc = read(store)
    segment = doc['transcript_segments'][0]
    assert segment['text'] == 'Yến nói với bác năm 2025.'
    assert {item['lang']: item['text'] for item in segment['translations']} == {
        'en': 'Yến spoke with the elder in 2025.',
        'fr': 'Yến a parlé avec son aîné.',
    }
    assert doc['client_processing_projection'] == {'keep': True}
    assert conversations.translation_materialization_is_current(UID, doc, segment, 'en', 'viewed_v1')
    segment['translations'][0]['text'] = 'legacy overwrote the value'
    assert not conversations.translation_materialization_is_current(UID, doc, segment, 'en', 'viewed_v1')


def test_deleted_locked_or_removed_segments_reject_write(monkeypatch):
    monkeypatch.setenv('TRANSLATION_DEMAND_GATE_ENABLED', 'true')
    store = store_with_segments({'id': 's', 'text': 'năm', 'translations': []})
    for field in ('deleted', 'is_locked'):
        store.rows[PATH][field] = True
        assert (
            conversations.materialize_translation(
                UID, CID, 's', 'năm', 'en', 'year', policy_version='viewed_v1', firestore_client=store
            )
            is None
        )
        store.rows[PATH][field] = False
    assert (
        conversations.materialize_translation(
            UID, CID, 'removed', 'năm', 'en', 'year', policy_version='viewed_v1', firestore_client=store
        )
        is None
    )
