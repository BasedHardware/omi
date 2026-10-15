import asyncio
import contextvars
import logging
import threading
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer as A,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptKind as K,
    SpeakerTagPromptOrigin as O,
    SpeakerTagPromptQualityOutcome as Q,
)
from utils import executors
from utils import speaker_sample
from utils.speaker_tag_prompts import service
from utils.stt import pre_recorded
from utils.executors import ExecutorSaturatedError, MonitoredThreadPoolExecutor
from utils.other import storage
from tests.unit.fixtures.audio_chunk_storage import memory_bucket

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self, monkeypatch, *, paid=True, save_others=True, prompts_enabled=True, state=None):
        self.assignments = []
        self.scheduled = []
        self.answered = []
        self.events = []
        self.people = {'p1': {'id': 'p1', 'name': 'Sam', 'speaker_embedding': [0.1]}}
        self.created = []
        self.state = state or {}
        self.settings = {'speaker_tag_prompts_enabled': prompts_enabled, 'save_other_voice_profiles': save_others}
        db = service.voice_profiles_db
        monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: paid)
        monkeypatch.setattr(db, 'get_voice_profile_settings', lambda uid: dict(self.settings))
        monkeypatch.setattr(db, 'get_voice_profile_context', lambda uid: (dict(self.settings), True))
        monkeypatch.setattr(db, 'get_tag_prompt_state', lambda uid: dict(self.state))
        monkeypatch.setattr(db, 'record_tag_prompt_answered', lambda uid, pid, now: self.answered.append(pid))
        monkeypatch.setattr(db, 'mark_tag_prompts_empty', lambda uid, now: self.state.update(last_empty_check_at=now))
        monkeypatch.setattr(service.users_db, 'get_person', lambda uid, pid: self.people.get(pid))
        monkeypatch.setattr(service.users_db, 'get_person_by_name', lambda uid, name: None)
        monkeypatch.setattr(service.users_db, 'create_person', lambda uid, data: self.created.append(data) or data)
        monkeypatch.setattr(service.users_db, 'get_people', lambda uid: list(self.people.values()))
        monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [])
        monkeypatch.setattr(
            service, 'emit_product_event', lambda **kwargs: self.events.append((kwargs['event'], kwargs['properties']))
        )

        def assign(uid, conversation_id, **kwargs):
            self.assignments.append(kwargs)
            segments = [
                {'id': 's1', 'speaker_id': 1, 'start': 0, 'end': 9},
                {'id': 's2', 'speaker_id': 1, 'start': 9, 'end': 12},
            ]
            raw = {'id': conversation_id, 'transcript_segments': segments}
            raw['_speaker_learning_queued'] = bool(kwargs.get('owner_segment_ids')) or bool(
                kwargs.get('person_id') and kwargs.get('use_for_speech_training')
            )
            return raw, ['s1', 's2'], [], []

        monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)

    def schedule(self, fn, **kwargs):
        self.scheduled.append((fn, kwargs))


def _request(kind, origin, answer, **extra):
    payload = dict(
        prompt_id='pid',
        kind=kind,
        origin=origin,
        conversation_id='c1',
        speaker_id=1,
        segment_ids=['s1'],
        answer=answer,
    )
    payload.update(extra)
    return SpeakerTagPromptAnswerRequest(**payload)


def test_legacy_owner_card_without_excerpt_evidence_cannot_label_or_learn(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.StaleOwnerConfirmation):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.me), world.schedule, NOW)
    assert not world.assignments and not world.scheduled


def test_free_user_names_a_person_on_a_served_card(monkeypatch):
    world = World(monkeypatch, paid=False)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.assignments[0]['person_id'] == 'p1' and not world.created


def test_naming_a_person_teaches_voice_when_allowed(monkeypatch):
    world = World(monkeypatch)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    assert world.assignments[0]['person_id'] == 'p1' and world.assignments[0]['use_for_speech_training'] is True
    fn, kwargs = world.scheduled[0]
    assert fn is service.run_authorized_person_learning and kwargs == {
        'uid': 'u',
        'person_id': 'p1',
        'conversation_id': 'c1',
        'segment_ids': ['s1', 's2'],
    }
    assert response.quality_outcome == Q.person_missed_known


