"""Owner-recognition counters: one finalized conversation, live decisions, rollover."""

import asyncio
import importlib
import importlib.util
import json
import logging
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import routers.listen.speakers as speakers_mod
import utils.conversations.process_conversation as process_conversation_mod
from models.client_processing import ClientProcessing, ProjectedStructure, ProjectionProvenance
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import structured_is_rich
from utils.conversations.relevance import RelevanceDecision
from utils.observability.owner_recognition import (
    LIVE_SPEAKER_DECISIONS,
    LIVE_SPEAKER_ROLLOVER,
    OWNER_RECOGNITION_CONVERSATIONS,
    OWNER_RECOGNITION_OWNER_SHARE,
    emit_finalized_owner_recognition,
    live_decision_labels,
    lookup_owner_voiceprint,
    owner_recognition_already_observed,
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
        already_observed=False,
        owner_profile_present=True,
    )
    defaults.update(kwargs)
    return emit_finalized_owner_recognition(conversation, **defaults)


def _conversation_total() -> float:
    return sum(metric._value.get() for metric in OWNER_RECOGNITION_CONVERSATIONS._metrics.values())


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


def test_reprocess_of_an_already_observed_conversation_does_not_double_count(caplog):
    conversation = _conversation(
        [_segment(True, 0, 3, speaker_id=0), _segment(False, 3, 6, speaker_id=1)],
        source='omi',
    )
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified')
    assert _emit(conversation) == 'owner_identified'
    with caplog.at_level(logging.INFO, logger='utils.observability.owner_recognition'):
        assert _emit(conversation, already_observed=True) is None
    assert _count(OWNER_RECOGNITION_CONVERSATIONS, surface='live', source='omi', outcome='owner_identified') == (
        pytest.approx(before + 1)
    )
    assert not any('counted=False' in record.message for record in caplog.records)


def test_sync_intake_completed_status_is_not_an_observation():
    """Intake persists completed before the first enrichment, and clears discarded on promotion."""
    segments = [_segment(False, 0, 6, speaker_id=1, scope='sync:9')]
    fresh = _conversation(segments, source='omi')
    fresh.status = 'completed'
    fresh.discarded = False
    assert (
        owner_recognition_already_observed(
            fresh,
            is_reprocess=True,
            trigger=ProcessingTrigger.SYNC_UPDATE,
            prior_relevance_decision=None,
        )
        is False
    )
    promoted = _conversation(segments, source='omi')
    promoted.status = 'completed'
    promoted.discarded = False
    assert (
        owner_recognition_already_observed(
            promoted,
            is_reprocess=True,
            trigger=ProcessingTrigger.SYNC_UPDATE,
            prior_relevance_decision={'trigger': 'sync_intake', 'verdict': 'discard'},
        )
        is False
    )
    repeat = _conversation(segments, source='omi')
    repeat.status = 'completed'
    assert (
        owner_recognition_already_observed(
            repeat,
            is_reprocess=True,
            trigger=ProcessingTrigger.SYNC_UPDATE,
            prior_relevance_decision={'trigger': 'sync_update', 'verdict': 'keep'},
        )
        is True
    )
    before = _count(OWNER_RECOGNITION_CONVERSATIONS, surface='sync', source='omi', outcome='owner_not_identified')
    assert _emit(fresh, already_observed=False, owner_profile_present=True) == 'owner_not_identified'
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


def test_process_conversation_observes_every_successful_persist():
    text = (BACKEND / 'utils' / 'conversations' / 'process_conversation.py').read_text()
    body = text[text.index('def process_conversation(') :]
    assert body.count('_observe_owner_recognition_completion(') == 2
    report = body[body.index('def report_persistence(') : body.index('is_initial_creation')]
    assert 'if current and completed is not None:' in report
    assert '_observe_owner_recognition_completion(completed)' in report
    fence = body.index('if not persisted:')
    assert body.index('report_persistence(persisted, completed=conversation)') < fence
    assert 'return conversation' in body[fence : fence + 400]
    for marker in (
        'report_persistence(\n                persisted,',
        'if plan.mode == \'store_projection\'',
        'eager_basic_deny',
    ):
        assert marker in body
    assert 'prior_completed' not in body


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
    built = urllib.parse.urlsplit(rates.query_url('http://prometheus.example/', 'up'))
    assert (built.scheme, built.netloc, built.path) == ('http', 'prometheus.example', '/api/v1/query')
    assert urllib.parse.parse_qs(built.query) == {'query': ['up']}


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


