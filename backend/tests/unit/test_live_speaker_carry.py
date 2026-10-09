"""C6: manual speaker decisions carry across a same-stream conversation rollover.

A recording rotation mints a new conversation row while one provider stream —
and its (scope, label) voice identity — continues. Only explicit winning receipt
decisions carry, stamped ``source='carried'`` and bound to the active scope.
"""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from database import conversations as conversations_db
from routers.listen import conversations as controller_module
from routers.listen import speakers as listen_speakers
from routers.listen.conversations import LiveConversationController
from routers.listen.receiver import ListenReceiver
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.live_speaker_carry import carried_receipt
from utils.stt import live_session
from utils.stt import streaming as st
from utils.manual_speaker_assignments import apply_manual_assignments
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator, SpeakerProviderEpoch
from models.transcript_segment import TranscriptSegment

UID = 'uid-carry'
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCOPE = 'conn-a:0'


def _segment(seg_id, *, speaker='SPEAKER_0', speaker_id=0, scope=SCOPE, **extra):
    segment = {
        'id': seg_id,
        'speaker': speaker,
        'speaker_id': speaker_id,
        'speaker_id_scope': scope,
        'start': 0.0,
        'end': 5.0,
        'text': 'hi',
        'is_user': False,
    }
    segment.update(extra)
    return segment


def _conversation(receipt, segments=None):
    return {
        'id': 'conv-prev',
        'status': 'in_progress',
        'transcript_segments': segments if segments is not None else [_segment('s0'), _segment('s1')],
        'manual_speaker_assignments': receipt,
    }


def _person_receipt(**extra):
    entry = {'generation': 3, 'person_id': 'p1', 'is_user': False}
    entry.update(extra)
    return {'generation': 3, 'speakers': {'0': entry}}


def test_named_voice_on_the_active_scope_carries():
    receipt = carried_receipt(_conversation(_person_receipt()), SCOPE)
    entry = receipt['speakers']['0']
    assert receipt['generation'] == 1
    assert entry['person_id'] == 'p1' and entry['is_user'] is False
    assert entry['source'] == 'carried' and entry['generation'] == 1
    assert entry['speaker_id_scope'] == SCOPE and entry['stream_speaker'] == 'SPEAKER_0'
    assert entry['carried_from_conversation_id'] == 'conv-prev'
    assert 'label_evidence' not in receipt


def test_owner_and_negative_decisions_carry():
    owner = carried_receipt(
        _conversation({'generation': 1, 'speakers': {'0': {'generation': 1, 'is_user': True}}}), SCOPE
    )
    assert owner['speakers']['0']['is_user'] is True and 'person_id' not in owner['speakers']['0']
    rejection = {
        'generation': 2,
        'speakers': {
            '0': {
                'generation': 2,
                'is_user': False,
                'person_id': None,
                'rejection': {'kind': 'not_me', 'person_id': None},
            }
        },
    }
    carried = carried_receipt(_conversation(rejection), SCOPE)
    assert carried['speakers']['0']['rejection'] == {'kind': 'not_me', 'person_id': None}
    anonymous = {'generation': 1, 'speakers': {'0': {'generation': 1, 'is_user': False, 'person_id': None}}}
    assert carried_receipt(_conversation(anonymous), SCOPE)['speakers']['0']['person_id'] is None


def test_selected_segment_decision_carries_when_unambiguous():
    receipt = {
        'generation': 4,
        'segments': {
            's0': {'generation': 4, 'person_id': 'p1', 'is_user': False, 'speaker_id': 0, 'speaker_id_scope': SCOPE}
        },
    }
    carried = carried_receipt(_conversation(receipt), SCOPE)
    assert carried['speakers']['0']['person_id'] == 'p1'


