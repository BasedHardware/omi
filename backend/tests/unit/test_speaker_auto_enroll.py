"""Explicit consent, measured evidence, encrypted pools and publication fences."""

import json
import struct
import asyncio
import io
import time
import wave
from copy import deepcopy
from dataclasses import replace
from unittest.mock import MagicMock
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from database import speaker_auto_enroll as db
from database import conversations as conversations_db
from database import users as users_db
from database import person_aliases
from database.speaker_learning_fields import project_person_learning
from models.other import Person
from models.transcript_segment import TranscriptSegment
from routers.listen.speakers import SpeakerMatcher
from utils.conversations import speaker_resolution
from utils.sync import speaker_identity
from utils.speakers import auto_enroll as p
from utils.stt.voiceprints import usable_person_voiceprint
from utils import speaker_auto_enroll as workflow
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID, PID, CID = 'owner-a', 'person-a', 'conversation-a'
NOW = datetime.now(timezone.utc)
OWNER = [1.0, *([0.0] * 255)]
VOICE = [0.0, 1.0, *([0.0] * 254)]
CONTEXT = dict(private_cloud_sync_enabled=True, save_other_voice_profiles=True, speaker_embedding=OWNER)


def authorized_context(blob):
    return {**CONTEXT, p.AUTHORITY_FIELD: {PID: p.pool_token(blob)}}


def source():
    segments = [
        dict(
            id=f's{i}',
            start=i * 6.0,
            end=i * 6.0 + 5,
            speaker_id=1,
            speaker_id_scope='capture-a',
            person_id=PID,
            is_user=False,
        )
        for i in range(2)
    ]
    return {
        'private_cloud_sync_enabled': True,
        'transcript_segments': segments,
        'manual_speaker_assignments': {
            'generation': 1,
            'speakers': {'1': dict(person_id=PID, is_user=False, use_for_speech_training=True, generation=1)},
        },
    }


def evidence(conversation=None):
    conversation = conversation or source()
    return {
        s['id']: dict(binding=p.binding(s), window=[s['start'], s['end']], seconds=5, vector=VOICE)
        for s in conversation['transcript_segments']
    }


def contribution(cid=CID, at=None, vector=VOICE):
    return dict(
        conversation_id=cid,
        segment_ids=['s0', 's1'],
        vector=vector,
        model=p.MODEL,
        seconds=10,
        generation=1,
        **({'at': at} if at is not None else {}),
    )


def pick(c=None, e=None, owner=OWNER):
    return p.candidate(c or source(), PID, ['s0', 's1'], evidence() if e is None else e, owner)


def test_clean_explicit_disjoint_voice_is_accepted():
    chosen = pick()
    assert chosen['seconds'] == 10 and chosen['segment_ids'] == ['s0', 's1']
    assert chosen['vector'] == VOICE


def owner_near_pair():
    a = 0.499
    b = np.sqrt(1 - a * a)
    c = (0.66 - a * a) / b
    return ([a, b, 0.0, *([0.0] * 253)], [a, c, np.sqrt(1 - a * a - c * c), *([0.0] * 253)])


def test_owner_exclusion_checks_candidate_and_decayed_pool_averages():
    first, second = owner_near_pair()
    assert p.owner_safe(first, OWNER) and p.owner_safe(second, OWNER)
    e = evidence()
    e['s0']['vector'], e['s1']['vector'] = first, second
    assert pick(e=e) is None
    entries = [contribution('first', NOW.timestamp(), first), contribution('second', NOW.timestamp(), second)]
    assert p.vector(entries, NOW.timestamp(), OWNER) is None
    person = dict(id=PID, **{p.POOL_FIELD: p.seal(UID, PID, entries)})
    assert p.usable(UID, person, authorized_context(person[p.POOL_FIELD])) is None


def test_new_conversation_cannot_publish_an_owner_like_roster_average(store):
    first, second = owner_near_pair()
    person = store.rows[('users', UID, 'people', PID)]
    before = p.seal(UID, PID, [contribution('previous', NOW.timestamp(), first)])
    person[p.POOL_FIELD] = before
    e = evidence()
    for row in e.values():
        row['vector'] = second
    assert pick(e=e) is not None
    assert not db.publish(UID, PID, CID, ['s0', 's1'], e, NOW, 1, firestore_client=store)
    assert person[p.POOL_FIELD] == before