def test_saving_other_voices_off_labels_without_teaching(monkeypatch):
    world = World(monkeypatch, save_others=False)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.created and world.created[0]['name'] == 'Ana'
    assert world.assignments[0]['use_for_speech_training'] is False
    assert world.scheduled == [] and not response.voice_sample_queued
    assert response.quality_outcome == Q.person_not_enrolled


def test_declined_durable_admission_still_queues_immediate_teaching(monkeypatch):
    world = World(monkeypatch)

    def assign(uid, conversation_id, **kwargs):
        raw = {'id': conversation_id, 'transcript_segments': [{'id': 's1', 'start': 0, 'end': 9}]}
        raw['_speaker_learning_queued'] = False
        return raw, ['s1'], [], []

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    recorded = []

    class _Counter:
        def labels(self, **labels):
            recorded.append(labels)
            return SimpleNamespace(inc=lambda: None)

    monkeypatch.setattr(service, 'SPEAKER_TAG_PROMPT_VOICE_SAMPLES', _Counter())
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    assert response.voice_sample_queued
    assert world.scheduled == [
        (
            service.run_authorized_person_learning,
            {'uid': 'u', 'person_id': 'p1', 'conversation_id': 'c1', 'segment_ids': ['s1']},
        )
    ]
    assert any(labels.get('outcome') == 'queued' for labels in recorded)


def test_rejecting_owner_without_played_evidence_fails_closed(monkeypatch):
    world = World(monkeypatch)
    with pytest.raises(service.StaleOwnerConfirmation):
        service.apply_answer('u', _request(K.owner_check, O.auto_user, A.not_me), world.schedule, NOW)
    assert not world.assignments


def test_unknown_voice_writes_an_anonymous_decision_and_skip_writes_nothing(monkeypatch):
    world = World(monkeypatch)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.someone_else), world.schedule, NOW)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.skip), world.schedule, NOW)
    assert world.assignments == [
        {
            'person_id': None,
            'is_user': False,
            'speaker_id': 1,
            'use_for_speech_training': False,
            'evidence_source': 'card',
        }
    ]
    assert world.answered == ['pid', 'pid']


def test_invalid_answer_for_kind(monkeypatch):
    world = World(monkeypatch)
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.not_me), world.schedule, NOW)


@pytest.mark.parametrize(
    'origin,answer,person_id,suggested,enrolled,expected',
    [
        (O.auto_user, A.me, None, None, False, Q.owner_auto_confirmed),
        (O.auto_user, A.person, 'p1', None, True, Q.owner_auto_rejected),
        (O.auto_person, A.person, 'p1', 'p1', True, Q.person_auto_confirmed),
        (O.auto_person, A.person, 'p2', 'p1', True, Q.person_auto_corrected),
        (O.auto_person, A.me, None, 'p1', False, Q.person_auto_corrected),
        (O.unnamed, A.me, None, None, False, Q.owner_missed),
        (O.unnamed, A.not_me, None, None, False, Q.owner_unmatched_not_owner),
        (O.unnamed, A.person, 'p1', None, True, Q.person_missed_known),
        (O.unnamed, A.new_person, 'p9', None, False, Q.person_not_enrolled),
        (O.unnamed, A.someone_else, None, None, False, Q.unknown_voice),
        (O.auto_person, A.skip, None, 'p1', False, Q.skipped),
    ],
)
def test_quality_outcome_table(origin, answer, person_id, suggested, enrolled, expected):
    outcome = service.quality_outcome(
        origin, answer, person_id=person_id, suggested_person_id=suggested, person_enrolled=enrolled
    )
    assert outcome == expected


def test_prompts_respect_disabled_and_daily_cooldown(monkeypatch):
    world = World(monkeypatch, prompts_enabled=False)
    assert service.get_prompts('u', NOW).status == 'disabled'

    world = World(monkeypatch, state={'first_shown_at': NOW, 'last_shown_at': NOW - timedelta(hours=3)})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown' and response.first_time is False
    assert response.next_eligible_at == NOW - timedelta(hours=3) + service.SHOW_COOLDOWN


