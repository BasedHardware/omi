"""Loopback proofs for bind/wipe contention and bounded transcript scrubbing."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest

from database import conversations, recurring_voices, recurring_voice_assignments, recurring_voice_privacy
from database import speaker_auto_enroll
from database.legal_holds import DestructiveOperationInProgress
from tests.integration.test_batch_pipeline_deletion_firestore import state  # noqa: F401

pytestmark = pytest.mark.integration
OWNER = [1.0, *([0.0] * 255)]
VOICE = [0.0, 1.0, *([0.0] * 254)]


@pytest.fixture
def recurring(state, monkeypatch):
    store, uid, user, *_ = state
    monkeypatch.setattr(recurring_voices.encryption, 'derive_key', lambda _: bytes(32))
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda _: None)
    monkeypatch.setattr(conversations, 'record_speaker_review', lambda *a: None)
    now = datetime.now(timezone.utc).timestamp()
    profile = dict(
        state='recurring',
        entries=[dict(conversation_id=cid, at=now, seconds=30, vector=VOICE) for cid in ['source', 'second']],
    )
    blob = recurring_voices.seal(uid, 'v', profile)
    user.update(
        dict(
            private_cloud_sync_enabled=True,
            save_other_voice_profiles=True,
            speaker_embedding=OWNER,
            **{recurring_voices.INDEX: {'v': recurring_voices.pools.pool_token(blob)}},
        )
    )
    user.collection(recurring_voices.COLLECTION).document('v').set({'sealed': blob})
    user.collection('people').document('p').set(
        dict(speaker_embedding=VOICE, speech_samples=['synthetic'], speech_samples_version=3)
    )
    segments = [
        dict(
            id='s1',
            start=0,
            end=30,
            text='synthetic',
            is_user=False,
            speaker_id=1,
            speaker_id_scope='final:batch:conversation:source',
            recurring_voice_id='v',
        )
    ]
    user.collection('conversations').document('source').set(
        dict(private_cloud_sync_enabled=True, transcript_segments=segments)
    )
    return store.client, uid, user, segments


@pytest.mark.parametrize('order', ['wipe_first', 'bind_first'])
def test_bind_racing_account_wipe_leaves_no_profile(recurring, monkeypatch, order):
    client, uid, user, _ = recurring

    def bind():
        return conversations.assign_conversation_speaker(
            uid, 'source', person_id='p', segment_ids=['s1'], firestore_client=client
        )

    def wipe():
        client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
        for sub in user.collections():
            for row in sub.stream():
                row.reference.delete()
        user.delete()

    if order == 'wipe_first':
        # The collection has already been enumerated/cleared while an assignment
        # still has a valid source and person to act on.
        client.collection('account_deletions').document(uid).set({'wipe_status': 'running'})
        for row in user.collection(recurring_voices.COLLECTION).stream():
            row.reference.delete()
        with pytest.raises(DestructiveOperationInProgress):
            bind()
        wipe()
    else:
        prepared, resume, wiping = Event(), Event(), Event()
        original = recurring_voice_assignments.prepare

        def pause(*args, **kwargs):
            result = original(*args, **kwargs)
            prepared.set()
            assert resume.wait(15), 'bind test timed out'
            return result

        def concurrent_wipe():
            wiping.set()
            wipe()

        monkeypatch.setattr(recurring_voice_assignments, 'prepare', pause)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assignment = pool.submit(bind)
            try:
                assert prepared.wait(15)
                erasure = pool.submit(concurrent_wipe)
                assert wiping.wait(15)
                assert not erasure.done()
            finally:
                resume.set()
            assignment.result(timeout=30)
            erasure.result(timeout=30)
    assert not user.get().exists
    assert list(user.collection(recurring_voices.COLLECTION).stream()) == []


def test_manual_binding_bumps_people_generation_atomically(recurring):
    client, uid, user, _ = recurring
    from database.people_generation import generation_ref

    head = generation_ref(user)
    before = (head.get().to_dict() or {}).get('generation', 0)
    conversations.assign_conversation_speaker(uid, 'source', person_id='p', segment_ids=['s1'], firestore_client=client)
    assert head.get().to_dict()['generation'] == before + 1
    row = user.collection(recurring_voices.COLLECTION).document('v').get().to_dict()
    assert recurring_voices.open_profile(uid, 'v', row['sealed'])['bound_person_id'] == 'p'


@pytest.mark.parametrize('setting', ['save_other_voice_profiles', 'private_cloud_sync_enabled'])
def test_optout_scrubs_paged_transcripts_preserving_concurrent_edits_and_encoding(recurring, monkeypatch, setting):
    client, uid, user, segments = recurring
    monkeypatch.setattr(recurring_voice_privacy, 'SCRUB_PAGE_SIZE', 2)
    for i, level in enumerate(['standard', 'enhanced', 'standard', 'enhanced', 'standard']):
        raw = conversations.encode_conversation_for_write(uid, {'transcript_segments': segments}, level)
        user.collection('conversations').document(f'c{i}').set(dict(raw, data_protection_level=level))
    # Introduce an edit after ID enumeration and before the scrub transaction.
    original = recurring_voice_privacy.transcript_pointer._client.run_transactional
    edited = False

    def concurrent_edit(db, callback, **kwargs):
        nonlocal edited
        if callback.to_wrap.__name__ == 'scrub' and not edited:
            edited = True
            changed = [{**segments[0], 'text': 'concurrent correction', 'person_id': 'p'}]
            user.collection('conversations').document('c0').update({'transcript_segments': changed})
        return original(db, callback, **kwargs)

    monkeypatch.setattr(recurring_voice_privacy.transcript_pointer._client, 'run_transactional', concurrent_edit)
    speaker_auto_enroll.update_privacy(uid, {setting: False}, firestore_client=client)
    assert user.get().to_dict()[recurring_voices.INDEX] == {}
    assert list(user.collection(recurring_voices.COLLECTION).stream()) == []
    for snapshot in user.collection('conversations').stream():
        raw = snapshot.to_dict()
        decoded = conversations.decode_transcript_segments_verified(
            uid, raw['transcript_segments'], bool(raw.get('transcript_segments_compressed'))
        )
        assert all('recurring_voice_id' not in s for s in decoded)
        if snapshot.id == 'c0':
            assert decoded[0]['text'] == 'concurrent correction' and decoded[0]['person_id'] == 'p'
        if raw.get('data_protection_level') == 'enhanced':
            assert isinstance(raw['transcript_segments'], str)
        else:
            assert isinstance(raw['transcript_segments'], bytes)
    # Retry is harmless, including after the profile authority has been cleared.
    speaker_auto_enroll.update_privacy(uid, {setting: False}, firestore_client=client)


@pytest.fixture
def processing(recurring, monkeypatch):
    from database import dream_dirty

    client, uid, user, segments = recurring
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(dream_dirty, 'mark_dirty', lambda *a, **kw: None)
    return client, uid, user, segments


@pytest.mark.parametrize('writer', ['persist_processing_result_with_lifecycle', 'upsert_conversation_with_lifecycle'])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('setting', ['save_other_voice_profiles', 'private_cloud_sync_enabled'])
def test_scrub_then_late_processing_save_cannot_restore_pointer(processing, setting, level, writer):
    client, uid, user, segments = processing
    user.collection('conversations').document('source').update({'data_protection_level': level})
    # The processor already holds the final pass result when consent changes.
    late = dict(id='source', transcript_segments=segments, data_protection_level=level, status='completed')
    speaker_auto_enroll.update_privacy(uid, {setting: False}, firestore_client=client)
    assert list(user.collection(recurring_voices.COLLECTION).stream()) == []
    result = getattr(conversations, writer)(uid, late)
    if writer == 'persist_processing_result_with_lifecycle':
        assert result is True
    raw = user.collection('conversations').document('source').get().to_dict()
    decoded = conversations.decode_transcript_segments_verified(
        uid, raw['transcript_segments'], raw['transcript_segments_compressed']
    )
    assert decoded[0]['text'] == 'synthetic' and 'recurring_voice_id' not in decoded[0]
    assert isinstance(raw['transcript_segments'], str if level == 'enhanced' else bytes)


def test_processing_save_contending_with_optout_is_scrubbed(processing, monkeypatch):
    client, uid, user, segments = processing
    checked, resume, withdrawing = Event(), Event(), Event()
    original = recurring_voices.active_ids

    def pause(transaction, owner):
        result = original(transaction, owner)
        checked.set()
        assert resume.wait(15), 'processing test timed out'
        return result

    def withdraw():
        withdrawing.set()
        speaker_auto_enroll.update_privacy(uid, {'save_other_voice_profiles': False}, firestore_client=client)

    monkeypatch.setattr(recurring_voices, 'active_ids', pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        saving = pool.submit(
            conversations.persist_processing_result_with_lifecycle,
            uid,
            dict(id='source', transcript_segments=segments, data_protection_level='enhanced', status='completed'),
        )
        try:
            assert checked.wait(15)
            optout = pool.submit(withdraw)
            assert withdrawing.wait(15)
            assert not optout.done()
        finally:
            resume.set()
        assert saving.result(timeout=30) is True
        optout.result(timeout=30)
    raw = user.collection('conversations').document('source').get().to_dict()
    decoded = conversations.decode_transcript_segments_verified(
        uid, raw['transcript_segments'], raw['transcript_segments_compressed']
    )
    assert decoded[0]['text'] == 'synthetic' and 'recurring_voice_id' not in decoded[0]
    assert list(user.collection(recurring_voices.COLLECTION).stream()) == []