def _sync_segment(*, text: str, is_user: bool, end: float, scope: str) -> dict:
    return {
        'start': 0.0,
        'end': end,
        'text': text,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': is_user,
        'speaker_id_scope': scope,
    }


def _sync_incoming(key: str, timestamp: int, segment: dict) -> dict:
    row = chunk(key, timestamp, text=segment['text'])
    row['created_at'] = row['started_at']
    row['finished_at'] = datetime.fromtimestamp(timestamp + segment['end'], timezone.utc)
    row['transcript_segments'] = [segment]
    row['status'] = 'completed'
    row['data_protection_level'] = 'enhanced'
    row['private_cloud_sync_enabled'] = False
    create = CreateConversation(
        started_at=row['started_at'],
        finished_at=row['finished_at'],
        transcript_segments=[
            TranscriptSegment(
                text=segment['text'],
                speaker='SPEAKER_00',
                is_user=segment['is_user'],
                start=0.0,
                end=segment['end'],
                speaker_id=0,
                speaker_id_scope=segment['speaker_id_scope'],
            )
        ],
        source=ConversationSource.omi,
        language='en',
    )
    row['structured'] = build_deterministic_minimum_structured(create).model_dump()
    return row


def _wire_sync_store(monkeypatch, store):
    from database import conversations as conversations_db
    from utils.conversations import lifecycle
    from utils.sync import pipeline

    assign = conversations_db.assign_sync_conversation
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *args, **kwargs: None)
    monkeypatch.setattr(
        conversations_db,
        'assign_sync_conversation',
        lambda uid, row, **kwargs: assign(uid, row, firestore_client=store, **kwargs),
    )

    def _get(uid, conversation_id, **kwargs):
        row = store.rows.get(('users', uid, 'conversations', conversation_id))
        if row is None:
            return None
        # The strict store retains Firestore delete sentinels. A real read does not.
        plain = {key: value for key, value in row.items() if type(value).__name__ != 'Sentinel'}
        return pipeline.conversations_db.prepare_conversation_for_read(deepcopy(plain), uid)

    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', _get)
    monkeypatch.setattr(pipeline.lifecycle_service, 'discard_by_relevance', lambda *args, **kwargs: True)
    return lifecycle, pipeline


def _stub_sync_enrichment(monkeypatch, store):
    """Keep the real intake and SYNC_UPDATE call, and skip the model."""

    def _structured(*args, **kwargs):
        observer = kwargs.get('relevance_observer')
        if observer is not None:
            observer(RelevanceDecision('keep', 'rule', 'substantive', ProcessingTrigger.SYNC_UPDATE))
        return build_deterministic_minimum_structured(args[2]), False

    def _persist(uid, payload, **kwargs):
        # The real writer re-encrypts the transcript. This stand-in keeps the
        # intake ciphertext and records the enrichment marker the second read uses.
        key = ('users', uid, 'conversations', payload['id'])
        current = dict(store.rows.get(key) or {})
        if 'relevance_decision' in payload:
            current['relevance_decision'] = payload['relevance_decision']
        if isinstance(payload.get('structured'), dict):
            current['structured'] = payload['structured']
        if 'discarded' in payload:
            current['discarded'] = payload['discarded']
        store.rows[key] = current
        return True

    module = process_conversation_mod
    monkeypatch.setattr(module, '_enrich_meeting_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'resolve_speakers_for_processing', lambda *args, **kwargs: False)
    monkeypatch.setattr(module, '_get_structured', _structured)
    monkeypatch.setattr(module, 'link_duplicate_captures', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'trigger_conversation_apps', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, '_extract_memories', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, '_save_action_items', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'submit_with_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'record_usage', lambda *args, **kwargs: None)
    monkeypatch.setattr(module.lifecycle_service, 'persist_processed_conversation', _persist)
    monkeypatch.setattr(module.users_db, 'get_people_by_ids', lambda *args, **kwargs: [])
    monkeypatch.setattr(module.users_db, 'get_user_speaker_embedding', lambda _uid: [0.2, 0.3])
    monkeypatch.setattr(module, 'is_trial_paywalled', lambda *args, **kwargs: False)


def test_sync_intake_then_first_enrichment_counts_once(monkeypatch):
    store = StrictFirestore()
    lifecycle, pipeline = _wire_sync_store(monkeypatch, store)
    _stub_sync_enrichment(monkeypatch, store)
    segment = _sync_segment(
        text='We agreed to ship the recognition fix today.',
        is_user=True,
        end=8.0,
        scope='sync:keep',
    )
    assigned, created, _survivors = lifecycle.ingest_sync_conversation(
        'u', _sync_incoming('keep', 1_700_000_000, segment)
    )
    assert created is True
    status = getattr(assigned.get('status'), 'value', assigned.get('status'))
    assert status == 'completed'
    assert structured_is_rich(assigned.get('structured')) is False
    before = _conversation_total()
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert _conversation_total() == pytest.approx(before + 1)
    stored = store.rows[('users', 'u', 'conversations', assigned['id'])]
    assert stored['relevance_decision']['trigger'] == 'sync_update'
    assert structured_is_rich(stored.get('structured')) is False
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert _conversation_total() == pytest.approx(before + 1)


def test_promoted_sync_fragment_counts_once(monkeypatch):
    store = StrictFirestore()
    lifecycle, pipeline = _wire_sync_store(monkeypatch, store)
    _stub_sync_enrichment(monkeypatch, store)
    filler = _sync_segment(text='yeah yeah', is_user=False, end=2.0, scope='sync:frag')
    assigned, created, _survivors = lifecycle.ingest_sync_conversation(
        'u', _sync_incoming('frag', 1_700_000_100, filler)
    )
    assert created is True
    assert assigned.get('discarded') is True
    assert (assigned.get('relevance_decision') or {}).get('trigger') == 'sync_intake'
    before = _conversation_total()
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert _conversation_total() == pytest.approx(before)
    speech = _sync_segment(
        text='We agreed to ship the recognition fix today.',
        is_user=True,
        end=8.0,
        scope='sync:frag',
    )
    promoted, _created, _survivors = lifecycle.ingest_sync_conversation(
        'u', _sync_incoming('later', 1_700_000_160, speech)
    )
    assert promoted['id'] == assigned['id']
    assert promoted.get('discarded') is False
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert _conversation_total() == pytest.approx(before + 1)
    pipeline._reprocess_conversation_after_update('u', assigned['id'], 'en')
    assert _conversation_total() == pytest.approx(before + 1)


def _desktop_capture() -> CreateConversation:
    return CreateConversation(
        started_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 9, 2, 12, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                text='We agreed to ship the recognition fix today.',
                speaker='SPEAKER_00',
                is_user=True,
                start=0.0,
                end=8.0,
            )
        ],
        source=ConversationSource.desktop,
        language='en',
    )