def test_repeated_dismissals_back_off_to_a_week(monkeypatch):
    world = World(monkeypatch, state={'last_shown_at': NOW - timedelta(days=2), 'consecutive_dismissals': 3})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown'
    assert response.next_eligible_at == NOW - timedelta(days=2) + service.DISMISSED_COOLDOWN


def test_empty_scan_is_remembered(monkeypatch):
    world = World(monkeypatch)
    first = service.get_prompts('u', NOW)
    assert first.status == 'no_candidates' and first.first_time is True
    calls = []
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: calls.append(1) or [])
    second = service.get_prompts('u', NOW + timedelta(minutes=30))
    assert second.status == 'no_candidates' and calls == []
    assert world.state['last_empty_check_at'] == NOW


def test_owner_clip_window_keeps_text_of_a_long_segment_cropped_to_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 30, 'is_user': True, 'speaker_id': 0, 'text': 'one long owner turn'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) == (10.0, 20.0, 'one long owner turn')


def test_clip_verification_cache_reuses_verdict_and_invalidates_on_audio_change(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    checks = []
    downloads = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(
        service,
        'conversation_clip_pcm',
        lambda *args: downloads.append(1) or b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5),
    )

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(expected_text)
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    for _ in range(2):
        assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five')
    assert len(checks) == 1 and len(downloads) == 2
    row['audio_files'][0]['duration'] = 21.0
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five')
    assert len(checks) == 2


def test_positive_cache_never_authorizes_different_clip_bytes(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    pcm = [b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)]
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: pcm[0])

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return ('matching words', len(checks) == 1, 'ok' if len(checks) == 1 else 'text_mismatch')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'matching words') == pcm[0]
    pcm[0] = b'\x02\x00' * (service.CLIP_SAMPLE_RATE * 5)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'matching words') is None
    assert len(checks) == 2


def test_clip_verification_rejects_mismatch_and_caches_negative(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x00\x00' * (service.CLIP_SAMPLE_RATE * 5))

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return ('unrelated words', False, 'text_mismatch: containment=0.00')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert len(checks) == 1
    assert list(cache.values())[0]['valid'] is False


def test_negative_cache_rechecks_changed_pcm_under_same_manifest(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    pcm = [b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)]
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: pcm[0])

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return (
            'one two three four five' if len(checks) == 2 else 'wrong speech elsewhere',
            len(checks) == 2,
            'ok' if len(checks) == 2 else 'text_mismatch',
        )

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    for _ in range(2):
        assert service.verified_clip_pcm('u', row, 1, 6, 'one two three four five') is None
    assert len(checks) == 1
    pcm[0] = b'\x02\x00' * (service.CLIP_SAMPLE_RATE * 5)
    assert service.verified_clip_pcm('u', row, 1, 6, 'one two three four five') == pcm[0]
    assert len(checks) == 2


def test_clip_match_rejects_short_subset_of_long_expected_text(monkeypatch):
    row = {'id': 'c1', 'audio_files': []}
    pcm = b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda *args, **kwargs: None)

    async def verify(audio, sample_rate, expected_text, language=None):
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 0, 5, 'one two three four five', pcm) == pcm
    assert (
        service.verified_clip_pcm('u', row, 0, 5, 'one two three four five six seven eight nine ten eleven twelve', pcm)
        is None
    )
    assert service.verified_clip_pcm('u', row, 0, 5, 'completely different spoken words today', pcm) is None


def test_clip_expected_text_trims_long_segment_to_clip_window():
    row = {
        'transcript_segments': [
            {
                'speaker_id': 0,
                'start': 0,
                'end': 20,
                'text': 'one two three four five six seven eight nine ten eleven twelve',
            }
        ]
    }
    text = service.clip_expected_text(row, 0, 10)
    assert text.startswith('one two')
    assert 'twelve' not in text

    cjk = {
        'transcript_segments': [
            {'speaker_id': 0, 'start': 0, 'end': 20, 'text': '今天我们一起讨论如何安排下周的工作会议和项目计划'}
        ]
    }
    assert len(service.clip_expected_text(cjk, 0, 10)) < len(cjk['transcript_segments'][0]['text'])


