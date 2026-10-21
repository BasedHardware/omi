"""Production grouping contract using synthetic cached evidence only."""

import time
from datetime import datetime, timezone

import numpy as np
import pytest

from config.jev_decisions import uid_bucket
from config.speaker_grouping import VARIANTS, configuration
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment, transcript_segment_for_client
from utils.conversations import speaker_grouping_shadow as shadow
from utils.conversations import speaker_resolution as stage
from utils.stt.conversation_speakers import Identity, resolve_conversation_speakers


def segment(index, scope='live:a', speaker=None, seconds=8):
    return TranscriptSegment(
        id=str(index),
        text='private words',
        start=index * 10,
        end=index * 10 + seconds,
        speaker_id=index if speaker is None else speaker,
        speaker_id_scope=scope,
        stt_provider='soniox',
        is_user=False,
    )


def resolve(segments, vectors, variant, **kwargs):
    return resolve_conversation_speakers(
        segments,
        vectors,
        grouping=variant,
        provider_keys={s.id: shadow.provider_key(s) for s in segments},
        grouping_deadline=time.monotonic() + 1,
        **kwargs
    )


@pytest.mark.parametrize('variant', VARIANTS)
def test_scope_resets_and_transitive_cannot_links(variant):
    segments = [segment(0, 'live:a', 0), segment(1, 'live:b', 0), segment(2, 'live:a', 1)]
    vectors = {s.id: [1, 0] for s in segments}
    result = resolve(segments, vectors, variant)
    assert result.speaker_ids['0'] != result.speaker_ids['2']
    assert len(set(result.speaker_ids.values())) == 2


@pytest.mark.parametrize('variant', ['provider_strict', 'provider_cannot_link'])
def test_same_scope_similar_voices_survive_anchor_absorption_and_person_match(variant):
    segments = [segment(0, seconds=60), segment(1, seconds=8)]
    result = resolve(segments, {'0': [1, 0], '1': [1, 0]}, variant, voiceprints={'person': [1, 0]})
    assert result.speaker_ids['0'] != result.speaker_ids['1']
    assert all(i.person_id == 'person' for i in result.voice_identities.values())


def test_g2_stricter_cross_scope_threshold_but_same_id_can_pool():
    a, b = [1, 0], [0.35, np.sqrt(1 - 0.35**2)]  # .65 distance, between thresholds
    segments = [segment(0), segment(1, 'live:b')]
    assert len(set(resolve(segments, {'0': a, '1': b}, 'provider_strict').speaker_ids.values())) == 1
    assert len(set(resolve(segments, {'0': a, '1': b}, 'provider_cannot_link').speaker_ids.values())) == 2
    segments[1].speaker_id_scope = 'live:a'
    segments[1].speaker_id = 0
    assert len(set(resolve(segments, {'0': a, '1': b}, 'provider_cannot_link').speaker_ids.values())) == 1


def test_owner_link_independent_accepts_only_and_free_nonowners_never_identity_pool():
    owner = [1, 0, 0]
    a, b = [0.7, np.sqrt(0.51), 0], [0.7, -np.sqrt(0.51), 0]  # owner distance .30; intervoice 1.02
    segments = [segment(0), segment(1, 'live:b')]
    strict = resolve(segments, {'0': a, '1': b}, 'provider_strict', voiceprints={'user': owner})
    assert not strict.voice_identities  # global owner contention
    linked = resolve(segments, {'0': a, '1': b}, 'owner_link', voiceprints={'user': owner})
    assert len(set(linked.speaker_ids.values())) == 1
    assert next(iter(linked.voice_identities.values())).is_user
    # Same geometry around an unadmitted person print cannot identity-pool.
    other = resolve(
        segments,
        {'0': [0, 0.7, np.sqrt(0.51)], '1': [0, 0.7, -np.sqrt(0.51)]},
        'owner_link',
        voiceprints={'user': owner},
    )
    assert len(set(other.speaker_ids.values())) == 2
    assert not other.voice_identities
    short = [segment(0, seconds=2), segment(1, 'live:b', seconds=2)]
    assert (
        len(set(resolve(short, {'0': a, '1': b}, 'owner_link', voiceprints={'user': owner}).speaker_ids.values())) == 2
    )