def test_automatic_labels_never_carry():
    segments = [_segment('s0', person_id='p1', speaker_match_source='live_embedding')]
    assert carried_receipt(_conversation({}, segments), SCOPE) == {}
    assert carried_receipt(_conversation(_person_receipt(), segments), 'other-scope') == {}
    unscoped = _conversation(_person_receipt(), [_segment('s0', scope=None)])
    assert carried_receipt(unscoped, SCOPE) == {}
    sentinel = _conversation(_person_receipt(), [_segment('s0', speaker_id=99)])
    assert carried_receipt(sentinel, SCOPE) == {}
    unplaced = _conversation(_person_receipt(), [_segment('s0', audio_alignment='unplaced')])
    assert carried_receipt(unplaced, SCOPE) == {}


def test_conflicting_same_generation_decisions_skip_the_voice():
    receipt = {
        'generation': 4,
        'speakers': {'0': {'generation': 4, 'person_id': 'p1', 'is_user': False}},
        'segments': {
            's1': {'generation': 4, 'person_id': 'p2', 'is_user': False, 'speaker_id': 0, 'speaker_id_scope': SCOPE}
        },
    }
    assert carried_receipt(_conversation(receipt), SCOPE) == {}
    newer_positive = {
        'generation': 5,
        'speakers': {'0': {'generation': 5, 'person_id': 'p2', 'is_user': False}},
        'segments': {
            's0': {
                'generation': 4,
                'is_user': False,
                'person_id': None,
                'rejection': {'kind': 'not_person', 'person_id': 'p1'},
                'speaker_id': 0,
                'speaker_id_scope': SCOPE,
            }
        },
    }
    carried = carried_receipt(_conversation(newer_positive), SCOPE)
    assert carried['speakers']['0']['person_id'] == 'p2' and 'rejection' not in carried['speakers']['0']


def test_carried_receipt_applies_on_same_scope_and_is_skipped_elsewhere():
    carried = carried_receipt(_conversation(_person_receipt()), SCOPE)
    same_scope = apply_manual_assignments([_segment('n0')], carried)
    assert same_scope[0]['person_id'] == 'p1' and same_scope[0]['speaker_label_source'] == 'carried'
    new_scope = apply_manual_assignments([_segment('n0', scope='conn-b:0')], carried)
    assert new_scope[0].get('person_id') is None


def test_newer_positive_decision_overrides_a_carry():
    carried = carried_receipt(_conversation(_person_receipt()), SCOPE)
    carried['segments'] = {'n0': {'generation': 2, 'person_id': 'p2', 'is_user': False}}
    applied = apply_manual_assignments([_segment('n0')], carried)
    assert applied[0]['person_id'] == 'p2' and applied[0]['speaker_label_source'] == 'manual'


def test_allocator_reserves_carried_speaker_ids():
    carried = carried_receipt(_conversation(_person_receipt()), SCOPE)
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate([])
    allocator.hydrate_receipt(carried)
    fresh = {'speaker': 'SPEAKER_0', 'speaker_id_scope': 'conn-b:0'}
    allocator.assign(fresh)
    assert fresh['speaker_id'] == 1


def test_continuing_allocator_keeps_the_carried_voice_id():
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate([_segment('s0')])
    allocator.hydrate_receipt(carried_receipt(_conversation(_person_receipt()), SCOPE))
    continued = {'speaker': 'SPEAKER_0', 'speaker_id_scope': SCOPE}
    allocator.assign(continued)
    assert continued['speaker_id'] == 0


def _receiver():
    host = SimpleNamespace(
        request=SimpleNamespace(sample_rate=16000),
        is_multi_channel=False,
        use_custom_stt=True,
        state=SimpleNamespace(),
    )
    return ListenReceiver(host, [], {})