def _desktop_projection() -> ClientProcessing:
    return ClientProcessing(
        schema_version=1,
        transcript_sha256='ab' * 32,
        structure=ProjectedStructure(title='local title', overview='local overview'),
        provenance=ProjectionProvenance(
            model_id='local-test-model',
            runtime='test-runtime',
            device_class='test-device',
            generated_at=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        ),
    )


def _stub_desktop_terminal(monkeypatch):
    module = process_conversation_mod
    monkeypatch.setattr(module, 'is_trial_paywalled', lambda *args, **kwargs: False)
    monkeypatch.setattr(module, 'link_duplicate_captures', lambda *args, **kwargs: None)
    monkeypatch.setattr(module.lifecycle_service, 'create_completed_conversation', lambda *args, **kwargs: True)
    monkeypatch.setattr(module.lifecycle_service, 'persist_processed_conversation', lambda *args, **kwargs: True)
    monkeypatch.setattr(module.users_db, 'get_user_speaker_embedding', lambda _uid: [0.2])


@pytest.mark.parametrize('mode', ['store_projection', 'deterministic_minimum', 'eager_denial'])
def test_desktop_terminal_paths_count_once(monkeypatch, mode):
    module = process_conversation_mod
    _stub_desktop_terminal(monkeypatch)
    before = _count(
        OWNER_RECOGNITION_CONVERSATIONS,
        surface='desktop',
        source='desktop',
        outcome='single_speaker_all_owner',
    )
    if mode == 'eager_denial':
        monkeypatch.setattr(module, 'free_tier_local_processing_enabled', lambda uid: False)
        monkeypatch.setattr(module, 'basic_plan_gate_eager_extraction_enabled', lambda: True)
        monkeypatch.setattr(
            module,
            '_flag_off_identified_basic_deny',
            lambda *args, **kwargs: module.FreeTierProcessingPlan(
                mode='deterministic_minimum', reason='basic_not_entitled', decision=None
            ),
        )
        stored = module.process_conversation('uid', 'en', _desktop_capture(), trigger=ProcessingTrigger.FIRST_OPEN)
    else:
        monkeypatch.setattr(module, 'free_tier_local_processing_enabled', lambda uid: True)
        monkeypatch.setattr(
            module,
            'resolve_free_tier_processing_plan',
            lambda **kwargs: module.FreeTierProcessingPlan(mode=mode, reason='basic_not_entitled', decision=None),
        )
        stored = module.process_conversation(
            'uid',
            'en',
            _desktop_capture(),
            client_projection=_desktop_projection() if mode == 'store_projection' else None,
        )
    assert stored.status == ConversationStatus.completed
    assert _count(
        OWNER_RECOGNITION_CONVERSATIONS,
        surface='desktop',
        source='desktop',
        outcome='single_speaker_all_owner',
    ) == pytest.approx(before + 1)
    total = _conversation_total()
    module.process_conversation('uid', 'en', stored, trigger=ProcessingTrigger.USER_REPROCESS)
    assert _conversation_total() == pytest.approx(total)