def test_prompt_list_verification_budget_returns_without_empty_cooldown(monkeypatch):
    world = World(monkeypatch)
    started = NOW - timedelta(hours=1)
    row = {
        'id': 'slow',
        'started_at': started,
        'status': 'completed',
        'audio_files': [{'chunk_timestamps': [started.timestamp()], 'duration': 20.0}],
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 0, 'start': 0, 'end': 10, 'text': 'one two three four five six seven eight'}
        ],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *args, **kwargs: [row])
    monkeypatch.setattr(service, 'LIST_VERIFY_BUDGET_SECONDS', 0.02)
    release = threading.Event()
    started_verify = threading.Event()

    def slow_verify(*args, **kwargs):
        started_verify.set()
        release.wait(timeout=1)
        return None

    monkeypatch.setattr(service, 'verified_clip_pcm', slow_verify)
    for shared in (executors.postprocess_executor, executors.sync_executor, executors.storage_executor):
        monkeypatch.setattr(
            shared, 'submit', lambda *args, **kwargs: pytest.fail('verification used a shared executor')
        )
    try:
        began = time.monotonic()
        response = service.get_prompts('u', NOW)
        assert time.monotonic() - began < 0.5
        assert started_verify.is_set()
        assert response.status == 'no_candidates'
        assert 'last_empty_check_at' not in world.state
    finally:
        release.set()


def test_list_verification_pool_is_bounded_and_dedupes_inflight(monkeypatch):
    pool = MonitoredThreadPoolExecutor(name='tag-test', max_workers=1, max_queue_size=1)
    monkeypatch.setattr(service, 'speaker_tag_verify_executor', pool)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_verify(uid, row, start, end, text, *, verification_deadline):
        calls.append(row['id'])
        started.set()
        release.wait(timeout=2)
        return b'valid'

    monkeypatch.setattr(service, 'verified_clip_pcm', slow_verify)
    deadline = time.monotonic() + 1
    try:
        row = {'id': 'same', 'audio_files': [{'duration': 20}]}
        with ThreadPoolExecutor(max_workers=4) as callers:
            duplicates = list(
                callers.map(
                    lambda _: service._submit_list_verification('u', row, 0, 5, 'same words', deadline), range(4)
                )
            )
        assert started.wait(timeout=1)
        assert all(future is duplicates[0] for future in duplicates)
        assert calls == ['same']

        queued = service._submit_list_verification('u', {'id': 'queued'}, 0, 5, 'other words', deadline)
        assert pool.active_count == 1
        assert pool._work_queue.qsize() == 1
        with pytest.raises(ExecutorSaturatedError):
            service._submit_list_verification('u', {'id': 'rejected'}, 0, 5, 'third words', deadline)
        assert service._submit_list_verification('u', row, 0, 5, 'same words', deadline) is duplicates[0]
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert queued.done()


def test_list_verification_deadline_logs_info_not_error(monkeypatch, caplog):
    pool = MonitoredThreadPoolExecutor(name='tag-deadline', max_workers=1)
    monkeypatch.setattr(service, 'speaker_tag_verify_executor', pool)
    caplog.set_level(logging.INFO)

    def timed_out(uid, row, start, end, text, *, verification_deadline):
        raise service.FutureTimeoutError()

    monkeypatch.setattr(service, 'verified_clip_pcm', timed_out)
    try:
        future = service._submit_list_verification('u', {'id': 'late'}, 0, 5, 'one two', time.monotonic() + 1)
        cleared = threading.Event()
        future.add_done_callback(lambda _: cleared.set())
        with pytest.raises(service.FutureTimeoutError):
            future.result(timeout=2)
        assert cleared.wait(timeout=2)
        verification_key = service._verification_cache_key('u', {'id': 'late'}, 0, 5, 'one two')
        assert 'speaker tag list verification deadline reached' in [record.getMessage() for record in caplog.records]
        assert not any(
            record.levelno >= logging.ERROR and 'speaker tag list verification' in record.getMessage()
            for record in caplog.records
        )
        assert verification_key not in service._inflight_verifications
    finally:
        pool.shutdown(wait=True)