def test_each_provider_stream_build_mints_a_fresh_epoch_scope():
    receiver = _receiver()
    stamped = []
    receiver._enqueue_stt_segments = lambda segments, provider=None, speaker_epoch=None: speaker_epoch.stamp(
        segments, provider or 'soniox'
    ) or stamped.extend(segments)
    first, _, _ = receiver._build_stt_callbacks()
    epoch_one = receiver.speaker_provider_epoch
    first([{'speaker': 'SPEAKER_0'}])
    scope_one = stamped[-1]['speaker_id_scope']
    second, _, _ = receiver._build_stt_callbacks()
    epoch_two = receiver.speaker_provider_epoch
    assert epoch_two is not epoch_one and epoch_two.current_scope != scope_one
    second([{'speaker': 'SPEAKER_0'}])
    assert stamped[-1]['speaker_id_scope'] == epoch_two.current_scope != scope_one
    first([{'speaker': 'SPEAKER_0'}])
    assert stamped[-1]['speaker_id_scope'] == scope_one
    assert receiver.speaker_provider_epoch is epoch_two


def test_rotation_without_a_rebuild_keeps_the_scope():
    receiver = _receiver()
    receiver._build_stt_callbacks()
    epoch = receiver.speaker_provider_epoch
    epoch.stamp([{'speaker': 'SPEAKER_0'}], 'soniox')
    scope = epoch.current_scope
    epoch.stamp([{'speaker': 'SPEAKER_0'}], 'soniox')
    assert epoch.current_scope == scope


class _CarryHarness:
    """Firestore-backed listen host for the rollover create path."""

    def __init__(self, monkeypatch):
        self.store = StrictFirestore()
        self.rows = {}
        self.pointer = None
        self.on_scope_swap = None
        monkeypatch.setattr(
            controller_module.lifecycle_service, 'delete_empty_recording_conversation', lambda *a: False
        )

    def add_previous(self, receipt, segments):
        row = dict(
            id='prev-conv',
            source='omi',
            client_device_id='phone',
            status='in_progress',
            discarded=False,
            started_at=NOW,
            finished_at=NOW,
            created_at=NOW,
            transcript_segments=segments,
            manual_speaker_assignments=receipt,
            photos=[],
        )
        self.rows['prev-conv'] = row
        self.store.rows[('users', UID, 'conversations', 'prev-conv')] = row

    async def call(self, fn, *args, **kwargs):
        name = fn.__name__
        if name == 'open_live_recording_session':
            _uid, _sid, proposed = args
            return dict(
                conversation_id=proposed,
                requires_rollover=False,
                conversation_snapshot=None,
                conversation_snapshot_known=False,
                lifecycle_version=1,
                lifecycle_phase='in_progress',
                lifecycle_sequence=0,
            )
        if name == 'get_conversation':
            row = deepcopy(self.rows.get(args[1]))
            if self.on_scope_swap is not None:
                self.on_scope_swap()
            return row
        if name == 'create_in_progress_conversation':
            row = deepcopy(args[1])
            self.rows[row['id']] = row
            self.store.rows[('users', UID, 'conversations', row['id'])] = row
            return True
        if name == 'set_in_progress_conversation_id':
            self.pointer = args[1]
            return None
        raise AssertionError(name)

    def connect(self, epoch, current='prev-conv'):
        host = SimpleNamespace(
            request=SimpleNamespace(
                uid=UID,
                source='omi',
                conversation_role='ambient',
                geolocation=None,
                call_id=None,
                onboarding_mode=False,
            ),
            client_device_context=SimpleNamespace(client_device_id='phone', platform='ios'),
            client_conversation_id=None,
            recording_session_id='rec-1',
            recording_session_ids_by_conversation={},
            is_multi_channel=False,
            use_custom_stt=False,
            private_cloud_sync_enabled=False,
            language='en',
            onboarding_admitted=False,
            conversation_creation_timeout=120,
            state=SimpleNamespace(current_conversation_id=current, active=True),
            persistence=SimpleNamespace(call=self.call),
            send_event=lambda *a, **k: None,
            transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
            speakers=SimpleNamespace(refresh_for_conversation=AsyncMock()),
            receiver=SimpleNamespace(speaker_provider_epoch=epoch) if epoch is not None else SimpleNamespace(),
        )
        controller = LiveConversationController(host, clock=lambda: NOW)

        async def no_continuation(proposed=None):
            return None

        controller._continuation = no_continuation
        return controller


