"""Owner-recognition counters: one finalized conversation, live decisions, rollover."""

import asyncio
import importlib
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import routers.listen.speakers as speakers_mod
from models.conversation_enums import ConversationSource
from models.transcript_segment import SpeakerIdentityStatus
from utils.observability.owner_recognition import (
    LIVE_SPEAKER_DECISIONS,
    LIVE_SPEAKER_ROLLOVER,
    OWNER_RECOGNITION_CONVERSATIONS,
    OWNER_RECOGNITION_OWNER_SHARE,
    emit_finalized_owner_recognition,
    live_decision_labels,
    lookup_owner_voiceprint,
    surface_label,
)
from utils.stt.speaker_match import SPEAKER_MATCH_MIN_EVIDENCE_SECONDS, SpeakerMatchDecision

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


def _count(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def _segment(is_user, start, end, speaker_id=0, scope=None):
    return SimpleNamespace(
        is_user=is_user,
        start=start,
        end=end,
        speaker_id=speaker_id,
        speaker_id_scope=scope,
        text='hello',
    )


def _conversation(segments, *, source='omi', resolution='capture', scores=None, conversation_id='conv-1'):
    return SimpleNamespace(
        id=conversation_id,
        source=source,
        transcript_segments=segments,
        speaker_resolution=SimpleNamespace(status=resolution) if resolution else None,
        speaker_match_scores=scores,
        discarded=False,
        status='processing',
    )


def _emit(conversation, **kwargs):
    defaults = dict(
        uid='uid-1',
        is_reprocess=False,
        prior_completed=False,
        prior_discarded=False,
        owner_profile_present=True,
    )
    defaults.update(kwargs)
    return emit_finalized_owner_recognition(conversation, **defaults)


def test_owner_identified_counts_once_and_records_share(caplog):
    segments = [
        _segment(True, 0, 3, speaker_id=0, scope='connection:1'),
        _segment(False, 3, 6, speaker_id=1, scope='connection:1'),
    ]
    conversation = _conversation(segments, scores=[{'stage': 'capture'}], resolution='resolved')
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified')
    share_before = OWNER_RECOGNITION_OWNER_SHARE._sum.get()
    with caplog.at_level(logging.INFO, logger='utils.observability.owner_recognition'):
        assert _emit(conversation) == 'owner_identified'
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified'
    ) == pytest.approx(before + 1)
    assert OWNER_RECOGNITION_OWNER_SHARE._sum.get() == pytest.approx(share_before + 0.5)
    line = next(record.message for record in caplog.records if 'owner_recognition_outcome' in record.message)
    for field in (
        'uid=uid-1',
        'conversation=conv-1',
        'surface=live',
        'source=omi',
        'outcome=owner_identified',
        'speakers=2',
        'owner_speech_seconds=3.000',
        'total_speech_seconds=6.000',
        'speaker_match_scores=True',
        'speaker_resolution_status=resolved',
        'counted=True',
    ):
        assert field in line, line


def test_no_owner_profile_is_distinct_from_a_miss():
    segments = [_segment(False, 0, 6, speaker_id=1, scope='sync:1')]
    conversation = _conversation(segments, source=ConversationSource.phone)
    missing_before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='phone', outcome='no_owner_profile')
    miss_before = _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='phone', outcome='owner_not_identified'
    )
    share_before = OWNER_RECOGNITION_OWNER_SHARE._sum.get()
    assert _emit(conversation, owner_profile_present=False) == 'no_owner_profile'
    assert _emit(conversation, owner_profile_present=True) == 'owner_not_identified'
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='phone', outcome='no_owner_profile'
    ) == pytest.approx(missing_before + 1)
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='phone', outcome='owner_not_identified'
    ) == pytest.approx(miss_before + 1)
    assert OWNER_RECOGNITION_OWNER_SHARE._sum.get() == pytest.approx(share_before)


def test_single_speaker_all_owner_is_not_folded_into_identified():
    conversation = _conversation([_segment(True, 0, 6, speaker_id=0)], source='desktop')
    before = _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='desktop', source='desktop', outcome='single_speaker_all_owner'
    )
    identified = _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='desktop', source='desktop', outcome='owner_identified'
    )
    share_before = OWNER_RECOGNITION_OWNER_SHARE._sum.get()
    assert _emit(conversation, owner_profile_present=False) == 'single_speaker_all_owner'
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='desktop', source='desktop', outcome='single_speaker_all_owner'
    ) == pytest.approx(before + 1)
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='desktop', source='desktop', outcome='owner_identified'
    ) == pytest.approx(identified)
    assert OWNER_RECOGNITION_OWNER_SHARE._sum.get() == pytest.approx(share_before + 1.0)


