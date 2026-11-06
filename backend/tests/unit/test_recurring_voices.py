"""Behavioral privacy and precision contracts for recurring batch voices."""

from copy import deepcopy
from datetime import datetime, timezone

import numpy as np
import pytest

from config import batch_conversation_speakers as flags
from database import recurring_voices as db, speaker_auto_enroll
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.speakers import recurring_voices as p

OWNER = [1.0, *([0.0] * 255)]
VOICE = [0.0, 1.0, *([0.0] * 254)]
OTHER = [0.0, 0.0, 1.0, *([0.0] * 253)]
NOW = datetime.now(timezone.utc).timestamp()
PRINTS = {'user': OWNER}
CENTROIDS = {'a': {'embedding': VOICE, 'evidence_seconds': 30}, 'b': {'embedding': OWNER, 'evidence_seconds': 30}}


def evaluate(profiles=None, cid='c1', now=NOW, prints=PRINTS, clusters=CENTROIDS):
    return p.evaluate(clusters, prints, profiles or {}, cid, now)


def test_learn_promote_and_match_without_a_name_and_retry_deduplication():
    profiles, labels, events, _ = evaluate()
    assert events == ['created'] and labels['a'] == {}
    vid = next(iter(profiles))
    retry, _, _, _ = evaluate(profiles, now=NOW + 1)
    assert len(retry[vid]['entries']) == 1 and retry[vid]['entries'][0]['at'] == NOW
    recurring, labels, events, _ = evaluate(profiles, cid='c2', now=NOW + 10)
    assert events == ['promoted']
    assert recurring[vid]['state'] == 'recurring'
    assert labels['a'] == {'recurring_voice_id': vid}
    assert 'person_id' not in labels['a']


@pytest.mark.parametrize('change', ['no_owner', 'owner_voice', 'short', 'single', 'wrong_dimension', 'nan'])
def test_learning_qualification(change):
    clusters, prints = deepcopy(CENTROIDS), dict(PRINTS)
    if change == 'no_owner':
        prints = {}
    if change == 'owner_voice':
        clusters['a']['embedding'] = OWNER
    if change == 'short':
        clusters['a']['evidence_seconds'] = 29.99
    if change == 'single':
        clusters.pop('b')
    if change == 'wrong_dimension':
        clusters['a']['embedding'] = [1.0, 0.0]
    if change == 'nan':
        clusters['a']['embedding'] = [float('nan')] * 256
    assert not evaluate(prints=prints, clusters=clusters)[0]


def test_joint_margin_person_competes_and_two_profiles_abstain():
    profiles = evaluate()[0]
    profiles = evaluate(profiles, cid='c2')[0]
    vid = next(iter(profiles))
    _, labels, _, outcomes = evaluate(profiles, prints={**PRINTS, 'p': VOICE})
    assert labels['a'] == {} and 'abstained_margin' in outcomes
    profiles['competing'] = deepcopy(profiles[vid])
    _, labels, _, outcomes = evaluate(profiles)
    assert labels['a'] == {} and 'abstained_margin' in outcomes


def test_inconsistent_refresh_never_drifts_profile():
    profiles = evaluate()[0]
    vid = next(iter(profiles))
    near = np.array(VOICE) * 0.6 + np.array(OTHER) * 0.8  # distance .4: matches but cannot refresh
    clusters = deepcopy(CENTROIDS)
    clusters['a']['embedding'] = near.tolist()
    following = evaluate(profiles, cid='c2', clusters=clusters)[0]
    assert following[vid]['entries'] == profiles[vid]['entries']