def _stamped_epoch(scope_name='conn-a'):
    epoch = SpeakerProviderEpoch(scope_name)
    epoch.stamp([{'speaker': 'SPEAKER_0'}], 'soniox')
    return epoch


@pytest.mark.anyio
async def test_rollover_carries_the_manual_receipt_into_the_fresh_row(monkeypatch):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0'), _segment('s1')])
    controller = harness.connect(_stamped_epoch())
    await controller.create_new_in_progress_conversation(rollover=True)
    fresh = harness.rows[harness.pointer]
    carried = fresh['manual_speaker_assignments']
    assert carried['speakers']['0']['person_id'] == 'p1'
    assert carried['speakers']['0']['source'] == 'carried'
    assert carried['speakers']['0']['speaker_id_scope'] == SCOPE


@pytest.mark.anyio
async def test_provider_restart_during_the_previous_read_clears_the_carry(monkeypatch):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0')])
    epoch = _stamped_epoch()
    receiver_ns = SimpleNamespace(speaker_provider_epoch=epoch)
    controller = harness.connect(epoch)

    def swap():
        receiver_ns.speaker_provider_epoch = _stamped_epoch('conn-b')
        controller.host.receiver = receiver_ns

    harness.on_scope_swap = swap
    await controller.create_new_in_progress_conversation(rollover=True)
    assert 'manual_speaker_assignments' not in harness.rows[harness.pointer]


@pytest.mark.anyio
async def test_no_carry_without_rollover_or_receiver(monkeypatch):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0')])
    controller = harness.connect(_stamped_epoch())
    await controller.create_new_in_progress_conversation()
    assert 'manual_speaker_assignments' not in harness.rows[harness.pointer]
    harness2 = _CarryHarness(monkeypatch)
    harness2.add_previous(_person_receipt(), [_segment('s0')])
    controller2 = harness2.connect(None)
    await controller2.create_new_in_progress_conversation(rollover=True)
    assert 'manual_speaker_assignments' not in harness2.rows[harness2.pointer]


@pytest.mark.anyio
async def test_carried_receipt_labels_incoming_segments_and_serializes_carried(monkeypatch):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0')])
    controller = harness.connect(_stamped_epoch())
    await controller.create_new_in_progress_conversation(rollover=True)
    fresh = harness.rows[harness.pointer]
    fresh_id = fresh['id']
    carried = fresh['manual_speaker_assignments']
    harness.store.rows[('users', UID, 'conversations', fresh_id)] = conversations_db._prepare_conversation_for_write(
        fresh, UID, 'standard'
    )
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: harness.store)
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(harness.rows['prev-conv']['transcript_segments'])
    allocator.hydrate_receipt(carried)
    incoming = {
        'id': 'n0',
        'speaker': 'SPEAKER_0',
        'speaker_id_scope': SCOPE,
        'start': 0.0,
        'end': 4.0,
        'text': 'hi',
        'is_user': False,
    }
    allocator.assign(incoming)
    assert incoming['speaker_id'] == 0
    merge = conversations_db.update_conversation_segments(UID, fresh_id, [], live_segments=[dict(incoming)])
    stored = next(s for s in merge.segments if s.get('id') == 'n0')
    assert stored['person_id'] == 'p1' and stored['speaker_label_source'] == 'carried'
    raw = harness.store.collection('users').document(UID).collection('conversations').document(fresh_id).get()
    decoded = conversations_db._decrypt_conversation_data(raw.to_dict(), UID)
    persisted = next(s for s in decoded['transcript_segments'] if s.get('id') == 'n0')
    assert persisted['person_id'] == 'p1' and persisted['speaker_label_source'] == 'carried'
    assert TranscriptSegment(**persisted).model_dump()['speaker_label_source'] == 'carried'
    reconnected = dict(incoming, id='n1', speaker_id=0, speaker_id_scope='conn-b:0')
    merge = conversations_db.update_conversation_segments(UID, fresh_id, [], live_segments=[reconnected])
    ghost = next(s for s in merge.segments if s.get('id') == 'n1')
    assert ghost.get('person_id') is None and ghost.get('speaker_label_source') is None