def test_short_speech_is_too_little_even_when_labeled_owner():
    conversation = _conversation([_segment(True, 0, 4, speaker_id=0, scope='connection:1')])
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='too_little_speech')
    assert _emit(conversation) == 'too_little_speech'
    assert _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='too_little_speech') == (
        pytest.approx(before + 1)
    )


def test_reprocess_of_a_visible_conversation_does_not_double_count(caplog):
    conversation = _conversation(
        [_segment(True, 0, 3, speaker_id=0), _segment(False, 3, 6, speaker_id=1)],
        source='omi',
    )
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified')
    assert _emit(conversation) == 'owner_identified'
    with caplog.at_level(logging.INFO, logger='utils.observability.owner_recognition'):
        assert _emit(conversation, is_reprocess=True, prior_completed=True, prior_discarded=False) is None
    assert _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified') == (
        pytest.approx(before + 1)
    )
    assert not any('counted=False' in record.message for record in caplog.records)


def test_reprocess_of_a_discarded_row_counts_the_visible_outcome():
    conversation = _conversation([_segment(False, 0, 6, speaker_id=1, scope='sync:9')], source='omi')
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='omi', outcome='owner_not_identified')
    assert _emit(conversation, is_reprocess=True, prior_completed=True, prior_discarded=True) == 'owner_not_identified'
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='omi', outcome='owner_not_identified'
    ) == pytest.approx(before + 1)


def test_failed_voiceprint_read_does_not_become_no_owner_profile(caplog):
    def _boom(_uid):
        raise RuntimeError('firestore down')

    assert lookup_owner_voiceprint('uid-1', read_embedding=_boom) is None
    assert lookup_owner_voiceprint('uid-1', read_embedding=lambda _uid: None) is False
    assert lookup_owner_voiceprint('uid-1', read_embedding=lambda _uid: [0.2, 0.3]) is True
    conversation = _conversation([_segment(False, 0, 6, speaker_id=2, scope='connection:1')])
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='no_owner_profile')
    with caplog.at_level(logging.INFO, logger='utils.observability.owner_recognition'):
        assert _emit(conversation, owner_profile_present=None) is None
    assert _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='no_owner_profile') == (
        pytest.approx(before)
    )
    assert any('outcome=profile_lookup_failed' in record.message for record in caplog.records)


def test_surface_uses_source_and_scopes():
    desktop = _conversation([_segment(False, 0, 6, scope='sync:1')], source=ConversationSource.desktop)
    assert surface_label(desktop) == 'desktop'
    sync = _conversation([_segment(False, 0, 6, scope='legacy-conversation:c:0')], source='phone')
    assert surface_label(sync) == 'sync'
    mixed = _conversation(
        [_segment(False, 0, 3, scope='sync:1'), _segment(False, 3, 6, scope='connection:2')],
        source='omi',
    )
    assert surface_label(mixed) == 'live'
    other = _conversation([], source='workflow')
    assert surface_label(other) == 'other'
    assert _emit(other) == 'too_little_speech'


def test_process_conversation_emits_only_after_the_persist_fence():
    text = (BACKEND / 'utils' / 'conversations' / 'process_conversation.py').read_text()
    body = text[text.index('def process_conversation(') :]
    emit = body.index('emit_finalized_owner_recognition(')
    fence = body.rfind('if not persisted:', 0, emit)
    assert fence != -1
    assert 'return conversation' in body[fence:emit]
    assert 'prior_completed' in body[:emit]
    assert 'get_user_speaker_embedding' in body[fence:emit]


def test_metrics_survive_module_reload():
    import utils.observability.owner_recognition as mod

    first = mod.OWNER_RECOGNITION_CONVERSATIONS
    share = mod.OWNER_RECOGNITION_OWNER_SHARE
    decisions = mod.LIVE_SPEAKER_DECISIONS
    rollover = mod.LIVE_SPEAKER_ROLLOVER
    importlib.reload(mod)
    assert mod.OWNER_RECOGNITION_CONVERSATIONS is first
    assert mod.OWNER_RECOGNITION_OWNER_SHARE is share
    assert mod.LIVE_SPEAKER_DECISIONS is decisions
    assert mod.LIVE_SPEAKER_ROLLOVER is rollover
    mod.record_live_speaker_decision('owner', 'accepted')