@pytest.mark.parametrize('variant', VARIANTS)
def test_manual_labels_win(variant):
    segments = [segment(0), segment(1), segment(2, 'live:b')]
    result = resolve(
        segments,
        {s.id: [1, 0] for s in segments},
        variant,
        manual_speakers={0: Identity(True, None), 1: Identity(False, 'person')},
        voiceprints={'user': [1, 0]},
    )
    assert result.speaker_ids['0'] == 0
    assert result.speaker_ids['1'] == 1
    assert all(not i.is_user for i in result.voice_identities.values())


def conversation(segments):
    return Conversation(
        id='c',
        created_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
        started_at=None,
        finished_at=None,
        structured=Structured(),
        transcript_segments=segments,
    )


def compare(monkeypatch, segments, vectors, **kwargs):
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'owner')
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', 'owner')
    c = conversation(segments)
    incumbent = resolve_conversation_speakers(segments, vectors, voiceprints={'user': [1, 0]})
    selected = shadow.compare_and_select(
        'owner',
        c,
        incumbent,
        vectors,
        manual_speakers={},
        voiceprints={'user': [1, 0]},
        embedding_seconds={s.id: s.end - s.start for s in segments},
        abstained_segment_ids=set(),
        receipt={},
        **kwargs
    )
    return c, incumbent, selected


def test_shadow_no_visible_change_and_content_free_logs(monkeypatch, caplog):
    segments = [segment(0), segment(1, 'live:b')]
    before = conversation(segments).model_dump(mode='json')
    with caplog.at_level('INFO'):
        c, incumbent, selected = compare(monkeypatch, segments, {'0': [1, 0], '1': [1, 0]})
    assert selected is incumbent
    assert c.model_dump(mode='json') == before
    assert all(set(s.speaker_grouping_shadow) == set(VARIANTS) for s in c.transcript_segments)
    assert 'private words' not in caplog.text
    assert caplog.text.count('event=speaker_grouping_shadow uid=') == 3
    assert caplog.text.count('event=speaker_grouping_shadow_segment') == 6


def test_mode_selects_without_shadow(monkeypatch):
    monkeypatch.setenv('SPEAKER_GROUPING_MODE', 'provider_strict')
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'off')
    segments = [segment(0), segment(1)]
    c = conversation(segments)
    vectors = {'0': [1, 0], '1': [1, 0]}
    baseline = resolve_conversation_speakers(segments, vectors)
    selected = shadow.compare_and_select(
        'uid',
        c,
        baseline,
        vectors,
        manual_speakers={},
        voiceprints={},
        embedding_seconds={},
        abstained_segment_ids=set(),
        receipt={},
    )
    assert len(set(selected.speaker_ids.values())) == 2
    assert all(s.speaker_grouping_shadow is None for s in segments)


@pytest.mark.parametrize('failure', ['exception', 'budget', 'limit', 'provenance'])
def test_fail_open(monkeypatch, failure):
    segments = [segment(0)]
    vectors = {'0': [1, 0]}
    if failure == 'exception':
        monkeypatch.setattr(
            shadow, 'resolve_conversation_speakers', lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
        )
    elif failure == 'budget':
        monkeypatch.setattr(shadow, 'MAX_SECONDS', 0)
    elif failure == 'limit':
        monkeypatch.setattr(shadow, 'MAX_SEGMENTS', 0)
    else:
        segments[0].speaker_id_scope = 'conversation:old'
    c, incumbent, selected = compare(monkeypatch, segments, vectors)
    assert selected is incumbent
    assert all(s.speaker_grouping_shadow is None for s in c.transcript_segments)


def test_original_scoped_partition_survives_rewrite_and_storage():
    s = segment(0)
    key = shadow.provider_key(s)
    s.assign_resolved_speaker(55, 'conversation:c')
    restored = TranscriptSegment(**s.model_dump())
    restored.assign_resolved_speaker(70, 'conversation:c')
    assert shadow.provider_key(restored) == key
    assert 'provider_speaker' not in restored.model_dump(mode='json')
    client = transcript_segment_for_client(restored.model_dump())
    assert 'provider_speaker' not in client
    assert 'speaker_grouping_shadow' not in client
    legacy = segment(1, 'conversation:c')
    assert shadow.provider_key(legacy) is None
    s._clear_audio_evidence()
    assert shadow.provider_key(s) is None