def _matcher_host(receipt, emitted):
    async def _call(fn, *args):
        if fn.__name__ == 'get_manual_speaker_receipt':
            return receipt
        if fn.__name__ == 'get_person':
            assert args == (UID, 'p1')
            return {'id': 'p1', 'name': 'Rei'}
        raise AssertionError(f'Unexpected matcher persistence call: {fn.__name__}')

    return SimpleNamespace(
        request=SimpleNamespace(uid=UID, sample_rate=16000),
        state=SimpleNamespace(
            active=True,
            speaker_id_enabled=True,
            audio_ring_buffer=SimpleNamespace(
                get_time_range=lambda: (0.0, 60.0), extract=lambda a, b: b'\x01\x00' * 16000
            ),
        ),
        persistence=SimpleNamespace(call=_call),
        emit_speaker_suggestion=lambda *a, **k: emitted.append((a, k)),
        limits=SimpleNamespace(speaker_id_min_audio=1.0),
        spawn=lambda coro, name=None: coro.close() or SimpleNamespace(add_done_callback=lambda f: None),
        private_cloud_sync_enabled=False,
        send_speaker_sample_request=None,
        recording_session_id='rec-1',
        has_speech_profile=False,
    )


def _matcher_segment():
    return {
        'id': 'n0',
        'conversation_id': 'conv-new',
        'duration': 10,
        'abs_start': 0,
        'abs_end': 10,
        'speaker_id_scope': SCOPE,
    }


def _match(matcher):
    asyncio.run(matcher.match(0, _matcher_segment()))


def test_matcher_does_not_emit_an_automatic_alternative_for_a_carried_person(monkeypatch):
    carried = carried_receipt(_conversation(_person_receipt()), SCOPE)
    emitted = []
    matcher = listen_speakers.SpeakerMatcher(_matcher_host(carried, emitted))
    matcher._profile_conversation_id = 'conv-new'
    matcher.person_embeddings['p2'] = {'embedding': np.array([[1.0, 0.0]]), 'name': 'Yara'}
    matcher.speaker_evidence[0] = deque([(np.array([[1.0, 0.0]]), 10.0)])
    monkeypatch.setattr(listen_speakers, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[1.0, 0.0]]))
    _match(matcher)
    assert emitted == []
    # The carried manual identity wins even without its embedding; the other
    # person's matching vector must not replace it or emit an alternative.
    assert matcher.speaker_to_person == {0: ('p1', 'Rei')}


def test_matcher_binds_a_known_carried_person_without_emitting(monkeypatch):
    carried = carried_receipt(_conversation(_person_receipt()), SCOPE)
    emitted = []
    matcher = listen_speakers.SpeakerMatcher(_matcher_host(carried, emitted))
    matcher._profile_conversation_id = 'conv-new'
    matcher.person_embeddings['p1'] = {'embedding': np.array([[1.0, 0.0]]), 'name': 'Rei'}
    matcher.speaker_evidence[0] = deque([(np.array([[1.0, 0.0]]), 10.0)])
    monkeypatch.setattr(listen_speakers, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[1.0, 0.0]]))
    _match(matcher)
    assert emitted == []
    assert matcher.speaker_to_person == {0: ('p1', 'Rei')}
    assert matcher.voice_identity_status[0] == listen_speakers.SpeakerIdentityStatus.not_user