@pytest.mark.parametrize('case', ['valid', 'optout', 'off_on', 'owner_changed', 'read_failure', 'kill'])
def test_live_cached_derived_profiles_recheck_privacy_and_retract_automatic_maps(store, monkeypatch, case):
    async def call(fn, *args):
        if case == 'read_failure':
            raise OSError('authority unavailable')
        return fn(*args, firestore_client=store)

    emitted = []
    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID),
        persistence=SimpleNamespace(call=call),
        state=SimpleNamespace(speaker_map_dirty=False),
        emit_speaker_suggestion=lambda *args, **kwargs: emitted.append((args, kwargs)),
    )
    matcher = SpeakerMatcher(host)
    blob = p.seal(UID, PID, [contribution(at=NOW.timestamp())])
    store.rows[('users', UID)][p.AUTHORITY_FIELD] = {PID: p.pool_token(blob)}
    matcher.person_embeddings = {
        PID: dict(
            embedding=VOICE,
            name='Synthetic',
            auto_enrolled=True,
            **p.cache_authority(UID, dict(id=PID, **{p.POOL_FIELD: blob}), CONTEXT),
        ),
        'legacy': dict(embedding=VOICE, name='Independent audio'),
    }
    matcher.speaker_to_person = {7: (PID, 'Synthetic'), 8: (PID, 'Synthetic')}
    matcher._mapping_origin = {7: 'automatic', 8: 'manual'}
    matcher._voice_segments[7] = 's7'
    user = store.rows[('users', UID)]
    if case == 'optout':
        user['save_other_voice_profiles'] = False
    elif case == 'off_on':
        user[db.PRIVACY_VERSION] = 2
    elif case == 'owner_changed':
        user['speaker_embedding'] = VOICE
    elif case == 'kill':
        monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'false')
    asyncio.run(matcher.refresh_enrollment_authority())
    assert (PID in matcher.person_embeddings) is (case == 'valid')
    assert (7 in matcher.speaker_to_person) is (case == 'valid')
    assert 8 in matcher.speaker_to_person and 'legacy' in matcher.person_embeddings
    assert bool(emitted) is (case != 'valid')


@pytest.mark.parametrize(
    'case',
    [
        'automatic',
        'carried',
        'no_training',
        'owner',
        'foreign_overlap',
        'stale',
        'short',
        'unmeasured',
        'mixed',
        'dimensions',
        'overlap',
    ],
)
def test_invalid_evidence_abstains(case):
    c, e = source(), evidence()
    d = c['manual_speaker_assignments']['speakers']['1']
    if case == 'automatic':
        c['manual_speaker_assignments'] = {}
    elif case == 'carried':
        d['source'] = 'carried'
    elif case == 'no_training':
        d['use_for_speech_training'] = False
    elif case == 'owner':
        e['s0']['vector'] = OWNER
    elif case == 'foreign_overlap':
        c['transcript_segments'].append(dict(id='foreign', start=1, end=9, speaker_id=2, speaker_id_scope='capture-a'))
    elif case == 'stale':
        c['transcript_segments'][0]['start'] = 0.1
    elif case == 'short':
        e.pop('s1')
    elif case == 'unmeasured':
        e['s0']['seconds'] = 0
    elif case == 'mixed':
        e['s1']['vector'] = [-v for v in VOICE]
    elif case == 'dimensions':
        e['s1']['vector'] = [1, 0]
    elif case == 'overlap':
        e['s1']['window'] = [4, 9]
    assert pick(c, e) is None


@pytest.mark.parametrize('owner', [None, [], [1, 0], [float('nan')] * 256])
def test_missing_or_incompatible_owner_abstains(owner):
    assert pick(owner=owner) is None