def test_metric_labels_bounded_and_correction_agreement(monkeypatch):
    events = []
    monkeypatch.setattr(shadow, 'count', lambda v, o, amount=1: events.append((v, o, amount)))
    s = segment(0)
    s.speaker_grouping_shadow = {VARIANTS[0]: 'user', VARIANTS[1]: 'unknown'}
    s.is_user = True
    shadow.record_correction({'transcript_segments': [s.model_dump()]}, ['0'])
    assert events == [(VARIANTS[0], 'correction_agreed', 1), (VARIANTS[1], 'correction_disagreed', 1)]
    assert shadow.SHADOW_TOTAL._labelnames == ('variant', 'outcome')


def test_cohort_default_dark_hash_stable_and_allowlist(monkeypatch):
    for key in (
        'SPEAKER_GROUPING_SHADOW',
        'SPEAKER_GROUPING_MODE',
        'SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST',
        'SPEAKER_GROUPING_SHADOW_PERCENT',
    ):
        monkeypatch.delenv(key, raising=False)
    assert configuration('owner').mode == 'incumbent'
    assert not configuration('owner').shadow
    # Frozen EXP-004 salt/hash algorithm value, independent of Python hash seed.
    assert uid_bucket('owner', 'speaker-grouping-shadow-v1') == pytest.approx(69.89021505301744)
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'cohort')
    for uid in ['a', 'owner', 'different']:
        assert configuration(uid).shadow == (uid_bucket(uid, 'speaker-grouping-shadow-v1') < 10)
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', 'owner')
    assert configuration('owner').shadow and configuration('owner').detailed
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW_PERCENT', 'nan')
    assert not configuration('different').shadow
    monkeypatch.setenv('SPEAKER_GROUPING_SHADOW', 'typo')
    assert not configuration('owner').shadow


def test_shadow_storage_uses_transcript_encryption(monkeypatch):
    from database import conversations as db

    s = segment(0)
    s.assign_resolved_speaker(5, 'conversation:c')
    s.speaker_grouping_shadow = {'provider_strict': 'person:private-person'}
    payload = {'id': 'c', 'transcript_segments': [s.model_dump()]}
    encrypted = db.encode_conversation_for_write('owner', payload, 'enhanced')
    assert isinstance(encrypted['transcript_segments'], str)
    assert 'private-person' not in encrypted['transcript_segments']
    restored = db.decode_transcript_segments_verified('owner', encrypted['transcript_segments'], True)
    assert restored[0]['provider_speaker'] == s.provider_speaker
    assert restored[0]['speaker_grouping_shadow'] == s.speaker_grouping_shadow


def test_proxies_separate_missing_evidence_from_rejection():
    segments = [segment(0), segment(1)]
    vectors = {'0': [1, 0], '1': [0, 1]}
    baseline = resolve_conversation_speakers(segments, vectors)
    # Construct an unsafe mixed owner group independent of the production policy.
    baseline.speaker_ids = {'0': 0, '1': 0}
    baseline.voice_identities = {0: Identity(True, None)}
    keys = {s.id: shadow.provider_key(s) for s in segments}
    mixed, fragmented = shadow._proxies(segments, baseline, keys, vectors, {'0': 8, '1': 8}, {'user': np.array([1, 0])})
    assert mixed == 1
    assert fragmented == 0
    assert shadow._proxies(segments, baseline, keys, vectors, {}, {'user': np.array([1, 0])})[0] == 0


def test_metric_helper_refuses_unbounded_label_values():
    with pytest.raises(ValueError, match='unbounded'):
        shadow.count('uid-not-a-variant', 'owner_same')
    with pytest.raises(ValueError, match='unbounded'):
        shadow.count('provider_strict', 'conversation-id-not-an-outcome')


def test_fresh_capture_text_repair_cannot_certify_absorbing_provider_id():
    a, b = segment(0), segment(1)
    a.text = 'This is an incomplete thought'
    b.text = 'little addition'
    a.start, a.end = 0, 2
    b.start, b.end = 2, 3
    combined = TranscriptSegment.combine_segments([], [a, b]).segments
    assert len(combined) == 1
    assert shadow.provider_key(combined[0]) is None
    assert combined[0].provider_speaker['id'] == -1
    fresh = segment(2)
    fresh._clear_audio_evidence()
    assert shadow.provider_key(fresh) is None