def test_list_verification_unexpected_error_logs_error_with_traceback(monkeypatch, caplog):
    pool = MonitoredThreadPoolExecutor(name='tag-failure', max_workers=1)
    monkeypatch.setattr(service, 'speaker_tag_verify_executor', pool)
    caplog.set_level(logging.INFO)

    def boom(uid, row, start, end, text, *, verification_deadline):
        raise RuntimeError('doomed')

    monkeypatch.setattr(service, 'verified_clip_pcm', boom)
    try:
        future = service._submit_list_verification('u', {'id': 'doom'}, 0, 5, 'one two', time.monotonic() + 1)
        cleared = threading.Event()
        future.add_done_callback(lambda _: cleared.set())
        with pytest.raises(RuntimeError):
            future.result(timeout=2)
        assert cleared.wait(timeout=2)
        verification_key = service._verification_cache_key('u', {'id': 'doom'}, 0, 5, 'one two')
        [failure] = [
            record
            for record in caplog.records
            if record.levelno >= logging.ERROR and 'speaker tag list verification failed' in record.getMessage()
        ]
        assert 'error_type=RuntimeError' in failure.getMessage()
        assert failure.exc_info
        assert verification_key not in service._inflight_verifications
    finally:
        pool.shutdown(wait=True)


def test_list_verification_propagates_contextvars(monkeypatch):
    pool = MonitoredThreadPoolExecutor(name='tag-context', max_workers=1)
    monkeypatch.setattr(service, 'speaker_tag_verify_executor', pool)
    marker = contextvars.ContextVar('speaker_tag_marker', default='absent')
    observed = []

    def verify(uid, row, start, end, text, *, verification_deadline):
        observed.append(marker.get())
        return b'ok'

    monkeypatch.setattr(service, 'verified_clip_pcm', verify)
    try:
        marker.set('byok-marker')
        future = service._submit_list_verification('u', {'id': 'ctx'}, 0, 5, 'one two', time.monotonic() + 1)
        assert future.result(timeout=2) == b'ok'
        assert observed == ['byok-marker']
    finally:
        pool.shutdown(wait=True)


def test_verification_stt_runs_inline_with_one_budgeted_provider_attempt(monkeypatch):
    def forbidden_shared_pool(*args, **kwargs):
        pytest.fail('verification submitted STT to a shared executor')

    monkeypatch.setattr(speaker_sample, 'run_blocking', forbidden_shared_pool)
    words = [{'text': word, 'speaker': 'SPEAKER_00'} for word in 'one two three four five'.split()]
    monkeypatch.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *args, **kwargs: words)
    result = speaker_sample.verify_and_transcribe_sample_in_worker(
        b'wave', 16000, 'one two three four five', None, time.monotonic() + 1
    )
    assert result == ('one two three four five', True, 'ok')

    attempts = []

    class SlowProvider:
        def __init__(self, timeout):
            attempts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            raise TimeoutError('provider timed out')

    monkeypatch.setenv('MODULATE_API_KEY', 'test-only')
    monkeypatch.setattr(pre_recorded, 'require_provider_environment', lambda _: None)
    monkeypatch.setattr(pre_recorded.httpx, 'Client', SlowProvider)
    with pre_recorded.verification_stt_deadline(time.monotonic() + 0.5):
        with pytest.raises(RuntimeError, match='after 1 attempts'):
            pre_recorded.modulate_prerecorded_from_bytes(b'wave')
    assert len(attempts) == 1
    assert 0 < attempts[0].read <= 0.5

    attempts.clear()
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'https://invalid.example')
    with pre_recorded.verification_stt_deadline(time.monotonic() + 0.5):
        with pytest.raises(RuntimeError, match='after 1 attempts'):
            pre_recorded.parakeet_prerecorded_from_bytes(b'wave')
    assert len(attempts) == 1
    assert 0 < attempts[0].read <= 0.5