def test_expiry_retraction_cap_and_three_candidate_limit():
    profiles = evaluate()[0]
    vid = next(iter(profiles))
    assert p.active(profiles[vid], NOW + p.CANDIDATE_AGE) is None
    recurring = evaluate(profiles, cid='c2', now=NOW + 1)[0]
    retracted = p.retract(recurring[vid], {'c1'})
    assert retracted['state'] == 'candidate'
    assert p.retract(retracted, {'c2'}) is None
    assert p.active(recurring[vid], NOW + 91 * 86400) is None
    clusters = {str(i): {'embedding': np.eye(256)[i + 1].tolist(), 'evidence_seconds': 30} for i in range(6)}
    assert len(evaluate(clusters=clusters)[0]) == 3
    full = {
        str(i): {**deepcopy(profiles[vid]), 'entries': [{**profiles[vid]['entries'][0], 'vector': OTHER}]}
        for i in range(25)
    }
    following, _, events, _ = evaluate(full)
    assert len(following) == 25 and 'evicted_cap' in events


def test_codec_binds_uid_and_voice_id_fails_closed(monkeypatch):
    monkeypatch.setattr(db.encryption, 'derive_key', lambda uid: bytes(32))
    profile = next(iter(evaluate()[0].values()))
    blob = db.seal('u', 'v', profile)
    assert db.open_profile('u', 'v', blob)['entries'] == profile['entries']
    assert db.open_profile('other', 'v', blob) is None
    assert db.open_profile('u', 'other', blob) is None
    assert db.open_profile('u', 'v', blob[:-3] + 'bad') is None
    assert db.open_profile('u', 'v', '') is None


def test_additive_field_is_persisted_without_changing_openapi():
    from models.developer_transcript import SimpleTranscriptSegment

    segment = TranscriptSegment(text='hello', start=0, end=30, is_user=False, recurring_voice_id='private-id')
    assert segment.model_dump()['recurring_voice_id'] == 'private-id'
    assert segment.model_dump(mode='json')['recurring_voice_id'] == 'private-id'
    assert 'recurring_voice_id' not in TranscriptSegment.model_json_schema()['properties']
    assert 'recurring_voice_id' not in SimpleTranscriptSegment(**segment.model_dump()).model_dump(mode='json')