def test_cache_requires_model_measurement_and_exact_binding():
    c = source()
    h = dict(
        v=1,
        ids=['s0', 's1'],
        durations=[5, 5],
        dim=256,
        enrollment_model=p.MODEL,
        enrollment_binding_version=2,
        evidence_seconds={'s0': 5, 's1': 5},
        enrollment_bindings={
            k: {field: value for field, value in row.items() if field in ('binding', 'window')}
            for k, row in evidence(c).items()
        },
    )

    def encode():
        header = json.dumps(h).encode()
        return struct.pack('>I', len(header)) + header + np.array([VOICE, VOICE], dtype='<f2').tobytes()

    assert pick(c, p.decode_evidence(encode())) is not None
    h.pop('enrollment_model')
    assert p.decode_evidence(encode()) == {}
    assert p.decode_evidence(b'invalid') == {}


def test_cache_writer_does_not_stamp_an_incompatible_embedding_model():
    payload = speaker_resolution.encode_cache(
        {'s0': (5.0, np.ones(64))}, {'s0': 5.0}, {'s0': {'binding': 'bound', 'window': [0, 5]}}
    )
    size = struct.unpack('>I', payload[:4])[0]
    header = json.loads(payload[4 : 4 + size])
    assert 'enrollment_model' not in header and p.decode_evidence(payload) == {}


def test_enrollment_binding_records_the_pcm_crop_not_the_original_placement(monkeypatch):
    start = NOW.timestamp()
    rate = speaker_resolution.SAMPLE_RATE
    pcm = np.arange(20 * rate, dtype=np.int16).tobytes()
    clips = []

    def embed(data, **kwargs):
        with wave.open(io.BytesIO(data), 'rb') as audio:
            clips.append(audio.readframes(audio.getnframes()))
        return np.asarray(VOICE)

    monkeypatch.setattr(speaker_resolution, 'iter_audio_chunk_pcm', lambda *args, **kwargs: iter([(start, pcm)]))
    monkeypatch.setattr(speaker_resolution, 'extract_embedding_from_bytes', embed)
    segment = TranscriptSegment(id='wide', start=0, end=30, text='Synthetic speech.', speaker_id=1, is_user=False)
    placements = {'wide': SimpleNamespace(window=(start, start + 30))}
    cache, seconds, measured = {}, {}, {}
    count, _ = speaker_resolution._embed_missing(
        UID,
        SimpleNamespace(id=CID, started_at=NOW),
        [segment],
        cache,
        time.monotonic() + 60,
        placements=placements,
        evidence_seconds=seconds,
        measured_windows=measured,
    )
    assert count == 1 and clips == [pcm[int(2.5 * rate) * 2 : int(17.5 * rate) * 2]]
    assert measured['wide'] == (start + 2.5, start + 17.5)
    bindings = p.evidence_bindings([segment], {'wide': 'wide'}, placements, measured, {})
    decoded = p.decode_evidence(speaker_resolution.encode_cache(cache, seconds, bindings))
    assert decoded['wide']['window'] == [start + 2.5, start + 17.5]
    assert decoded['wide']['seconds'] == 15
    assert p.evidence_bindings([segment], {'wide': 'wide'}, placements, {}, decoded) == bindings
    placements['wide'].window = (start + 1, start + 31)
    assert p.evidence_bindings([segment], {'wide': 'wide'}, placements, {}, decoded) == {}


def test_cache_writer_only_grants_authority_to_fresh_or_unchanged_bound_vectors():
    bindings = {'s0': {'binding': 'current', 'window': [0, 5]}}
    value = (5, np.asarray(VOICE))
    cache = {'s0': value}
    assert p.accepted_bindings(bindings, cache, dict(cache), {}) == {}
    prior = {'s0': {'binding': 'old', 'window': [0, 5]}}
    assert p.accepted_bindings(bindings, cache, dict(cache), prior) == {}
    assert p.accepted_bindings(bindings, cache, dict(cache), bindings) == bindings
    assert p.accepted_bindings(bindings, cache, {}, {}) == bindings