def _stub_completed_reprocess(monkeypatch):
    """Skip the model and derived writes so a USER_REPROCESS can finish."""

    def _structured(*args, **kwargs):
        return build_deterministic_minimum_structured(args[2]), False

    module = process_conversation_mod
    monkeypatch.setattr(module, '_enrich_meeting_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'resolve_speakers_for_processing', lambda *args, **kwargs: False)
    monkeypatch.setattr(module, '_get_structured', _structured)
    monkeypatch.setattr(module, 'trigger_conversation_apps', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, '_extract_memories', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, '_save_action_items', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'submit_with_context', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'record_usage', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'conversation_apps_opt_in_only', lambda: False)


def test_deferred_desktop_projection_counts_on_first_completed_reprocess(monkeypatch):
    module = process_conversation_mod
    _stub_desktop_terminal(monkeypatch)
    _stub_completed_reprocess(monkeypatch)
    monkeypatch.setattr(module, 'free_tier_local_processing_enabled', lambda uid: False)
    monkeypatch.setattr(module, 'should_defer_desktop_processing', lambda uid: True)
    monkeypatch.setattr(module, 'basic_plan_gate_eager_extraction_enabled', lambda: False)
    monkeypatch.setattr(module.lifecycle_service, 'create_processing_conversation', lambda *args, **kwargs: True)
    before = _conversation_total()
    deferred = module.process_conversation(
        'uid',
        'en',
        _desktop_capture(),
        client_projection=_desktop_projection(),
    )
    assert deferred.status == ConversationStatus.processing
    assert deferred.deferred is True
    assert deferred.client_processing is not None
    assert deferred.processing_state is None
    assert structured_is_rich(deferred.structured) is False
    assert (
        owner_recognition_already_observed(
            deferred,
            is_reprocess=True,
            trigger=ProcessingTrigger.USER_REPROCESS,
        )
        is False
    )
    assert _conversation_total() == pytest.approx(before)
    stored = module.process_conversation('uid', 'en', deferred, trigger=ProcessingTrigger.USER_REPROCESS)
    assert stored.status == ConversationStatus.completed
    assert _conversation_total() == pytest.approx(before + 1)
    module.process_conversation('uid', 'en', stored, trigger=ProcessingTrigger.USER_REPROCESS)
    assert _conversation_total() == pytest.approx(before + 1)


def test_observer_failure_cannot_skip_persistence_callbacks(monkeypatch):
    module = process_conversation_mod
    _stub_desktop_terminal(monkeypatch)
    monkeypatch.setattr(module, 'free_tier_local_processing_enabled', lambda uid: True)
    monkeypatch.setattr(
        module,
        'resolve_free_tier_processing_plan',
        lambda **kwargs: module.FreeTierProcessingPlan(
            mode='store_projection', reason='basic_not_entitled', decision=None
        ),
    )

    def _boom(*args, **kwargs):
        raise RuntimeError('emit failed')

    monkeypatch.setattr(module, 'emit_finalized_owner_recognition', _boom)

    class _RaisingHandler(logging.Handler):
        def handle(self, record):
            raise RuntimeError('log handler failed')

    handler = _RaisingHandler(level=logging.WARNING)
    previous_level = module.logger.level
    module.logger.addHandler(handler)
    module.logger.setLevel(logging.WARNING)
    seen = []
    try:
        stored = module.process_conversation(
            'uid',
            'en',
            _desktop_capture(),
            client_projection=_desktop_projection(),
            persistence_observer=lambda current: seen.append(('persist', current)),
            derived_effects_disposition_observer=lambda disposition: seen.append(('disposition', disposition)),
        )
    finally:
        module.logger.removeHandler(handler)
        module.logger.setLevel(previous_level)
    assert stored.status == ConversationStatus.completed
    assert seen == [
        ('persist', True),
        ('disposition', module.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS),
    ]