@pytest.fixture
def store(monkeypatch):
    from contextlib import nullcontext
    from database import recurring_voice_privacy

    monkeypatch.setattr(recurring_voice_privacy, 'scrub_transcripts', lambda *a, **kw: None)

    monkeypatch.setattr(db, 'external_write_fence', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(db.encryption, 'derive_key', lambda uid: bytes(32))
    return StrictFirestore(
        {
            ('users', 'u'): {
                'private_cloud_sync_enabled': True,
                'save_other_voice_profiles': True,
                'speaker_embedding': OWNER,
            },
            ('users', 'u', 'conversations', 'c1'): {'private_cloud_sync_enabled': True},
        }
    )


def test_transaction_fences_concurrent_optout_source_change_and_deletion(store):
    from types import SimpleNamespace

    conversation = SimpleNamespace(
        id='c1',
        transcript_segments=[
            TranscriptSegment(text='x', start=0, end=30, is_user=False, speaker_id_scope='final:batch:x')
        ],
    )
    expected = db.checkpoint('u', 'c1', firestore_client=store)
    assert db.learn('u', conversation, CENTROIDS, PRINTS, expected, firestore_client=store) == {
        'a': {},
        'b': {'person_id': 'user'},
    }
    assert len(store.rows[('users', 'u')][db.INDEX]) == 1
    store.rows[('users', 'u', 'conversations', 'c1')]['deleted'] = True
    previous = deepcopy(store.rows)
    assert db.learn('u', conversation, CENTROIDS, PRINTS, expected, firestore_client=store) == {}
    assert store.rows == previous
    store.rows[('users', 'u', 'conversations', 'c1')].pop('deleted')
    speaker_auto_enroll.update_privacy('u', {'save_other_voice_profiles': False}, firestore_client=store)
    assert store.rows[('users', 'u')][db.INDEX] == {}
    assert ('users', 'u', db.COLLECTION, next(iter(previous[('users', 'u')][db.INDEX]))) not in store.rows
    assert db.learn('u', conversation, CENTROIDS, PRINTS, expected, firestore_client=store) == {}


def test_replays_cannot_extend_candidate_retention_or_create_more_than_three():
    profiles = evaluate()[0]
    vid = next(iter(profiles))
    following, _, events, _ = p.evaluate(
        CENTROIDS, PRINTS, profiles, 'c1', NOW + 31 * 86400, created_ids=[vid], evidence_at=NOW
    )
    assert not following and 'created' not in events
    following, _, events, _ = p.evaluate(CENTROIDS, PRINTS, {}, 'c1', NOW, created_ids=['old1', 'old2', 'old3'])
    assert not following and 'created' not in events


def test_people_mutation_after_checkpoint_refuses_recurring_publication(store):
    from types import SimpleNamespace
    from database.people_generation import write_person

    expected = db.checkpoint('u', 'c1', firestore_client=store)
    person = store.collection('users').document('u').collection('people').document('new-person')
    write_person(store, person, 'set', {'speaker_embedding': VOICE})
    before = deepcopy(store.rows)
    conversation = SimpleNamespace(
        id='c1',
        transcript_segments=[
            TranscriptSegment(text='x', start=0, end=30, is_user=False, speaker_id_scope='final:batch:x')
        ],
    )
    assert db.learn('u', conversation, CENTROIDS, PRINTS, expected, firestore_client=store) == {}
    assert store.rows == before and not store.transactions[-1].has_written


def test_kill_switch_and_percent_are_nested_under_batch_admission(monkeypatch):
    from types import SimpleNamespace

    batch = [SimpleNamespace(speaker_id_scope='final:batch:x', provider_speaker=None)]
    live = [SimpleNamespace(speaker_id_scope='listen:x', provider_speaker=None)]
    assert flags.recurring_enabled_for('u', batch)
    assert not flags.recurring_enabled_for('u', live)
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'false')
    assert not flags.recurring_enabled_for('u', batch)
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'true')
    monkeypatch.setenv('SPEAKER_RECURRING_PERCENT', '0')
    assert not flags.recurring_enabled_for('u', batch)
    monkeypatch.setenv('SPEAKER_RECURRING_PERCENT', 'nan')
    assert not flags.recurring_enabled_for('u', batch)
    monkeypatch.setenv('SPEAKER_RECURRING_PERCENT', '100')
    monkeypatch.setenv('SPEAKER_RECURRING_VOICES_ENABLED', 'false')
    assert not flags.recurring_enabled_for('u', batch)


def test_resolved_batch_binding_keeps_admission_without_reopening_audio_units(monkeypatch):
    from types import SimpleNamespace

    resolved = [SimpleNamespace(speaker_id_scope='final:batch:conversation:c1', provider_speaker=None)]
    assert flags.recurring_enabled_for('u', resolved)
    assert not flags.final_pass_enabled_for('u', resolved)
    for name, value in [
        ('BATCH_FINAL_PASS_ENABLED', 'false'),
        ('BATCH_FINAL_PASS_PERCENT', '0'),
        ('BATCH_FINAL_PASS_PERCENT', 'nan'),
        ('SPEAKER_RECURRING_VOICES_ENABLED', 'false'),
        ('SPEAKER_RECURRING_PERCENT', '0'),
        ('BATCH_CONVERSATION_SPEAKERS_ENABLED', 'false'),
    ]:
        with monkeypatch.context() as current:
            current.setenv(name, value)
            assert not flags.recurring_enabled_for('u', resolved)


def test_near_misses_are_suggestions_never_names():
    near = (np.array(VOICE) * 0.45 + np.array(OTHER) * np.sqrt(1 - 0.45**2)).tolist()
    assert p.near_misses(VOICE, {'near': near, 'owner': OWNER, 'user': VOICE}) == [
        {'person_id': 'near', 'level': 1, 'suggest': False}
    ]