def test_candidate_keeps_the_thirty_second_budget_with_fifteen_second_clips():
    c = source()
    c['transcript_segments'] = [
        dict(c['transcript_segments'][0], id=f's{i}', start=i * 12, end=i * 12 + 11) for i in range(3)
    ]
    e = {
        s['id']: dict(binding=p.binding(s), window=[s['start'], s['end']], seconds=11, vector=VOICE)
        for s in c['transcript_segments']
    }
    chosen = pick(c, e)
    assert chosen['seconds'] == 22 and chosen['segment_ids'] == ['s0', 's1']


def test_encryption_is_owner_and_person_bound_and_kill_switch_stops_use(monkeypatch):
    blob = p.seal(UID, PID, [contribution(at=NOW.timestamp())])
    assert 'vector' not in blob and CID not in blob
    assert p.open_pool('different-owner', PID, blob) == []
    assert p.open_pool(UID, 'different-person', blob) == []
    person = dict(id=PID, **{p.POOL_FIELD: blob})
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=authorized_context(blob)) == VOICE
    assert usable_person_voiceprint(person, uid=UID) is None
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=authorized_context(blob)) is None
    assert p.retract(UID, PID, blob, [CID], ['s0'])


def test_independent_manual_audio_replacement_cannot_be_shadowed_by_old_pool():
    blob = p.seal(UID, PID, [contribution(at=NOW.timestamp())])
    replacement = [0.0, 0.0, 1.0, *([0.0] * 253)]
    person = dict(
        id=PID,
        speaker_embedding=replacement,
        speech_samples=['synthetic.wav'],
        speech_samples_version=3,
        **{p.POOL_FIELD: blob},
    )
    assert p.usable(UID, person, authorized_context(blob)) is None
    assert usable_person_voiceprint(person, uid=UID, auto_enroll_allowed=authorized_context(blob)) == replacement


def test_retraction_clears_opaque_pool_so_key_recovery_cannot_resurrect_it():
    blob = p.seal('old-key-owner', PID, [contribution(at=NOW.timestamp())])
    assert p.open_pool(UID, PID, blob) == []
    update = p.retract(UID, PID, blob, [CID], ['s0'])
    assert update[p.POOL_FIELD] != blob
    assert p.open_pool(UID, PID, update[p.POOL_FIELD]) == []


def test_pool_caps_decay_expiration_refresh_and_incompatible_replacement():
    now = NOW.timestamp()
    entries = []
    for i in range(7):
        entries = p.refresh(entries, contribution(str(i)), now + i)
    assert len(entries) == 5 and [e['conversation_id'] for e in entries] == ['2', '3', '4', '5', '6']
    retried = p.refresh(entries, contribution('6'), now + 30)
    assert len(retried) == 5 and retried[-1]['at'] == now + 6
    assert p.refresh(entries, contribution('different', vector=[-v for v in VOICE]), now + 10) is None
    assert p.vector(entries, now + p.MAX_AGE_SECONDS + 7, OWNER) is None
    other = [0.0, 0.8, 0.6, *([0.0] * 253)]
    result = p.vector([contribution('old', now - p.HALF_LIFE_SECONDS), contribution('new', now, other)], now, OWNER)
    assert result[2] / result[1] == pytest.approx(1.2 / 2.6)


@pytest.fixture
def store():
    return StrictFirestore(
        {
            ('users', UID): dict(
                private_cloud_sync_enabled=True, save_other_voice_profiles=True, speaker_embedding=OWNER
            ),
            ('users', UID, 'people', PID): dict(id=PID, updated_at=NOW, speech_samples=[]),
            ('users', UID, 'conversations', CID): source(),
        }
    )


def publish(store):
    return db.publish(UID, PID, CID, ['s0', 's1'], evidence(), NOW, 1, firestore_client=store)