def test_live_decision_labels_are_closed():
    accepted_owner = SpeakerMatchDecision('user', 'user', 0.4, float('inf'))
    assert live_decision_labels(accepted_owner, owner_enrolled=True) == ('owner', 'accepted')
    accepted_person = SpeakerMatchDecision('sarah', 'sarah', 0.4, 0.9)
    assert live_decision_labels(accepted_person, owner_enrolled=True) == ('person', 'accepted')
    rejected_owner = SpeakerMatchDecision(None, 'user', 0.9, float('inf'))
    assert live_decision_labels(rejected_owner, owner_enrolled=True) == ('owner', 'rejected')
    ambiguous = SpeakerMatchDecision(None, 'user', 0.4, 0.45, owner_contended=True)
    assert live_decision_labels(ambiguous, owner_enrolled=True) == ('owner', 'ambiguous')
    empty = SpeakerMatchDecision(None, None, float('inf'), float('inf'))
    assert live_decision_labels(empty, owner_enrolled=False) == ('person', 'rejected')


class _Ring:
    def get_time_range(self):
        return 0.0, 60.0

    def extract(self, _start, _end):
        return b'\x00\x00' * round((_end - _start) * 16000)


def _matcher(monkeypatch, embedding):
    host = SimpleNamespace(
        state=SimpleNamespace(audio_ring_buffer=_Ring(), speaker_map_dirty=False, speaker_map_version=0),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        request=SimpleNamespace(sample_rate=16000, uid='uid-live'),
        emit_speaker_suggestion=lambda *args: None,
        recording_session_id='rec-live-1',
        persistence=SimpleNamespace(call=_no_call),
    )
    matcher = speakers_mod.SpeakerMatcher(host)
    matcher.person_embeddings = {
        'user': {'embedding': np.array([[1.0, 0.0]], dtype=np.float32), 'name': 'User'},
    }
    matcher._profile_conversation_id = 'conv-live'
    monkeypatch.setattr(speakers_mod, 'extract_embedding_from_bytes', lambda _audio, _name: embedding)
    # The decision path still builds a wav. Skip the encoder so the fast-unit
    # budget measures the matcher, not PyAV, under a loaded CI shard.
    monkeypatch.setattr(speakers_mod.av, 'open', lambda *_args, **_kwargs: _Wav())
    monkeypatch.setattr(speakers_mod.av, 'AudioFrame', _AudioFrame)
    return matcher


class _WavStream:
    layout = 'mono'

    def encode(self, _frame=None):
        return []


class _Wav:
    def add_stream(self, *_args, **_kwargs):
        return _WavStream()

    def mux(self, _packet):
        return None

    def close(self):
        return None


class _AudioFrame:
    rate = 0

    @staticmethod
    def from_ndarray(*_args, **_kwargs):
        return _AudioFrame()


async def _no_call(*_args, **_kwargs):
    return {}


def test_pending_and_accepted_owner_decisions_carry_session_and_conversation(monkeypatch, caplog):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher = _matcher(monkeypatch, owner)
    pending = _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='pending')
    accepted = _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='accepted')
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        asyncio.run(matcher.match(0, {'id': 's1', 'duration': 2.5, 'abs_start': 0.0, 'abs_end': 2.5}))
        assert 0 not in matcher.speaker_to_person
        asyncio.run(
            matcher.match(
                0,
                {
                    'id': 's2',
                    'duration': SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
                    'abs_start': 3.0,
                    'abs_end': 3.0 + SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
                },
            )
        )
    assert _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='pending') == pytest.approx(pending + 1)
    assert _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='accepted') == pytest.approx(accepted + 1)
    assert matcher.speaker_to_person[0][0] == 'user'
    assert matcher._mapping_origin[0] == 'automatic'
    decisions = [record.message for record in caplog.records if 'speaker_id_decision' in record.message]
    assert decisions
    assert all('session=rec-live-1' in line and 'conversation=conv-live' in line for line in decisions)


def test_rejected_person_decision_when_owner_print_is_absent(monkeypatch):
    other = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher = _matcher(monkeypatch, other)
    matcher.person_embeddings = {'p1': {'embedding': other, 'name': 'Sarah'}}
    monkeypatch.setattr(speakers_mod, 'compare_embeddings', lambda *_args: 0.93)
    before = _count(LIVE_SPEAKER_DECISIONS, target='person', decision='rejected')
    asyncio.run(matcher.match(1, {'id': 's1', 'duration': 6.0, 'abs_start': 0.0, 'abs_end': 6.0, 'speaker_id': 1}))
    assert _count(LIVE_SPEAKER_DECISIONS, target='person', decision='rejected') == pytest.approx(before + 1)
    assert 1 not in matcher.speaker_to_person