def test_selected_manual_decision_suppresses_emit_without_binding_the_map(monkeypatch):
    receipt = {
        'generation': 2,
        'segments': {
            'n0': {'generation': 2, 'person_id': 'p1', 'is_user': False, 'speaker_id': 0, 'speaker_id_scope': SCOPE}
        },
    }
    emitted = []
    matcher = listen_speakers.SpeakerMatcher(_matcher_host(receipt, emitted))
    matcher._profile_conversation_id = 'conv-new'
    matcher.person_embeddings['p1'] = {'embedding': np.array([[1.0, 0.0]]), 'name': 'Rei'}
    matcher.speaker_evidence[0] = deque([(np.array([[1.0, 0.0]]), 10.0)])
    monkeypatch.setattr(listen_speakers, 'extract_embedding_from_bytes', lambda *a, **k: np.array([[1.0, 0.0]]))
    _match(matcher)
    assert emitted == []
    assert matcher.speaker_to_person == {}
    assert 0 not in matcher.speaker_to_person


def _managed_receiver():
    stamped = []
    receiver = SimpleNamespace(
        host=SimpleNamespace(
            request=SimpleNamespace(uid=UID, vad_gate_override=None),
            stt_language='en',
            language='en',
            language_profile=None,
            stt_service=st.STTService.soniox,
            stt_model='soniox',
            vocabulary=[],
            state=SimpleNamespace(active=True),
        ),
        speaker_provider_epoch=SpeakerProviderEpoch(),
        _stt_failed_providers=set(),
        vad_gate=None,
        capture_timeline_v2=False,
        _run_on_listen_loop=lambda fn, segments: fn(segments),
        _enqueue_stt_segments=None,
        _enqueue_epoch_segments=None,
        _record_elapsed_validation=lambda *args: None,
    )

    def enqueue(segments, provider=None, speaker_epoch=None):
        (speaker_epoch or receiver.speaker_provider_epoch).stamp(segments, provider or 'soniox')
        stamped.append(segments)

    receiver._enqueue_stt_segments = enqueue
    receiver._enqueue_epoch_segments = enqueue
    return receiver, stamped


@pytest.mark.anyio
async def test_managed_chain_reconnect_mints_a_fresh_speaker_scope(monkeypatch):
    callbacks = []
    raw_socket = SimpleNamespace(is_connection_dead=False, finish=lambda: None, send=lambda data: True)

    async def connect_soniox(callback, *args, **kwargs):
        callbacks.append(callback)
        return raw_socket

    async def pick_primary(**kwargs):
        return await kwargs['connect_primary'](), kwargs['primary_service']

    monkeypatch.setattr(st, 'process_audio_soniox', connect_soniox)
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(st, 'deepgram_fallback_model', lambda language: None)
    monkeypatch.setattr(live_session.st, 'connect_stt_socket_with_fallback', pick_primary)
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    receiver, stamped = _managed_receiver()
    session = live_session.LiveChainSession(receiver)
    await session.connect(16000)
    first_epoch = receiver.speaker_provider_epoch
    callbacks[0]([{'speaker': 'SPEAKER_0', 'start': 0.0, 'end': 1.0, 'text': 'a'}])
    assert stamped[-1][0]['speaker_id_scope'] == first_epoch.current_scope
    scope_one = first_epoch.current_scope
    await session.connect(16000, same_provider=True)
    second_epoch = receiver.speaker_provider_epoch
    assert second_epoch is not first_epoch
    callbacks[1]([{'speaker': 'SPEAKER_0', 'start': 1.0, 'end': 2.0, 'text': 'b'}])
    assert stamped[-1][0]['speaker_id_scope'] == second_epoch.current_scope != scope_one
    assert receiver.speaker_provider_epoch is second_epoch


class _FakeSendTracker:
    project_times = True
    provider_label = None

    def set_validation_callback(self, callback):
        self.validation_callback = callback

    def translate(self, segments):
        return segments