@pytest.mark.parametrize(
    'kind', ['correction', 'conversation_delete', 'person_delete', 'dismiss', 'partial_retraction']
)
@pytest.mark.parametrize('killed', [False, True])
def test_revocation_invalidates_cached_live_sync_and_stale_loads_atomically(store, monkeypatch, kind, killed):
    assert publish(store)
    path = ('users', UID, 'people', PID)
    if kind == 'partial_retraction':
        store.rows[('users', UID, 'conversations', 'other-source')] = source()
        assert db.publish(
            UID,
            PID,
            'other-source',
            ['s0', 's1'],
            evidence(),
            store.rows[path]['updated_at'],
            1,
            firestore_client=store,
        )
    person = deepcopy(store.rows[path])
    before = db.context(UID, firestore_client=store)
    cached = dict(
        embedding=p.usable(UID, person, before),
        name='Synthetic',
        auto_enrolled=True,
        **p.cache_authority(UID, person, before),
    )
    assert p.cached_authorized(PID, cached, before)
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    extractor = MagicMock(return_value=np.asarray(VOICE))
    deps = replace(
        speaker_identity._DEFAULT_DEPS,
        speaker_embedding_configured=lambda: True,
        collect_speaker_audio=lambda *args: SimpleNamespace(clips=[(b'fake-audio', 10)], available_seconds=10),
        extract_embedding_from_bytes=extractor,
        compare_embeddings=lambda *args: 0.0,
        detect_speaker_from_text=lambda *args, **kwargs: None,
    )
    cache = speaker_identity.PersonEmbeddingsCache(True)
    cache[PID] = cached
    first = TranscriptSegment(id='before', start=0, end=10, text='Synthetic speech.', speaker_id=0, is_user=False)
    speaker_identity.identify_speakers_for_segments([first], b'audio', cache, UID, dependencies=deps)
    assert extractor.call_count == 1 and first.person_id == PID
    if killed:
        monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'false')
    if kind == 'correction':
        store.rows[('users', UID, 'people', 'replacement')] = {'id': 'replacement', 'name': 'Replacement'}
        conversations_db.assign_conversation_speaker(
            UID, CID, person_id='replacement', segment_ids=['s0'], firestore_client=store
        )
    elif kind in {'conversation_delete', 'partial_retraction'}:
        db.retract_conversation(UID, CID, firestore_client=store)
    elif kind == 'person_delete':
        db.revoke_person(UID, PID, firestore_client=store)
        assert not db.publish(
            UID, PID, CID, ['s0', 's1'], evidence(), store.rows[path]['updated_at'], 1, firestore_client=store
        )
    else:
        person_aliases.dismiss_person_transaction.to_wrap(
            store.transaction(), store.collection('users').document(UID).collection('people').document(PID)
        )
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'true')
    after = db.context(UID, firestore_client=store)
    assert after[db.PRIVACY_VERSION] == before[db.PRIVACY_VERSION]
    assert not p.cached_authorized(PID, cached, after)
    # A people snapshot from before revocation cannot be paired with newer
    # authority to bless its stale vector at load time.
    assert p.usable(UID, person, after) is None

    async def call(fn, *args):
        return fn(*args, firestore_client=store)

    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID),
        persistence=SimpleNamespace(call=call),
        state=SimpleNamespace(speaker_map_dirty=False),
        emit_speaker_suggestion=lambda *args, **kwargs: None,
    )
    matcher = SpeakerMatcher(host)
    matcher.person_embeddings[PID] = cached
    matcher.speaker_to_person = {7: (PID, 'Synthetic'), 8: (PID, 'Synthetic')}
    matcher._mapping_origin = {7: 'automatic', 8: 'manual'}
    asyncio.run(matcher.refresh_enrollment_authority())
    assert PID not in matcher.person_embeddings and 7 not in matcher.speaker_to_person
    assert 8 in matcher.speaker_to_person
    later = TranscriptSegment(id='after', start=0, end=10, text='Synthetic speech.', speaker_id=0, is_user=False)
    speaker_identity.identify_speakers_for_segments([later], b'audio', cache, UID, dependencies=deps)
    assert extractor.call_count == 1 and later.person_id is None
    if kind == 'partial_retraction':
        fresh = store.rows[path]
        assert p.usable(UID, fresh, after) == VOICE
        assert p.cached_authorized(PID, {**cached, **p.cache_authority(UID, fresh, after)}, after)