def test_ambiguous_owner_claim_is_counted(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher = _matcher(monkeypatch, owner)

    async def receipt(_fn, _uid, _conversation_id):
        return {'segments': {'manual': {'is_user': True, 'person_id': None, 'generation': 1}}}

    matcher.host.persistence.call = receipt
    before = _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='ambiguous')
    asyncio.run(matcher.match(2, {'id': 'automatic', 'duration': 6.0, 'abs_start': 0.0, 'abs_end': 6.0}))
    assert matcher.voice_identity_status[2] == SpeakerIdentityStatus.ambiguous
    assert _count(LIVE_SPEAKER_DECISIONS, target='owner', decision='ambiguous') == pytest.approx(before + 1)


def _rollover_matcher():
    host = SimpleNamespace(state=SimpleNamespace(speaker_id_enabled=False))
    matcher = speakers_mod.SpeakerMatcher(host)
    matcher._profile_conversation_id = 'conv-old'
    matcher.speaker_to_person[0] = ('user', 'User')
    matcher._mapping_origin[0] = 'automatic'
    matcher.speaker_to_person[1] = ('p1', 'Sarah')
    matcher._mapping_origin[1] = 'manual'
    return matcher


def test_rollover_counts_a_mapped_owner_as_dropped_until_carry_changes():
    matcher = _rollover_matcher()
    none_owner = _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner')
    manual_person = _count(LIVE_SPEAKER_ROLLOVER, carried='manual', target='person')
    automatic_owner = _count(LIVE_SPEAKER_ROLLOVER, carried='automatic', target='owner')
    matcher.note_rollover_carry({1})
    asyncio.run(matcher.refresh_for_conversation('conv-new'))
    assert matcher.speaker_to_person == {}
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner') == pytest.approx(none_owner + 1)
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='manual', target='person') == pytest.approx(manual_person + 1)
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='automatic', target='owner') == pytest.approx(automatic_owner)


def test_session_clear_is_not_a_rollover():
    matcher = _rollover_matcher()
    before = _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner')
    matcher.clear()
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner') == pytest.approx(before)


def test_refresh_without_a_rollover_note_does_not_count():
    matcher = _rollover_matcher()
    before = _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner')
    manual_before = _count(LIVE_SPEAKER_ROLLOVER, carried='manual', target='person')
    asyncio.run(matcher.refresh_for_conversation('conv-new'))
    assert matcher.speaker_to_person == {}
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='none', target='owner') == pytest.approx(before)
    assert _count(LIVE_SPEAKER_ROLLOVER, carried='manual', target='person') == pytest.approx(manual_before)


def _rates():
    path = BACKEND / 'scripts' / 'owner_recognition_rates.py'
    spec = importlib.util.spec_from_file_location('owner_recognition_rates', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reader_rejects_unbounded_windows_and_formats_rates():
    rates = _rates()
    with pytest.raises(SystemExit):
        rates.validate_window('1h;drop')
    names = [name for name, _query in rates.queries('1h')]
    assert 'omi_owner_recognition_conversations_total' in names
    assert all('[1h]' in query for _name, query in rates.queries('1h'))
    body = {
        'status': 'success',
        'data': {
            'resultType': 'vector',
            'result': [
                {
                    'metric': {'surface': 'live', 'source': 'omi', 'outcome': 'owner_identified'},
                    'value': [0, '0.25'],
                }
            ],
        },
    }
    text = rates.format_vector('omi_owner_recognition_conversations_total', body)
    assert 'surface=live' in text and 'outcome=owner_identified' in text and '0.25' in text
    rendered = rates.render(
        'http://prometheus.example',
        '5m',
        timeout=1,
        opener=lambda _endpoint, _promql: body,
    )
    assert rendered.startswith('endpoint=http://prometheus.example window=5m')
    assert 'http://prometheus.example' in rates.query_url('http://prometheus.example/', 'up')


def test_owner_identified_share_alert_is_in_both_exports():
    split = json.loads((BACKEND / 'charts' / 'monitoring' / 'alerts' / 'owner-recognition.json').read_text())
    combined = json.loads((BACKEND / 'charts' / 'monitoring' / 'alert-rules.json').read_text())
    rule = split[0]
    match = next(item for item in combined if item['uid'] == 'omi-owner-identified-share-drop')
    assert match == rule
    assert rule['noDataState'] == 'OK'
    assert rule['for'] == '2h'
    assert len(rule['uid']) <= 40
    expressions = ' '.join(node['model'].get('expr', '') for node in rule['data'])
    assert 'omi_owner_recognition_conversations_total' in expressions
    assert 'surface=~"live|sync"' in expressions
    assert '[2h]' in expressions and '[7d]' in expressions
    assert 'outcome="owner_identified"' in expressions
    assert 'too_little_speech' not in expressions
    assert rule['data'][3]['model']['expression'] == '$A >= 100 && $C > 0 && $B < ($C * 0.5)'
    assert (REPO / rule['annotations']['runbook']).is_file()