def test_truncated_clip_is_rejected_before_transcription(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x00\x00' * service.CLIP_SAMPLE_RATE)
    called = []

    async def verify(*args, **kwargs):
        called.append(1)
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert called == []


def test_clip_download_error_skips_prompt_without_leaking_content(monkeypatch, caplog):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)

    def fail(*args):
        raise RuntimeError('private sample data')

    monkeypatch.setattr(service, 'conversation_clip_pcm', fail)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert 'private sample data' not in caplog.text


def test_get_prompts_excludes_misaligned_merged_sync_audio(monkeypatch):
    World(monkeypatch)
    started = NOW - timedelta(hours=1)
    row = {
        'id': 'merged',
        'started_at': started,
        'status': 'completed',
        'sync_live_target': True,
        'sync_merged_from': ['donor'],
        'audio_files': [{'chunk_timestamps': [started.timestamp(), started.timestamp() + 88.2], 'duration': 92.3}],
        'conversation_audio': {'spans': [{'wall_offset': 0, 'len': 149.4}]},
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 0, 'start': 10.28, 'end': 20.28, 'text': 'Please confirm these spoken words'}
        ],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *args, **kwargs: [row])
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: None)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x01\x00' * (10 * 16000))
    checked = []

    def verify(audio, sample_rate, expected_text, language, deadline):
        checked.append(expected_text)
        return ('Static and coughing', False, 'text_mismatch: containment=0.00')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample_in_worker', verify)
    response = service.get_prompts('u', NOW)
    assert response.status == 'no_candidates'
    assert checked == ['Please confirm these spoken words']


def test_owner_clip_window_requires_clean_owner_stretch():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 4, 'is_user': True, 'text': 'one two'},
            {'id': 'b', 'start': 4, 'end': 8, 'is_user': True, 'text': 'three four'},
            {'id': 'c', 'start': 8, 'end': 9, 'is_user': False, 'text': 'x'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) == (0.0, 8.0, 'one two three four')
    assert service.owner_clip_window(conversation, ['a']) is None  # too short
    assert service.owner_clip_window(conversation, ['a', 'c']) is None  # not all the owner


def test_owner_clip_window_rejects_a_second_diarized_voice_even_labeled_user():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': 'mine'},
            {'id': 'b', 'start': 3, 'end': 4, 'is_user': True, 'speaker_id': 1, 'text': 'theirs'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) is None


def test_owner_clip_window_uses_only_text_inside_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b', 'c']) == (5.0, 15.0, 'inside clip')
    no_inside_text = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': ''},
            {'id': 'b', 'start': 8, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': ''},
        ]
    }
    assert service.owner_clip_window(no_inside_text, ['a', 'b']) is None


def test_owner_sample_verifies_only_text_inside_the_clip(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ],
    }
    clipped = []
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service,
        'conversation_clip_pcm',
        lambda uid, conv, start, end, **kwargs: clipped.append((start, end))
        or b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 6),
    )

    async def verify(wav, rate, text, language=None):
        assert text == 'inside clip'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda uid, embedding, pool, **kwargs: 1,
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a', 'b', 'c'])) == 'stored'
    assert clipped == [(5.0, 15.0)]


def test_stale_owner_card_never_schedules_partial_learning(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.StaleOwnerConfirmation):
        service.apply_answer(
            'u', _request(K.owner_check, O.unnamed, A.me, segment_ids=['s1', 'stale']), world.schedule, NOW
        )
    assert not world.scheduled


def test_owner_sample_not_queued_when_prompt_segments_are_gone(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.StaleOwnerConfirmation):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.me), world.schedule, NOW)
    assert not world.scheduled