@pytest.mark.parametrize('timing', ['embedding', 'text'])
@pytest.mark.parametrize('speaker_id', [0, None])
def test_sync_rechecks_revocation_after_io(store, monkeypatch, timing, speaker_id):
    assert publish(store)
    person = store.rows[('users', UID, 'people', PID)]
    context = db.context(UID, firestore_client=store)
    cache = speaker_identity.PersonEmbeddingsCache(True)
    cache[PID] = dict(
        embedding=p.usable(UID, person, context),
        name='Synthetic',
        auto_enrolled=True,
        **p.cache_authority(UID, person, context),
    )
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)

    def extract(*args):
        if timing == 'embedding':
            db.retract_conversation(UID, CID, firestore_client=store)
        return np.asarray(VOICE)

    def detect(*args, **kwargs):
        if timing == 'text':
            db.retract_conversation(UID, CID, firestore_client=store)
        return None

    deps = replace(
        speaker_identity._DEFAULT_DEPS,
        speaker_embedding_configured=lambda: True,
        collect_speaker_audio=lambda *args: SimpleNamespace(clips=[(b'fake-audio', 10)], available_seconds=10),
        extract_embedding_from_bytes=extract,
        compare_embeddings=lambda *args: 0.0,
        detect_speaker_from_text=detect,
    )
    segment = TranscriptSegment(
        id='race', start=0, end=10, text='Synthetic speech.', speaker_id=speaker_id, is_user=False
    )
    other = TranscriptSegment(id='other', start=20, end=30, text='Other speech.', speaker_id=1, is_user=False)
    speaker_identity.identify_speakers_for_segments([segment, other], b'audio', cache, UID, dependencies=deps)
    assert segment.person_id is None and other.person_id is None


def test_live_final_authority_rechecks_after_continuity_io(store):
    assert publish(store)
    person = store.rows[('users', UID, 'people', PID)]
    context = db.context(UID, firestore_client=store)

    async def call(fn, *args):
        return fn(*args, firestore_client=store)

    async def authorize(*args, **kwargs):
        db.retract_conversation(UID, CID, firestore_client=store)
        return (False, set()), None

    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID),
        persistence=SimpleNamespace(call=call),
        state=SimpleNamespace(speaker_map_dirty=False),
        emit_speaker_suggestion=lambda *args, **kwargs: None,
    )
    matcher = SpeakerMatcher(host)
    matcher.person_embeddings[PID] = dict(
        embedding=p.usable(UID, person, context),
        auto_enrolled=True,
        **p.cache_authority(UID, person, context),
    )
    matcher.continuity.authorize_roster = authorize
    asyncio.run(matcher._final_authority({}, include_short=True))
    assert PID not in matcher.person_embeddings


def test_cached_authority_expires_when_the_first_contribution_expires():
    now = datetime.now(timezone.utc).timestamp()
    blob = p.seal(UID, PID, [contribution('old', now - p.MAX_AGE_SECONDS + 60), contribution('new', now)])
    person = dict(id=PID, **{p.POOL_FIELD: blob})
    context = authorized_context(blob)
    cached = dict(embedding=VOICE, **p.cache_authority(UID, person, context))
    assert cached['enrollment_expires_at'] == pytest.approx(now + 60)
    assert p.cached_authorized(PID, cached, context, now=now)
    assert not p.cached_authorized(PID, cached, context, now=now + 60)
    # A mutation to a different person's pool does not revoke this one.
    unrelated = {**context, **p.authority_after(context, {'other-person': 'opaque-new-pool'})}
    assert p.cached_authorized(PID, cached, unrelated, now=now)


def test_publication_and_retraction_are_strict_transactions(store):
    assert publish(store)
    person_path = ('users', UID, 'people', PID)
    assert p.open_pool(UID, PID, store.rows[person_path][p.POOL_FIELD])[0]['seconds'] == 10
    assert store.rows[('users', UID)][db.OWNER_INDEX] == [PID]
    db.retract_conversation(UID, CID, firestore_client=store)
    assert p.open_pool(UID, PID, store.rows[person_path][p.POOL_FIELD]) == []
    assert not publish(store)