@pytest.mark.anyio
async def test_managed_chain_late_v2_callback_stamps_its_own_stream_scope(monkeypatch):
    callbacks = []
    raw_socket = SimpleNamespace(is_connection_dead=False, finish=lambda: None, send=lambda data: True)

    async def connect_soniox(callback, *args, **kwargs):
        callbacks.append(callback)
        return raw_socket

    async def pick_primary(**kwargs):
        return await kwargs['connect_primary'](), kwargs['primary_service']

    monkeypatch.setattr(st, 'process_audio_soniox', connect_soniox)
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(st, 'deepgram_fallback_model', lambda language: None)
    monkeypatch.setattr(live_session.st, 'connect_stt_socket_with_fallback', pick_primary)
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    receiver, stamped = _managed_receiver()
    session = live_session.LiveChainSession(receiver)
    await session.connect(16000, _FakeSendTracker())
    first_epoch = receiver.speaker_provider_epoch
    callbacks[0]([{'speaker': 'SPEAKER_0', 'start': 0.0, 'end': 1.0, 'text': 'a'}])
    scope_one = first_epoch.current_scope
    await session.connect(16000, _FakeSendTracker(), same_provider=True)
    second_epoch = receiver.speaker_provider_epoch
    assert second_epoch is not first_epoch
    callbacks[1]([{'speaker': 'SPEAKER_0', 'start': 1.0, 'end': 2.0, 'text': 'b'}])
    scope_two = second_epoch.current_scope
    assert scope_two != scope_one and receiver.speaker_provider_epoch is second_epoch
    callbacks[0]([{'speaker': 'SPEAKER_0', 'start': 2.0, 'end': 3.0, 'text': 'late'}])
    assert stamped[-1][0]['speaker_id_scope'] == scope_one
    assert receiver.speaker_provider_epoch is second_epoch
    assert receiver.speaker_provider_epoch.current_scope == scope_two


@pytest.mark.anyio
async def test_managed_chain_fallback_provider_owns_its_scope(monkeypatch):
    async def connect_modulate(callback, *args, **kwargs):
        return SimpleNamespace(is_connection_dead=False, finish=lambda: None, send=lambda data: True)

    async def pick_modulate(**kwargs):
        return await kwargs['connect_modulate'](), st.STTService.modulate

    monkeypatch.setattr(st, 'process_audio_modulate', connect_modulate)
    monkeypatch.setattr(st, 'modulate_is_configured_fallback', lambda language: True)
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(st, 'deepgram_fallback_model', lambda language: None)
    monkeypatch.setattr(live_session.st, 'connect_stt_socket_with_fallback', pick_modulate)
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    receiver, _ = _managed_receiver()
    prior = receiver.speaker_provider_epoch
    socket = await live_session.LiveChainSession(receiver).connect(16000)
    assert receiver.speaker_provider_epoch is socket.speaker_provider_epoch
    assert receiver.speaker_provider_epoch is not prior


@pytest.mark.anyio
async def test_rollover_skips_carry_when_the_previous_read_fails(monkeypatch):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0')])
    controller = harness.connect(_stamped_epoch())

    async def failing(fn, *args, **kwargs):
        if fn.__name__ == 'get_conversation' and args[1] == 'prev-conv':
            raise RuntimeError('lookup boom')
        return await harness.call(fn, *args, **kwargs)

    controller.host.persistence = SimpleNamespace(call=failing)
    await controller.create_new_in_progress_conversation(rollover=True)
    fresh = harness.rows[harness.pointer]
    assert 'manual_speaker_assignments' not in fresh


@pytest.mark.anyio
@pytest.mark.parametrize('flag', ['deleted', 'discarded', 'is_locked'])
async def test_rollover_never_carries_from_a_torn_previous_row(monkeypatch, flag):
    harness = _CarryHarness(monkeypatch)
    harness.add_previous(_person_receipt(), [_segment('s0')])
    harness.rows['prev-conv'][flag] = True
    controller = harness.connect(_stamped_epoch())
    await controller.create_new_in_progress_conversation(rollover=True)
    assert 'manual_speaker_assignments' not in harness.rows[harness.pointer]


def test_range_assignment_never_promotes_to_rollover_voice():
    receipt = {
        'generation': 4,
        'segments': {
            's0': {'generation': 4, 'person_id': 'p1', 'is_user': False, 'speaker_id': 0, 'segment_only': True},
        },
    }
    assert carried_receipt(_conversation(receipt), SCOPE) == {}