def test_owner_sample_is_verified_then_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hello there friend'}],
    }
    pooled = []
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 6)
    )

    async def verify(wav, rate, text, language=None):
        assert text == 'hello there friend' and language == 'en'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[3.0, 4.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda uid, embedding, pool, **kwargs: pooled.append((embedding, pool([embedding]))) or 1,
    )
    outcome = asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a']))
    assert outcome == 'stored'
    assert pooled[0][0] == [3.0, 4.0]
    assert pooled[0][1] == pytest.approx([0.6, 0.8])


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_real_live_batches_still_supply_owner_confirmations(memory_bucket, monkeypatch, protection):
    origin = 1700000000.0
    uid, cid = 'synthetic-user', 'synthetic'
    parts = [{'timestamp': origin + offset, 'data': b'\x01\x00' * 64000} for offset in (0, 4)]
    storage.upload_audio_chunks_batch(parts, uid, cid, data_protection_level=protection)
    conversation = {
        'id': cid,
        'started_at': origin,
        'language': 'en',
        'audio_files': [{'chunk_timestamps': [origin, origin + 4], 'duration': 8}],
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hello there friend'}],
        'manual_speaker_assignments': {'generation': 1, 'segments': {'a': {'generation': 1, 'is_user': True}}},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda *args: conversation)

    async def verify(wav, rate, text, language=None):
        assert text == 'hello there friend' and language == 'en'
        assert wav[44:] == b'\x01\x00' * (rate * 8)
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *args: np.array([[3.0, 4.0]]))
    pooled = []
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda *args, **kwargs: pooled.append(args[1]) or True,
    )
    assert asyncio.run(service.store_owner_voice_sample(uid, cid, ['a'])) == 'stored'
    assert pooled == [[3.0, 4.0]]
    assert len(memory_bucket.listings) == len(memory_bucket.reads) == 1


def test_owner_sample_rejected_by_quality_gate_is_not_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hi'}],
    }
    conversation['manual_speaker_assignments'] = {
        'generation': 1,
        'segments': {s['id']: {'generation': 1, 'is_user': True} for s in conversation['transcript_segments']},
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service, 'conversation_clip_pcm', lambda *a, **kwargs: b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 6)
    )

    async def verify(wav, rate, text, language=None):
        return None, False, 'multi_speaker: ratio=0.40'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda *a, **k: pytest.fail('must not pool')
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a'])) == 'rejected_quality'


def test_someone_else_with_a_person_is_the_correction_path(monkeypatch):
    world = World(monkeypatch)
    request = _request(K.confirm_person, O.auto_person, A.someone_else, person_id='p1', suggested_person_id='p9')
    response = service.apply_answer('u', request, world.schedule, NOW)
    assert world.assignments[0]['person_id'] == 'p1' and world.assignments[0]['evidence_source'] == 'card'
    assert response.person_id == 'p1' and response.quality_outcome == Q.person_auto_corrected
    new = _request(K.confirm_person, O.auto_person, A.someone_else, name='Dana', suggested_person_id='p9')
    response = service.apply_answer('u', new, world.schedule, NOW)
    assert world.created[-1]['name'] == 'Dana' and response.person_id == world.created[-1]['id']


def test_not_a_person_clears_an_automatic_label_and_is_remembered(monkeypatch):
    world = World(monkeypatch)
    ignored = []
    monkeypatch.setattr(service.voice_profiles_db, 'record_ignored_voice', lambda *args, **kwargs: ignored.append(args))
    response = service.apply_answer('u', _request(K.confirm_person, O.auto_person, A.not_a_person), world.schedule, NOW)
    assert world.assignments == [
        {
            'person_id': None,
            'is_user': False,
            'speaker_id': 1,
            'use_for_speech_training': False,
            'evidence_source': 'card',
            'rejection': {'kind': 'not_a_person', 'person_id': None},
        }
    ]
    assert ignored == [('u', 'c1', 1, NOW)] and world.answered == ['pid']
    assert response.quality_outcome == Q.person_auto_corrected
    # Revalidate even unnamed prompts: the stored label may have changed since it was served.
    service.apply_answer('u', _request(K.identify, O.unnamed, A.not_a_person), world.schedule, NOW)
    assert len(world.assignments) == 2 and len(ignored) == 2


def test_owner_question_is_binary_or_skip_on_every_plan(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.not_a_person), world.schedule, NOW)
    assert not world.assignments


def test_not_a_person_rejects_a_conversation_outside_the_authenticated_account(monkeypatch):
    World(monkeypatch)
    markers = []
    monkeypatch.setattr(service.voice_profiles_db, 'record_ignored_voice', lambda *args, **kw: markers.append(args))

    def missing(uid, conversation_id, **kwargs):
        assert uid == 'u' and conversation_id == 'foreign'
        raise LookupError('Conversation not found')

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', missing)
    with pytest.raises(LookupError):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.not_a_person, conversation_id='foreign'))
    assert markers == []