def test_survivor_deletion_retracts_donor_even_after_its_source_index_is_gone(store, monkeypatch):
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    store.rows[('users', UID)][db.OWNER_INDEX] = [PID]
    store.rows[('users', UID, 'people', PID)][p.POOL_FIELD] = p.seal(
        UID,
        PID,
        [contribution('premerge-donor', NOW.timestamp())],
    )
    store.rows[('users', UID, 'conversations', CID)]['sync_merged_from'] = ['premerge-donor']
    # There was no post-merge tag on the survivor; its own index is empty.
    # Upstream donor deletion may have failed or removed metadata without this pool.
    db.retract_conversation(UID, CID, firestore_client=store)
    assert p.open_pool(UID, PID, store.rows[('users', UID, 'people', PID)][p.POOL_FIELD]) == []
    assert store.rows[('users', UID, 'conversations', CID)]['deleted'] is True


@pytest.mark.parametrize(
    'race',
    [
        'sync_off',
        'save_off',
        'source_sync_off',
        'correction',
        'person_version',
        'person_deleted',
        'conversation_deleted',
        'locked',
        'discarded',
        'tombstone',
        'account_deletion',
        'kill',
    ],
)
def test_publication_rechecks_every_authority(store, monkeypatch, race):
    user = store.rows[('users', UID)]
    person = store.rows[('users', UID, 'people', PID)]
    c = store.rows[('users', UID, 'conversations', CID)]
    if race == 'sync_off':
        user['private_cloud_sync_enabled'] = False
    elif race == 'save_off':
        user['save_other_voice_profiles'] = False
    elif race == 'source_sync_off':
        c['private_cloud_sync_enabled'] = False
    elif race == 'correction':
        c['manual_speaker_assignments']['speakers']['1']['person_id'] = 'different'
    elif race == 'person_version':
        person['updated_at'] = None
    elif race == 'person_deleted':
        store.rows.pop(('users', UID, 'people', PID))
    elif race == 'conversation_deleted':
        store.rows.pop(('users', UID, 'conversations', CID))
    elif race in ('locked', 'discarded'):
        c['is_locked' if race == 'locked' else race] = True
    elif race == 'tombstone':
        store.rows[('users', UID, 'deleted_conversations', CID)] = {'deleted': True}
    elif race == 'account_deletion':
        store.rows[('account_deletions', UID)] = {'wipe_status': 'running'}
        with pytest.raises(Exception, match='account deletion'):
            publish(store)
        return
    elif race == 'kill':
        monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    assert not publish(store)
    assert not store.transactions[-1].updates


@pytest.mark.parametrize('setting', ['private_cloud_sync_enabled', 'save_other_voice_profiles'])
def test_privacy_optout_removes_indexed_pools_atomically(store, setting):
    assert publish(store)
    db.update_privacy(UID, {setting: False}, firestore_client=store)
    assert store.rows[('users', UID)][setting] is False
    assert store.rows[('users', UID)][db.OWNER_INDEX] == []
    assert store.rows[('users', UID, 'people', PID)][p.POOL_FIELD] is db.firestore.DELETE_FIELD


def test_privacy_off_on_cannot_resurrect_an_attempt_started_before_optout(store):
    db.update_privacy(UID, {'private_cloud_sync_enabled': False}, firestore_client=store)
    db.update_privacy(UID, {'private_cloud_sync_enabled': True}, firestore_client=store)
    assert not publish(store)


def test_assignment_correction_retracts_pool_with_receipt_even_when_killed(store, monkeypatch):
    assert publish(store)
    monkeypatch.setenv('SPEAKER_AUTO_ENROLL_ENABLED', 'off')
    store.rows[('users', UID, 'people', 'replacement')] = {'id': 'replacement', 'name': 'Synthetic'}
    conversations_db.assign_conversation_speaker(
        UID,
        CID,
        person_id='replacement',
        segment_ids=['s0'],
        firestore_client=store,
    )
    blob = store.rows[('users', UID, 'people', PID)][p.POOL_FIELD]
    assert p.open_pool(UID, PID, blob) == []
    row = store.rows[('users', UID, 'conversations', CID)]
    receipt = conversations_db.decode_manual_speaker_assignments(
        UID,
        row['manual_speaker_assignments'],
        bool(row.get('manual_speaker_assignments_compressed')),
    )
    assert receipt['segments']['s0']['person_id'] == 'replacement'


def test_readiness_projects_a_vector_without_claiming_audio_exists(store):
    assert publish(store)
    raw = store.rows[('users', UID, 'people', PID)]
    data = project_person_learning(UID, raw, firestore_client=store)
    assert data['voice_readiness'] == 'ready' and data['speech_samples'] == []
    person = Person(**{**data, 'name': 'Synthetic'})
    assert person.voice_readiness == 'ready' and person.voice_learning_state == 'learned'
    public = person.model_dump(mode='json')
    assert p.POOL_FIELD not in public and 'speaker_embedding' not in public


def test_no_training_overlap_cannot_ride_along_in_a_same_voice_clip():
    c, e = source(), evidence()
    c['transcript_segments'].append({**c['transcript_segments'][0], 'id': 'refused', 'start': 2, 'end': 4})
    c['manual_speaker_assignments']['segments'] = {
        'refused': dict(person_id=PID, generation=2, use_for_speech_training=False)
    }
    assert pick(c, e) is None


@pytest.mark.parametrize(
    'case', ['valid', 'owner', 'missing_owner', 'dimension', 'privacy_epoch', 'sync_off', 'source_off', 'tombstone']
)
def test_audio_fallback_rechecks_owner_retention_and_privacy_in_publication(store, monkeypatch, case):
    monkeypatch.setattr(users_db, 'db', store)
    owner = store.rows[('users', UID)]
    embedding = VOICE
    if case == 'owner':
        embedding = OWNER
    elif case == 'missing_owner':
        owner.pop('speaker_embedding')
    elif case == 'dimension':
        embedding = [1.0, 0.0]
    elif case == 'privacy_epoch':
        owner[db.PRIVACY_VERSION] = 1
    elif case == 'sync_off':
        owner['private_cloud_sync_enabled'] = False
    elif case == 'source_off':
        store.rows[('users', UID, 'conversations', CID)]['private_cloud_sync_enabled'] = False
    elif case == 'tombstone':
        store.rows[('users', UID, 'deleted_conversations', CID)] = {'deleted': True}
    user = store.collection('users').document(UID)
    result = users_db._replace_speech_profile_transaction(
        store.transaction(),
        user.collection('people').document(PID),
        NOW,
        {'speaker_embedding': embedding},
        user_ref=user,
        source=(UID, CID, ['s0', 's1'], 1),
        enrollment_privacy_version=0,
    )
    assert (result is not None) is (case == 'valid')
    assert bool(store.transactions[-1].updates) is (case == 'valid')


@pytest.mark.parametrize('case', ['valid', 'owner', 'missing_target', 'missing_owner', 'sync_off', 'source_off'])
def test_vector_worker_distinguishes_missing_evidence_from_authority_rejection(store, monkeypatch, case):
    rows = evidence()
    if case == 'owner':
        rows['s0']['vector'] = OWNER
    elif case == 'missing_target':
        for row in rows.values():
            row['binding'] = 'another-voice'
    elif case == 'missing_owner':
        store.rows[('users', UID)].pop('speaker_embedding')
    elif case == 'sync_off':
        store.rows[('users', UID)]['private_cloud_sync_enabled'] = False
    elif case == 'source_off':
        store.rows[('users', UID, 'conversations', CID)]['private_cloud_sync_enabled'] = False
    monkeypatch.setattr(workflow, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(workflow.users, 'get_person', lambda *args: store.rows[('users', UID, 'people', PID)])
    monkeypatch.setattr(
        workflow.conversations, 'get_conversation', lambda *args: store.rows[('users', UID, 'conversations', CID)]
    )
    monkeypatch.setattr(workflow, 'download_owner_evidence_cache', lambda *args: b'synthetic-cache')
    monkeypatch.setattr(workflow.policy, 'decode_evidence', lambda *args: rows)
    expected = {
        'valid': 'stored',
        'owner': 'rejected_quality',
        'missing_target': None,
        'missing_owner': 'rejected_embedding',
        'sync_off': 'disabled',
        'source_off': 'disabled',
    }
    assert workflow.enroll(UID, PID, CID, ['s0', 's1']) == expected[case]