def test_ignored_voices_list_skips_deleted_conversations_and_restore_forgets_answers(monkeypatch):
    state = {
        'ignored_voices': {
            'c1:1': {'conversation_id': 'c1', 'speaker_id': 1, 'ignored_at': NOW},
            'c2:3': {'conversation_id': 'c2', 'speaker_id': 3, 'ignored_at': NOW - timedelta(hours=1)},
            'bad': {'conversation_id': 'c3'},
        }
    }
    monkeypatch.setattr(service.voice_profiles_db, 'get_tag_prompt_state', lambda uid: state)
    monkeypatch.setattr(
        service.conversations_db,
        'get_conversations_by_id_without_photos',
        lambda uid, ids: [
            {'id': 'c1', 'structured': {'title': ' TV night '}, 'started_at': NOW},
            {'id': 'c2', 'deleted': True},
        ],
    )
    voices = service.list_ignored_voices('u').voices
    assert [(v.conversation_id, v.speaker_id, v.conversation_title) for v in voices] == [('c1', 1, 'TV night')]
    removed = []
    monkeypatch.setattr(service.voice_profiles_db, 'remove_ignored_voice', lambda *args: removed.append(args) or True)
    assert service.restore_ignored_voice('u', 'c1', 1)
    uid, conversation_id, speaker_id, prompt_ids = removed[0]
    assert (uid, conversation_id, speaker_id) == ('u', 'c1', 1)
    assert set(prompt_ids) == {service.prompt_id('c1', 1, kind) for kind in K}


def test_ignored_voices_limit_applies_after_missing_and_deleted_conversations(monkeypatch):
    entries = [
        {'conversation_id': f'c{i}', 'speaker_id': 1, 'ignored_at': NOW - timedelta(minutes=i)} for i in range(120)
    ]
    state = {'ignored_voices': {f"{entry['conversation_id']}:1": entry for entry in entries}}
    monkeypatch.setattr(service.voice_profiles_db, 'get_tag_prompt_state', lambda uid: state)

    def conversations(uid, ids):
        assert uid == 'u'
        return [{'id': cid, 'deleted': int(cid[1:]) < 60} for cid in ids if cid != 'c60']

    monkeypatch.setattr(service.conversations_db, 'get_conversations_by_id_without_photos', conversations)
    result = service.list_ignored_voices('u').voices
    assert len(result) == service.IGNORED_VOICES_LIST_LIMIT
    assert [voice.conversation_id for voice in result] == [f'c{i}' for i in range(61, 111)]


def test_ignored_voice_uses_the_merged_survivor_and_resolved_speaker(monkeypatch):
    World(monkeypatch)
    markers = []

    def assign(uid, conversation_id, **kwargs):
        assert uid == 'u' and conversation_id == 'donor' and kwargs['speaker_id'] == 1
        return (
            {
                'id': 'survivor',
                'manual_speaker_assignments': {'generation': 7},
                'transcript_segments': [
                    {'id': 's1', 'speaker_id': 8},
                    {'id': 's2', 'speaker_id': 8},
                    {'id': 'other', 'speaker_id': 1},
                ],
            },
            ['s1', 's2'],
            [],
            [],
        )

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    monkeypatch.setattr(
        service.voice_profiles_db, 'record_ignored_voice', lambda *args, **kwargs: markers.append((args, kwargs))
    )
    service.apply_answer('u', _request(K.identify, O.unnamed, A.not_a_person, conversation_id='donor'), now=NOW)
    assert markers == [(('u', 'survivor', 8, NOW), {'assignment_generation': 7})]


def test_free_user_can_reject_previously_served_paid_card(monkeypatch):
    world = World(monkeypatch, paid=False)
    service.apply_answer(
        'u', _request(K.confirm_person, O.auto_person, A.someone_else, suggested_person_id='p1'), world.schedule, NOW
    )
    assert world.assignments and world.assignments[0]['person_id'] is None
